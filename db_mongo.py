import json
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import ConfigurationError, ConnectionFailure, DuplicateKeyError, InvalidURI, OperationFailure, PyMongoError

from database.medical_records import utc_datetime
from db import EarlyCheckInError, next_check_in
from volt import VOLT_FIELD, advance_test


AccountConflict = DuplicateKeyError
DatabaseError = PyMongoError


def _startup_diagnostic(error, stage):
    detail_text = str(error).casefold()
    if isinstance(error, OperationFailure):
        if error.code == 18 or "bad auth" in detail_text or "authentication failed" in detail_text:
            return "[MONGO_AUTENTICACION] Atlas rejected the credentials. Check the database username and password in MONGODB_URI."
        if error.code == 13 or "not authorized" in detail_text:
            return "[MONGO_PERMISOS] Atlas denied the operation. Check that the user has the readWrite role on MONGODB_DB or medispace."
        if isinstance(error, DuplicateKeyError) or error.code in {85, 86, 11000}:
            return "[MONGO_INDICES] Atlas found a conflict while creating indexes. Check the database indexes and records."
    if isinstance(error, ConnectionFailure):
        return "[MONGO_RED] Could not reach Atlas. Check the Render outbound ranges in IP Access List and the cluster status."
    if isinstance(error, InvalidURI):
        return "[MONGO_URI] Check the MONGODB_URI format. Use the connection string from Connect → Drivers and percent-encode special characters in the password."
    if isinstance(error, ConfigurationError) and any(message_text in detail_text for message_text in ("_mongodb._tcp", "dns", "srv record", "nxdomain")):
        return "[MONGO_DNS] Could not resolve the cluster address. Copy it again from Atlas → Connect → Drivers and check the cluster status."
    if isinstance(error, (ConfigurationError, ValueError)):
        return "[MONGO_CONFIG] Check the MONGODB_URI format and the MONGODB_DB name."
    return f"[MONGO_ARRANQUE] Startup failed during {stage}. Check the cluster status and database user permissions."


def connect_database(uri, full_name):
    api_client = None
    stage = "configuration"
    try:
        api_client = MongoClient(uri, serverSelectionTimeoutMS=10000, timeoutMS=12000)
        database = api_client[full_name]
        stage = "connection"
        database.command("ping")
        stage = "index creation"
        database.usuarios.create_index("email", unique=True)
        database.usuarios.create_index("astronauta_id", unique=True, sparse=True)
        database.monitoreos.create_index("borrador_de", unique=True, sparse=True)
        database.monitoreos.create_index([("user_id", 1), ("profile", 1), ("finished_at", -1)])
    except (PyMongoError, ValueError) as error:
        if api_client is not None:
            api_client.close()
        raise RuntimeError(_startup_diagnostic(error, stage)) from None
    return database


def create_user(database, password_hash, medical_record, edit_key_hash=None):
    account_id = uuid4().hex
    # Older deployments still have the unique email index.
    database.usuarios.insert_one({
        "_id": account_id, "email": f"astronauta:{medical_record['_id']}", "name": medical_record["astronauta"]["nombre"],
        "password_hash": password_hash, "astronauta_id": medical_record["_id"],
        "expediente": medical_record, "revision_expediente": 0, "clave_edicion_hash": edit_key_hash,
    })
    return account_id


def edit_credentials(database, user_id):
    account_id = database.usuarios.find_one({"_id": user_id}, {"password_hash": 1, "clave_edicion_hash": 1})
    if account_id is not None:
        account_id.setdefault("clave_edicion_hash", None)
    return account_id


def configure_edit_key(database, user_id, key_hash):
    outcome = database.usuarios.update_one(
        {"_id": user_id, "clave_edicion_hash": None}, {"$set": {"clave_edicion_hash": key_hash}},
    )
    return outcome.matched_count == 1


def find_user_by_astronaut_id(database, astronaut_id_value):
    account_id = database.usuarios.find_one(
        {"astronauta_id": astronaut_id_value}, {"password_hash": 1, "name": 1, "expediente.astronauta.nombre": 1},
    )
    if account_id is None:
        return None
    full_name = account_id.get("expediente", {}).get("astronauta", {}).get("nombre") or account_id["name"]
    return {"id": account_id["_id"], "name": full_name, "password_hash": account_id["password_hash"]}


def medical_record_for_user(database, user_id):
    if user_id is None:
        return None
    account_id = database.usuarios.find_one({"_id": user_id}, {"expediente": 1})
    return account_id.get("expediente") if account_id else None


