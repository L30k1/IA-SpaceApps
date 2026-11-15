import json
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from pymongo import MongoClient
from pymongo.errors import ConfigurationError, ConnectionFailure, DuplicateKeyError, InvalidURI, OperationFailure, PyMongoError

from database.expedientes import fecha_utc
from db import RegistroPrematuro, proximo_registro
from volt import CAMPO_VOLT, avanzar


ConflictoCuenta = DuplicateKeyError
ErrorBase = PyMongoError


def _diagnostico_arranque(error, etapa):
    detalle = str(error).casefold()
    if isinstance(error, OperationFailure):
        if error.code == 18 or "bad auth" in detalle or "authentication failed" in detalle:
            return "[MONGO_AUTENTICACION] Atlas rechazó las credenciales. Revisa el usuario de base de datos y la contraseña en MONGODB_URI."
        if error.code == 13 or "not authorized" in detalle:
            return "[MONGO_PERMISOS] Atlas rechazó la operación. Revisa que el usuario tenga el rol readWrite en MONGODB_DB o medispace."
        if isinstance(error, DuplicateKeyError) or error.code in {85, 86, 11000}:
            return "[MONGO_INDICES] Atlas encontró un conflicto al crear los índices. Revisa los índices y registros de esa base."
    if isinstance(error, ConnectionFailure):
        return "[MONGO_RED] No se pudo alcanzar Atlas. Revisa los rangos de salida de Render en IP Access List y el estado del clúster."
    if isinstance(error, InvalidURI):
        return "[MONGO_URI] Revisa el formato de MONGODB_URI. Usa la cadena de Connect → Drivers y codifica los caracteres especiales de la contraseña."
    if isinstance(error, ConfigurationError) and any(texto in detalle for texto in ("_mongodb._tcp", "dns", "srv record", "nxdomain")):
        return "[MONGO_DNS] No se pudo resolver el clúster. Vuelve a copiar la dirección desde Atlas → Connect → Drivers y revisa el estado del clúster."
    if isinstance(error, (ConfigurationError, ValueError)):
        return "[MONGO_CONFIG] Revisa el formato de MONGODB_URI y el nombre de MONGODB_DB."
    return f"[MONGO_ARRANQUE] Falló la etapa {etapa}. Revisa el estado del clúster y los permisos del usuario."


def conectar(uri, nombre):
    cliente = None
    etapa = "configuración"
    try:
        cliente = MongoClient(uri, serverSelectionTimeoutMS=10000, timeoutMS=12000)
        database = cliente[nombre]
        etapa = "conexión"
        database.command("ping")
        etapa = "creación de índices"
        database.usuarios.create_index("email", unique=True)
        database.usuarios.create_index("astronauta_id", unique=True, sparse=True)
        database.monitoreos.create_index("borrador_de", unique=True, sparse=True)
        database.monitoreos.create_index([("user_id", 1), ("profile", 1), ("finished_at", -1)])
    except (PyMongoError, ValueError) as error:
        if cliente is not None:
            cliente.close()
        raise RuntimeError(_diagnostico_arranque(error, etapa)) from None
    return database


def create_user(database, password_hash, expediente):
    usuario = uuid4().hex
    # El índice único de email sigue presente en despliegues anteriores.
    database.usuarios.insert_one({
        "_id": usuario, "email": f"astronauta:{expediente['_id']}", "name": expediente["astronauta"]["nombre"],
        "password_hash": password_hash, "astronauta_id": expediente["_id"],
        "expediente": expediente, "revision_expediente": 0,
    })
    return usuario


def find_user_by_astronauta(database, astronauta_id):
    usuario = database.usuarios.find_one(
        {"astronauta_id": astronauta_id}, {"password_hash": 1, "name": 1, "expediente.astronauta.nombre": 1},
    )
    if usuario is None:
        return None
    nombre = usuario.get("expediente", {}).get("astronauta", {}).get("nombre") or usuario["name"]
    return {"id": usuario["_id"], "name": nombre, "password_hash": usuario["password_hash"]}


def expediente_for_user(database, user_id):
    if user_id is None:
        return None
    usuario = database.usuarios.find_one({"_id": user_id}, {"expediente": 1})
    return usuario.get("expediente") if usuario else None


def volt_draft(database, user_id):
    usuario = database.usuarios.find_one({"_id": user_id}, {"volt_draft": 1})
    return usuario.get("volt_draft") if usuario else None


def _estado(database, usuario):
    return database.usuarios.find_one({"_id": usuario, "expediente": {"$exists": True}},
                                      {"expediente": 1, "revision_expediente": 1, "volt_draft": 1})


def _actualizar(database, estado, cambios):
    resultado = database.usuarios.update_one(
        {"_id": estado["_id"], "revision_expediente": estado["revision_expediente"]},
        {"$set": cambios, "$inc": {"revision_expediente": 1}},
    )
    return bool(resultado.matched_count)


