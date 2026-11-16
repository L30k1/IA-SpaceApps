import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from database.medical_records import VITAL_SIGNS, utc_datetime
from volt import VOLT_FIELD, advance_test


class EarlyCheckInError(Exception):
    def __init__(self, available_at):
        self.available_at = available_at
        super().__init__("The required interval between check-ins has not passed yet.")


def initialize(path):
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS secuencia_usuarios (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                ultimo INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkups (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                profile TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 0,
                messages TEXT NOT NULL,
                hr INTEGER NOT NULL,
                spo2 INTEGER NOT NULL,
                temp REAL NOT NULL,
                status TEXT,
                finished_at TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS open_checkup
            ON checkups (user_id, profile) WHERE finished_at IS NULL;
            CREATE TABLE IF NOT EXISTS expedientes (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                astronauta_id TEXT UNIQUE NOT NULL,
                contenido TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkup_details (
                checkup_id INTEGER PRIMARY KEY REFERENCES checkups(id),
                contenido TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS psych_chat (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                revision INTEGER NOT NULL,
                mensajes TEXT NOT NULL,
                inicio_visible INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS emergency_chat (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                revision INTEGER NOT NULL,
                mensajes TEXT NOT NULL,
                inicio_visible INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS volt_drafts (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                contenido TEXT NOT NULL
            );
        """)
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR IGNORE INTO secuencia_usuarios VALUES (1, 0)")
        if "clave_edicion_hash" not in {column[1] for column in db.execute("PRAGMA table_info(users)")}:
            db.execute("ALTER TABLE users ADD COLUMN clave_edicion_hash TEXT")
        if "es_admin" not in {column[1] for column in db.execute("PRAGMA table_info(users)")}:
            db.execute("ALTER TABLE users ADD COLUMN es_admin INTEGER NOT NULL DEFAULT 0")
        if "inicio_visible" not in {column[1] for column in db.execute("PRAGMA table_info(psych_chat)")}:
            db.execute("ALTER TABLE psych_chat ADD COLUMN inicio_visible INTEGER NOT NULL DEFAULT 0")


def create_user(path, password_hash, medical_record, edit_key_hash=None):
    with closing(sqlite3.connect(path)) as db, db:
        # Existing sessions store the ID. A new account must never reuse it.
        user_id = db.execute(
            "UPDATE secuencia_usuarios SET ultimo = MAX(ultimo, (SELECT COALESCE(MAX(id), 0) FROM users)) + 1 "
            "WHERE id = 1 RETURNING ultimo"
        ).fetchone()[0]
        # Existing SQLite databases require the email column.
        db.execute(
            "INSERT INTO users (id, email, name, password_hash, clave_edicion_hash) VALUES (?, ?, ?, ?, ?)",
            (user_id, f"astronauta:{medical_record['_id']}", medical_record["astronauta"]["nombre"],
             password_hash, edit_key_hash),
        )
        db.execute(
            "INSERT INTO expedientes (user_id, astronauta_id, contenido) VALUES (?, ?, ?)",
            (user_id, medical_record["_id"], json.dumps(medical_record)),
        )
        return user_id


def edit_credentials(path, user_id):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        return db.execute("SELECT password_hash, clave_edicion_hash FROM users WHERE id = ?", (user_id,)).fetchone()


def configure_edit_key(path, user_id, key_hash):
    with closing(sqlite3.connect(path)) as db, db:
        outcome = db.execute(
            "UPDATE users SET clave_edicion_hash = ? WHERE id = ? AND clave_edicion_hash IS NULL",
            (key_hash, user_id),
        )
        return outcome.rowcount == 1


def medical_record_for_user(path, user_id):
    with closing(sqlite3.connect(path)) as db:
        return read_record_row(db, user_id)


def is_administrator(path, user_id):
    with closing(sqlite3.connect(path)) as db:
        return db.execute("SELECT 1 FROM users WHERE id = ? AND es_admin = 1", (user_id,)).fetchone() is not None


def list_admin_accounts(path, identifier, page_offset, limit_value):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        statement = """
            SELECT users.id, users.name, users.email, users.es_admin, expedientes.astronauta_id
            FROM users LEFT JOIN expedientes ON expedientes.user_id = users.id
        """
        parameters = ()
        if identifier:
            statement += " WHERE expedientes.astronauta_id = ?"
            parameters = (identifier,)
        return db.execute(statement + " ORDER BY users.id DESC LIMIT ? OFFSET ?",
                          (*parameters, limit_value, page_offset)).fetchall()


def get_admin_account(path, user_id):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        row_data = db.execute("""
            SELECT users.id, users.name, users.email, users.es_admin, expedientes.astronauta_id,
                   expedientes.contenido
            FROM users LEFT JOIN expedientes ON expedientes.user_id = users.id
            WHERE users.id = ?
        """, (user_id,)).fetchone()
        if row_data is None:
            return None
        account = dict(row_data)
        account["expediente"] = json.loads(account.pop("contenido") or "null")
        return account


def delete_account(path, administrator, account_id):
    if type(account_id) is not int or administrator == account_id:
        return False
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute(
            "SELECT 1 FROM users WHERE id = ? AND es_admin = 1", (administrator,),
        ).fetchone() is None:
            return False
        db.execute("UPDATE secuencia_usuarios SET ultimo = MAX(ultimo, (SELECT MAX(id) FROM users)) WHERE id = 1")
        if db.execute("DELETE FROM users WHERE id = ?", (account_id,)).rowcount == 0:
            return False
        db.execute("DELETE FROM checkup_details WHERE checkup_id IN (SELECT id FROM checkups WHERE user_id = ?)",
                   (account_id,))
        for table_name in ("checkups", "psych_chat", "emergency_chat", "volt_drafts", "expedientes"):
            db.execute(f"DELETE FROM {table_name} WHERE user_id = ?", (account_id,))

        # Use the same write lock as the medical record export.
        folder = Path(f"{path}.expedientes").resolve() / str(account_id)
        if folder.resolve() != folder:
            raise OSError("The medical record folder points outside the expected path.")
        if folder.exists():
            rmtree(folder)
        return True


def update_medical_record(path, user_id, apply_edit):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        medical_record = read_record_row(db, user_id)
        if medical_record is None:
            return False
        updated_record = apply_edit(medical_record)
        db.execute("UPDATE expedientes SET contenido = ? WHERE user_id = ?",
                   (json.dumps(updated_record, ensure_ascii=False), user_id))
        return True


def read_record_row(db, user_id):
    row = db.execute("SELECT contenido FROM expedientes WHERE user_id = ?", (user_id,)).fetchone()
    return json.loads(row[0]) if row else None


def read_volt_draft(db, user_id):
    row = db.execute("SELECT contenido FROM volt_drafts WHERE user_id = ?", (user_id,)).fetchone()
    return json.loads(row[0]) if row else None


def volt_draft(path, user_id):
    with closing(sqlite3.connect(path)) as db:
        return read_volt_draft(db, user_id)


def update_volt(path, user_id, action, identifier, answers, current_time):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        medical_record = read_record_row(db, user_id)
        active_draft = read_volt_draft(db, user_id)
        if medical_record is None:
            raise ValueError("This account has no active medical record.")
        entries = medical_record.get(VOLT_FIELD, [])
        has_next, entry, completed_id = advance_test(active_draft, entries, action, identifier, answers, current_time)
        if entry is not None:
            medical_record[VOLT_FIELD] = [*entries, entry]
            db.execute(
                "UPDATE expedientes SET contenido = ? WHERE user_id = ?",
                (json.dumps(medical_record, ensure_ascii=False), user_id),
            )
        if has_next is None:
            if active_draft is not None:
                db.execute("DELETE FROM volt_drafts WHERE user_id = ?", (user_id,))
        elif has_next is not active_draft:
            db.execute(
                "INSERT INTO volt_drafts VALUES (?, ?) ON CONFLICT (user_id) DO UPDATE SET contenido = excluded.contenido",
                (user_id, json.dumps(has_next)),
            )
        return completed_id


def save_record_result(path, user_id, field_name, entry, *fields):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        medical_record = read_record_row(db, user_id)
        if medical_record is None:
            return False
        entries = medical_record.setdefault(field_name, [])
        for previous in entries:
            if previous["id"] == entry["id"]:
                return all(previous.get(full_name) == entry.get(full_name) for full_name in fields)
        entries.append(entry)
        db.execute(
            "UPDATE expedientes SET contenido = ? WHERE user_id = ?",
            (json.dumps(medical_record, ensure_ascii=False), user_id),
        )
        return True


def next_check_in(entries, interval):
    last_item = max((utc_datetime(entry["fecha_hora"]) for entry in entries), default=None)
    return last_item + interval if last_item is not None else None


def save_psych_report(path, user_id, field_name, entry, interval):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        medical_record = read_record_row(db, user_id)
        if medical_record is None:
            return False
        entries = medical_record.setdefault(field_name, [])
        if any(previous_value["id"] == entry["id"] for previous_value in entries):
            return False
        available_at = next_check_in(entries, interval)
        if available_at is not None and utc_datetime(entry["fecha_hora"]) < available_at:
            raise EarlyCheckInError(available_at)
        entries.append(entry)
        db.execute(
            "UPDATE expedientes SET contenido = ? WHERE user_id = ?",
            (json.dumps(medical_record, ensure_ascii=False), user_id),
        )
        return True


def save_psych_followup(path, user_id, field_name, entry_id, followup):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        medical_record = read_record_row(db, user_id)
        if medical_record is None:
            return False
        for entry in medical_record.get(field_name, []):
            if entry["id"] == entry_id and not entry.get("seguimiento_ia"):
                entry["seguimiento_ia"] = followup
                db.execute(
                    "UPDATE expedientes SET contenido = ? WHERE user_id = ?",
                    (json.dumps(medical_record, ensure_ascii=False), user_id),
                )
                return True
        return False


def psych_chat(path, user_id, emergency=False, *, include_archived=False):
    table_name = "emergency_chat" if emergency else "psych_chat"
    with closing(sqlite3.connect(path)) as db:
        row = db.execute(f"SELECT revision, mensajes, inicio_visible FROM {table_name} WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return 0, []
        return row[0], json.loads(row[1])[0 if include_archived else row[2]:]


def save_psych_chat(path, user_id, revision, new_turns, emergency=False):
    table_name = "emergency_chat" if emergency else "psych_chat"
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if revision == 0:
            updated_record = db.execute(
                f"INSERT INTO {table_name} (user_id, revision, mensajes) SELECT id, 1, ? FROM users WHERE id = ? "
                "ON CONFLICT (user_id) DO NOTHING",
                (json.dumps(new_turns, ensure_ascii=False), user_id),
            )
        else:
            row = db.execute(f"SELECT mensajes FROM {table_name} WHERE user_id = ? AND revision = ?",
                             (user_id, revision)).fetchone()
            if row is None:
                return False
            content_blob = json.dumps([*json.loads(row[0]), *new_turns], ensure_ascii=False)
            updated_record = db.execute(
                f"UPDATE {table_name} SET mensajes = ?, revision = revision + 1 "
                "WHERE user_id = ? AND revision = ?",
                (content_blob, user_id, revision),
            )
        return updated_record.rowcount == 1


def clear_support_chat(path, user_id, revision):
    with closing(sqlite3.connect(path)) as db, db:
        updated_record = db.execute(
            "UPDATE psych_chat SET inicio_visible = json_array_length(mensajes), revision = revision + 1 "
            "WHERE user_id = ? AND revision = ?", (user_id, revision),
        )
        return updated_record.rowcount == 1


def find_user_by_astronaut_id(path, astronaut_id_value):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        return db.execute(
            "SELECT users.id, users.password_hash, "
            "COALESCE(json_extract(expedientes.contenido, '$.astronauta.nombre'), users.name) AS name FROM expedientes "
            "JOIN users ON users.id = expedientes.user_id WHERE expedientes.astronauta_id = ?",
            (astronaut_id_value,),
        ).fetchone()


def open_checkup(path, user_id, profile, greeting):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(
            "INSERT INTO checkups (user_id, profile, messages, hr, spo2, temp) "
            "SELECT id, ?, ?, 0, 0, 0 FROM users WHERE id = ? "
            "ON CONFLICT (user_id, profile) WHERE finished_at IS NULL DO NOTHING",
            (profile, json.dumps([greeting]), user_id),
        )


def get_open_checkup(path, user_id, profile):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        return db.execute(
            "SELECT checkups.*, checkup_details.contenido AS details "
            "FROM checkups LEFT JOIN checkup_details ON checkup_id = checkups.id "
            "WHERE user_id = ? AND profile = ? AND finished_at IS NULL",
            (user_id, profile),
        ).fetchone()


def checkup_record(record_id, finished_at, messages, vitals, details, status):
    try:
        timestamp = utc_datetime(finished_at)
    except ValueError:
        timestamp = datetime.strptime(finished_at, "%d/%m/%Y %H:%M UTC").replace(tzinfo=timezone.utc)
    measured_values = details.get("telemetria", dict(zip(("hr", "spo2", "temp"), vitals)))
    return {
        **{field: details.get(field) or None for field in ("mision_id", "fase", "motivo", "actividad")},
        "id": record_id,
        "fecha_hora": timestamp.isoformat(),
        "resultado": status,
        "mediciones": [
            {"tipo": kind, "valor": measured_values[key], "unidad": VITAL_SIGNS[kind][1]}
            for kind, key in zip(VITAL_SIGNS, ("hr", "spo2", "temp")) if measured_values[key] is not None
        ],
        "conversacion": messages,
        **{field: details[field] for field in ("evaluacion_ia", "evaluacion", "comparacion_referencias")
           if field in details},
        **({"contexto_fc": details["contexto_fc"]} if details.get("contexto_fc") else {}),
    }


def save_turn(path, draft, messages, vitals, details, status=None):
    finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds") if status else None
    with closing(sqlite3.connect(path)) as db, db:
        result = db.execute(
            "UPDATE checkups SET messages = ?, hr = ?, spo2 = ?, temp = ?, "
            "status = ?, finished_at = ?, revision = revision + 1 "
            "WHERE id = ? AND user_id = ? AND profile = ? AND revision = ? AND finished_at IS NULL",
            (json.dumps(messages), *vitals, status, finished_at, draft["id"], draft["user_id"],
             draft["profile"], draft["revision"]),
        )
        if result.rowcount != 1:
            return False
        if finished_at:
            record_row = db.execute(
                "SELECT contenido FROM expedientes WHERE user_id = ? AND astronauta_id = ?",
                (draft["user_id"], draft["profile"]),
            ).fetchone()
            if record_row is None:
                raise ValueError("The medical record for this checkup was not found.")
            medical_record = json.loads(record_row[0])
            record_id = f"chequeo-{uuid4().hex}"
            medical_record["chequeos"].append(
                checkup_record(record_id, finished_at, messages, vitals, details, status)
            )
            db.execute(
                "UPDATE expedientes SET contenido = ? WHERE user_id = ?",
                (json.dumps(medical_record, ensure_ascii=False), draft["user_id"]),
            )
            details = {**details, "expediente_chequeo_id": record_id}
        db.execute(
            "INSERT INTO checkup_details (checkup_id, contenido) VALUES (?, ?) "
            "ON CONFLICT (checkup_id) DO UPDATE SET contenido = excluded.contenido",
            (draft["id"], json.dumps(details)),
        )
        return True


def history(path, user_id, profile):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        return read_history(db, user_id, profile)


def read_history(db, user_id, profile):
    return db.execute(
        "SELECT checkups.*, checkup_details.contenido AS details "
        "FROM checkups LEFT JOIN checkup_details ON checkup_id = checkups.id "
        "WHERE user_id = ? AND profile = ? AND finished_at IS NOT NULL "
        "ORDER BY id DESC",
        (user_id, profile),
    ).fetchall()


@contextmanager
def record_for_export(path, user_id):
    with closing(sqlite3.connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        # Serialize file writes with SQLite updates.
        db.execute("BEGIN IMMEDIATE")
        medical_record = read_record_row(db, user_id)
        if medical_record is None:
            yield None, []
        else:
            yield medical_record, read_history(db, user_id, medical_record["_id"])