def is_administrator(database, user_id):
    account = database.usuarios.find_one({"_id": user_id}, {"es_admin": 1})
    return account is not None and account.get("es_admin") is True


ADMIN_ACCOUNT_FIELDS = {"name": 1, "email": 1, "astronauta_id": 1, "es_admin": 1}


def list_admin_accounts(database, identifier, page_offset, limit_value):
    query_filter = {"astronauta_id": identifier} if identifier else {}
    accounts = database.usuarios.find(query_filter, ADMIN_ACCOUNT_FIELDS).sort("_id", -1).skip(page_offset).limit(limit_value)
    return [{**account, "id": account["_id"], "es_admin": account.get("es_admin") is True} for account in accounts]


def get_admin_account(database, user_id):
    fields = {**ADMIN_ACCOUNT_FIELDS, "expediente": 1}
    account = database.usuarios.find_one({"_id": user_id}, fields)
    if account is None and ObjectId.is_valid(user_id):
        account = database.usuarios.find_one({"_id": ObjectId(user_id)}, fields)
    return {**account, "id": account["_id"], "es_admin": account.get("es_admin") is True} if account else None


def delete_account(database, administrator, account_id):
    if administrator == account_id:
        return False

    def delete_records(sesion):
        permission = database.usuarios.update_one(
            {"_id": administrator, "es_admin": True}, {"$inc": {"revision_expediente": 1}}, session=sesion,
        )
        if not permission.matched_count:
            return False
        account = database.usuarios.delete_one({"_id": account_id}, session=sesion)
        if not account.deleted_count:
            return False
        database.monitoreos.delete_many({"user_id": account_id}, session=sesion)
        database.chat_psicologico.delete_many(
            {"$or": [{"user_id": account_id}, {"_id": {"$in": [account_id, f"emergencia:{account_id}"]}}]}, session=sesion,
        )
        return True

    with database.client.start_session() as sesion:
        return sesion.with_transaction(delete_records)


def _insert_user_record(database, account_id, collection, document):
    def insert_record(sesion):
        # Writing to the account serializes record creation with account deletion.
        account = database.usuarios.update_one(
            {"_id": account_id}, {"$inc": {"revision_expediente": 1}}, session=sesion,
        )
        if not account.matched_count:
            return False
        collection.insert_one(document, session=sesion)
        return True

    with database.client.start_session() as sesion:
        return sesion.with_transaction(insert_record)


def volt_draft(database, user_id):
    account_id = database.usuarios.find_one({"_id": user_id}, {"volt_draft": 1})
    return account_id.get("volt_draft") if account_id else None


def _record_state(database, account_id):
    return database.usuarios.find_one({"_id": account_id, "expediente": {"$exists": True}},
                                      {"expediente": 1, "revision_expediente": 1, "volt_draft": 1})


def _update_record(database, state, changes):
    outcome = database.usuarios.update_one(
        {"_id": state["_id"], "revision_expediente": state["revision_expediente"]},
        {"$set": changes, "$inc": {"revision_expediente": 1}},
    )
    return bool(outcome.matched_count)


def update_medical_record(database, user_id, apply_edit):
    for _ in range(8):
        state = _record_state(database, user_id)
        if state is None:
            return False
        updated_record = apply_edit(state["expediente"])
        if _update_record(database, state, {"expediente": updated_record}):
            return True
    raise PyMongoError("The medical record changed during another operation.")


def update_volt(database, user_id, action, identifier, answers, current_time):
    for _ in range(8):
        state = _record_state(database, user_id)
        if state is None:
            raise ValueError("This account has no active medical record.")
        active_draft = state.get("volt_draft")
        entries = state["expediente"].get(VOLT_FIELD, [])
        has_next, entry, completed_id = advance_test(active_draft, entries, action, identifier, answers, current_time)
        if has_next is active_draft and entry is None:
            return completed_id
        changes = {"volt_draft": has_next}
        if entry is not None:
            changes[f"expediente.{VOLT_FIELD}"] = [*entries, entry]
        if _update_record(database, state, changes):
            return completed_id
    raise PyMongoError("The medical record changed during another operation.")


def save_record_result(database, user_id, field_name, entry, *fields):
    for _ in range(8):
        state = _record_state(database, user_id)
        if state is None:
            return False
        entries = state["expediente"].get(field_name, [])
        previous = next((r for r in entries if r["id"] == entry["id"]), None)
        if previous is not None:
            return all(previous.get(full_name) == entry.get(full_name) for full_name in fields)
        if _update_record(database, state, {f"expediente.{field_name}": [*entries, entry]}):
            return True
    raise PyMongoError("The medical record changed during another operation.")