def actualizar_volt(database, user_id, accion, identificador, respuestas, ahora):
    for _ in range(8):
        estado = _estado(database, user_id)
        if estado is None:
            raise ValueError("La cuenta no tiene un expediente activo.")
        borrador = estado.get("volt_draft")
        registros = estado["expediente"].get(CAMPO_VOLT, [])
        siguiente, registro, completado = avanzar(borrador, registros, accion, identificador, respuestas, ahora)
        if siguiente is borrador and registro is None:
            return completado
        cambios = {"volt_draft": siguiente}
        if registro is not None:
            cambios[f"expediente.{CAMPO_VOLT}"] = [*registros, registro]
        if _actualizar(database, estado, cambios):
            return completado
    raise PyMongoError("El expediente se modificó en otra operación.")


def save_cognitive_report(database, user_id, campo, registro, campo_respuestas):
    for _ in range(8):
        estado = _estado(database, user_id)
        if estado is None:
            return False
        registros = estado["expediente"].get(campo, [])
        anterior = next((r for r in registros if r["id"] == registro["id"]), None)
        if anterior is not None:
            return anterior[campo_respuestas] == registro[campo_respuestas]
        if _actualizar(database, estado, {f"expediente.{campo}": [*registros, registro]}):
            return True
    raise PyMongoError("El expediente se modificó en otra operación.")


def save_psych_report(database, user_id, campo, registro, intervalo):
    for _ in range(8):
        estado = _estado(database, user_id)
        if estado is None:
            return False
        registros = estado["expediente"].get(campo, [])
        if any(r["id"] == registro["id"] for r in registros):
            return False
        disponible = proximo_registro(registros, intervalo)
        if disponible is not None and fecha_utc(registro["fecha_hora"]) < disponible:
            raise RegistroPrematuro(disponible)
        if _actualizar(database, estado, {f"expediente.{campo}": [*registros, registro]}):
            return True
    raise PyMongoError("El expediente se modificó en otra operación.")


def save_psych_followup(database, user_id, campo, registro_id, seguimiento):
    resultado = database.usuarios.update_one(
        {"_id": user_id, f"expediente.{campo}": {"$elemMatch": {"id": registro_id, "seguimiento_ia": None}}},
        {"$set": {f"expediente.{campo}.$.seguimiento_ia": seguimiento}, "$inc": {"revision_expediente": 1}},
    )
    return bool(resultado.matched_count)


def psych_chat(database, user_id):
    conversacion = database.chat_psicologico.find_one({"_id": user_id})
    return (conversacion["revision"], conversacion["mensajes"]) if conversacion else (0, [])


def save_psych_chat(database, user_id, revision, mensajes):
    if revision == 0:
        try:
            database.chat_psicologico.insert_one({"_id": user_id, "revision": 1, "mensajes": mensajes})
        except DuplicateKeyError:
            return False
        return True
    resultado = database.chat_psicologico.update_one(
        {"_id": user_id, "revision": revision}, {"$set": {"mensajes": mensajes}, "$inc": {"revision": 1}},
    )
    return bool(resultado.matched_count)


def open_checkup(database, user_id, profile, greeting):
    try:
        database.monitoreos.insert_one({
            "_id": uuid4().hex, "user_id": user_id, "profile": profile,
            "borrador_de": f"{user_id}:{profile}",
            "revision": 0, "messages": [greeting], "details": {},
            "hr": 0, "spo2": 0, "temp": 0, "status": None, "finished_at": None,
        })
    except DuplicateKeyError:
        # Dos solicitudes pueden intentar crear el mismo borrador.
        if database.monitoreos.find_one({"user_id": user_id, "profile": profile, "finished_at": None}, {"_id": 1}) is None:
            raise


def _fila_chequeo(documento):
    return {
        **documento, "id": documento["_id"], "messages": json.dumps(documento["messages"], ensure_ascii=False),
        "details": json.dumps(documento["details"], ensure_ascii=False),
    }


def get_open_checkup(database, user_id, profile):
    documento = database.monitoreos.find_one({"user_id": user_id, "profile": profile, "finished_at": None})
    return _fila_chequeo(documento) if documento else None


def save_turn(database, draft, messages, vitals, details, status=None):
    finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds") if status else None
    if finished_at:
        details = {**details, "expediente_chequeo_id": f"chequeo-{draft['id']}"}
    cambios = dict(zip(("hr", "spo2", "temp"), vitals))
    cambios.update(messages=messages, details=details, status=status, finished_at=finished_at)
    actualizacion = {"$set": cambios, "$inc": {"revision": 1}}
    if finished_at:
        actualizacion["$unset"] = {"borrador_de": ""}
    resultado = database.monitoreos.update_one(
        {"_id": draft["id"], "user_id": draft["user_id"], "revision": draft["revision"], "finished_at": None},
        actualizacion,
    )
    return bool(resultado.matched_count)


def history(database, user_id, profile):
    documentos = database.monitoreos.find({"user_id": user_id, "profile": profile, "finished_at": {"$ne": None}})
    return [_fila_chequeo(documento) for documento in documentos.sort("finished_at", -1)]


@contextmanager
def expediente_para_archivo(database, user_id):
    expediente = expediente_for_user(database, user_id)
    yield expediente, history(database, user_id, expediente["_id"]) if expediente else []