def save_psych_report(database, user_id, field_name, entry, interval):
    for _ in range(8):
        state = _record_state(database, user_id)
        if state is None:
            return False
        entries = state["expediente"].get(field_name, [])
        if any(r["id"] == entry["id"] for r in entries):
            return False
        available_at = next_check_in(entries, interval)
        if available_at is not None and utc_datetime(entry["fecha_hora"]) < available_at:
            raise EarlyCheckInError(available_at)
        if _update_record(database, state, {f"expediente.{field_name}": [*entries, entry]}):
            return True
    raise PyMongoError("The medical record changed during another operation.")


def save_psych_followup(database, user_id, field_name, entry_id, followup):
    outcome = database.usuarios.update_one(
        {"_id": user_id, f"expediente.{field_name}": {"$elemMatch": {"id": entry_id, "seguimiento_ia": None}}},
        {"$set": {f"expediente.{field_name}.$.seguimiento_ia": followup}, "$inc": {"revision_expediente": 1}},
    )
    return bool(outcome.matched_count)


def psych_chat(database, user_id, emergency=False, *, include_archived=False):
    identifier = f"emergencia:{user_id}" if emergency else user_id
    conversation = database.chat_psicologico.find_one({"_id": identifier})
    if conversation is None:
        return 0, []
    start = 0 if include_archived else conversation.get("inicio_visible", 0)
    return conversation["revision"], conversation["mensajes"][start:]


def save_psych_chat(database, user_id, revision, new_turns, emergency=False):
    identifier = f"emergencia:{user_id}" if emergency else user_id
    if revision == 0:
        try:
            return _insert_user_record(database, user_id, database.chat_psicologico, {
                "_id": identifier, "user_id": user_id, "canal": "emergencia" if emergency else "apoyo",
                "revision": 1, "mensajes": new_turns,
            })
        except DuplicateKeyError:
            return False
    outcome = database.chat_psicologico.update_one(
        {"_id": identifier, "revision": revision},
        {"$push": {"mensajes": {"$each": new_turns}}, "$inc": {"revision": 1}},
    )
    return bool(outcome.matched_count)


def clear_support_chat(database, user_id, revision):
    outcome = database.chat_psicologico.update_one(
        {"_id": user_id, "revision": revision},
        [{"$set": {"inicio_visible": {"$size": "$mensajes"}, "revision": {"$add": ["$revision", 1]}}}],
    )
    return bool(outcome.matched_count)


def open_checkup(database, user_id, profile, greeting):
    try:
        _insert_user_record(database, user_id, database.monitoreos, {
            "_id": uuid4().hex, "user_id": user_id, "profile": profile,
            "borrador_de": f"{user_id}:{profile}",
            "revision": 0, "messages": [greeting], "details": {},
            "hr": 0, "spo2": 0, "temp": 0, "status": None, "finished_at": None,
        })
    except DuplicateKeyError:
        # Two requests can try to create the same draft.
        if database.monitoreos.find_one({"user_id": user_id, "profile": profile, "finished_at": None}, {"_id": 1}) is None:
            raise


def _checkup_row(document):
    return {
        **document, "id": document["_id"], "messages": json.dumps(document["messages"], ensure_ascii=False),
        "details": json.dumps(document["details"], ensure_ascii=False),
    }


def get_open_checkup(database, user_id, profile):
    document = database.monitoreos.find_one({"user_id": user_id, "profile": profile, "finished_at": None})
    return _checkup_row(document) if document else None


def save_turn(database, draft, messages, vitals, details, status=None):
    finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds") if status else None
    if finished_at:
        details = {**details, "expediente_chequeo_id": f"chequeo-{draft['id']}"}
    changes = dict(zip(("hr", "spo2", "temp"), vitals))
    changes.update(messages=messages, details=details, status=status, finished_at=finished_at)
    update_operation = {"$set": changes, "$inc": {"revision": 1}}
    if finished_at:
        update_operation["$unset"] = {"borrador_de": ""}
    outcome = database.monitoreos.update_one(
        {"_id": draft["id"], "user_id": draft["user_id"], "revision": draft["revision"], "finished_at": None},
        update_operation,
    )
    return bool(outcome.matched_count)


def history(database, user_id, profile):
    documents = database.monitoreos.find({"user_id": user_id, "profile": profile, "finished_at": {"$ne": None}})
    return [_checkup_row(document) for document in documents.sort("finished_at", -1)]


@contextmanager
def record_for_export(database, user_id):
    medical_record = medical_record_for_user(database, user_id)
    yield medical_record, history(database, user_id, medical_record["_id"]) if medical_record else []
