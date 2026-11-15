import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from calendario_mision import fechas_mision
from database.expedientes import SIGNOS, fecha_utc
from volt import CAMPO_VOLT, ESPERA, EXPOSICION, FIGURAS, VERSION_VOLT, estimulos, puntuar


class RegistroPrematuro(Exception):
    def __init__(self, disponible):
        self.disponible = disponible
        super().__init__("El intervalo entre registros aún no ha terminado.")


def initialize(path):
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL
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
                mensajes TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS volt_drafts (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                contenido TEXT NOT NULL
            );
        """)


def create_user(path, email, name, password_hash, expediente, *, existing_user=None):
    with closing(sqlite3.connect(path)) as db, db:
        user_id = existing_user
        if user_id is None:
            user_id = db.execute(
                "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
                (email, name, password_hash),
            ).lastrowid
        db.execute(
            "INSERT INTO expedientes (user_id, astronauta_id, contenido) VALUES (?, ?, ?)",
            (user_id, expediente["_id"], json.dumps(expediente)),
        )
        return user_id


def expediente_for_user(path, user_id):
    with closing(sqlite3.connect(path)) as db:
        return read_expediente(db, user_id)


def read_expediente(db, user_id):
    row = db.execute("SELECT contenido FROM expedientes WHERE user_id = ?", (user_id,)).fetchone()
    return json.loads(row[0]) if row else None


def guardar_fechas_mision(path, usuario, identificador, fechas, crear):
    inicio, fin = fechas
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        expediente = read_expediente(db, usuario)
        if expediente is None:
            raise ValueError("La cuenta no tiene un expediente activo.")
        misiones = expediente["misiones"]
        mision = next((m for m in misiones if m["id"] == identificador), None)
        if crear and mision is not None:
            raise ValueError("Ya hay una misión con ese identificador.")
        if not crear and mision is None:
            raise ValueError("La misión no figura en tu expediente.")
        for otra in misiones:
            periodo = fechas_mision(otra)
            if otra is not mision and periodo and inicio <= periodo[1] and periodo[0] <= fin:
                raise ValueError("Las fechas se superponen con otra misión de tu expediente.")
        if mision is None:
            mision = {"id": identificador}
            misiones.append(mision)
        mision.update(fecha_inicio=inicio.isoformat(), fecha_fin=fin.isoformat())
        db.execute("UPDATE expedientes SET contenido = ? WHERE user_id = ?",
                   (json.dumps(expediente, ensure_ascii=False), usuario))


def read_volt_draft(db, user_id):
    row = db.execute("SELECT contenido FROM volt_drafts WHERE user_id = ?", (user_id,)).fetchone()
    return json.loads(row[0]) if row else None


def volt_draft(path, user_id):
    with closing(sqlite3.connect(path)) as db:
        return read_volt_draft(db, user_id)


def actualizar_volt(path, user_id, accion, identificador, respuestas, ahora):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        expediente = read_expediente(db, user_id)
        borrador = read_volt_draft(db, user_id)
        if expediente is None:
            raise ValueError("La cuenta no tiene un expediente activo.")
        if accion == "iniciar":
            if borrador is None:
                db.execute("INSERT INTO volt_drafts VALUES (?, ?)", (user_id, json.dumps({
                    "id": uuid4().hex, "fase": "aprendizaje", "inicio": ahora.isoformat(),
                })))
            return None

        registros = expediente.get(CAMPO_VOLT, [])
        if accion == "diferido" and any(r["id"] == identificador for r in registros):
            return identificador
        if borrador is None or borrador["id"] != identificador:
            raise ValueError("Esta prueba ya no está activa. Vuelve a la página de memoria visual.")
        fase = borrador["fase"]
        if accion == "cancelar":
            db.execute("DELETE FROM volt_drafts WHERE user_id = ?", (user_id,))
            return None

        if accion == "inmediato":
            if fase != "aprendizaje":
                return None
            if (ahora - fecha_utc(borrador["inicio"])).total_seconds() < FIGURAS * EXPOSICION:
                raise ValueError("Completa primero la fase de aprendizaje.")
            borrador.update(
                fase="espera", inmediato=puntuar(respuestas, estimulos(identificador)[1]),
                fin_inmediato=ahora.isoformat(),
            )
        elif accion == "abrir_diferido":
            if fase == "diferido":
                return None
            if fase != "espera" or ahora < fecha_utc(borrador["fin_inmediato"]) + ESPERA:
                raise ValueError("Aún no termina el intervalo de 15 minutos.")
            borrador.update(fase="diferido", inicio_diferido=ahora.isoformat())
        elif accion == "diferido" and fase == "diferido":
            registro = {
                "id": identificador, "version": VERSION_VOLT, "fecha_hora": ahora.isoformat(),
                "intervalo_segundos": (fecha_utc(borrador["inicio_diferido"]) - fecha_utc(borrador["fin_inmediato"])).total_seconds(),
                "inmediato": borrador["inmediato"], "diferido": puntuar(respuestas, estimulos(identificador)[2]),
            }
            expediente[CAMPO_VOLT] = [*registros, registro]
            db.execute("UPDATE expedientes SET contenido = ? WHERE user_id = ?", (json.dumps(expediente, ensure_ascii=False), user_id))
            db.execute("DELETE FROM volt_drafts WHERE user_id = ?", (user_id,))
            return identificador
        else:
            raise ValueError("La fase solicitada no está disponible.")

        db.execute("UPDATE volt_drafts SET contenido = ? WHERE user_id = ?", (json.dumps(borrador), user_id))
        return None


def save_cognitive_report(path, user_id, campo, registro, campo_respuestas):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        expediente = read_expediente(db, user_id)
        if expediente is None:
            return False
        registros = expediente.setdefault(campo, [])
        for anterior in registros:
            if anterior["id"] == registro["id"]:
                return anterior[campo_respuestas] == registro[campo_respuestas]
        registros.append(registro)
        db.execute(
            "UPDATE expedientes SET contenido = ? WHERE user_id = ?",
            (json.dumps(expediente, ensure_ascii=False), user_id),
        )
        return True


def proximo_registro(registros, intervalo):
    ultimo = max((fecha_utc(registro["fecha_hora"]) for registro in registros), default=None)
    return ultimo + intervalo if ultimo is not None else None


def save_psych_report(path, user_id, campo, registro, intervalo):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        expediente = read_expediente(db, user_id)
        if expediente is None:
            return False
        registros = expediente.setdefault(campo, [])
        if any(previo["id"] == registro["id"] for previo in registros):
            return False
        disponible = proximo_registro(registros, intervalo)
        if disponible is not None and fecha_utc(registro["fecha_hora"]) < disponible:
            raise RegistroPrematuro(disponible)
        registros.append(registro)
        db.execute(
            "UPDATE expedientes SET contenido = ? WHERE user_id = ?",
            (json.dumps(expediente, ensure_ascii=False), user_id),
        )
        return True


def save_psych_followup(path, user_id, campo, registro_id, seguimiento):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        expediente = read_expediente(db, user_id)
        if expediente is None:
            return False
        for registro in expediente.get(campo, []):
            if registro["id"] == registro_id and not registro.get("seguimiento_ia"):
                registro["seguimiento_ia"] = seguimiento
                db.execute(
                    "UPDATE expedientes SET contenido = ? WHERE user_id = ?",
                    (json.dumps(expediente, ensure_ascii=False), user_id),
                )
                return True
        return False


def psych_chat(path, user_id):
    with closing(sqlite3.connect(path)) as db:
        row = db.execute("SELECT revision, mensajes FROM psych_chat WHERE user_id = ?", (user_id,)).fetchone()
        return (row[0], json.loads(row[1])) if row else (0, [])


def save_psych_chat(path, user_id, revision, mensajes):
    with closing(sqlite3.connect(path)) as db, db:
        contenido = json.dumps(mensajes, ensure_ascii=False)
        if revision == 0:
            actualizado = db.execute(
                "INSERT INTO psych_chat (user_id, revision, mensajes) VALUES (?, 1, ?) "
                "ON CONFLICT (user_id) DO NOTHING",
                (user_id, contenido),
            )
        else:
            actualizado = db.execute(
                "UPDATE psych_chat SET mensajes = ?, revision = revision + 1 "
                "WHERE user_id = ? AND revision = ?",
                (contenido, user_id, revision),
            )
        return actualizado.rowcount == 1


def find_user(path, email):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        return db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def find_user_by_astronauta(path, astronauta_id):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        return db.execute(
            "SELECT users.id, users.password_hash FROM expedientes "
            "JOIN users ON users.id = expedientes.user_id WHERE expedientes.astronauta_id = ?",
            (astronauta_id,),
        ).fetchone()


def open_checkup(path, user_id, profile, greeting):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(
            "INSERT INTO checkups (user_id, profile, messages, hr, spo2, temp) VALUES (?, ?, ?, 0, 0, 0) "
            "ON CONFLICT (user_id, profile) WHERE finished_at IS NULL DO NOTHING",
            (user_id, profile, json.dumps([greeting])),
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
        fecha = fecha_utc(finished_at)
    except ValueError:
        fecha = datetime.strptime(finished_at, "%d/%m/%Y %H:%M UTC").replace(tzinfo=timezone.utc)
    medidas = details.get("telemetria", dict(zip(("hr", "spo2", "temp"), vitals)))
    return {
        **{field: details.get(field) or None for field in ("mision_id", "fase", "motivo", "actividad")},
        "id": record_id,
        "fecha_hora": fecha.isoformat(),
        "resultado": status,
        "mediciones": [
            {"tipo": tipo, "valor": medidas[key], "unidad": SIGNOS[tipo][1]}
            for tipo, key in zip(SIGNOS, ("hr", "spo2", "temp")) if medidas[key] is not None
        ],
        "conversacion": messages,
        **{field: details[field] for field in ("evaluacion_ia", "evaluacion") if field in details},
    }


def save_turn(path, draft, messages, vitals, details, status=None):
    finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds") if status else None
    with closing(sqlite3.connect(path)) as db, db:
        result = db.execute(
            "UPDATE checkups SET messages = ?, hr = ?, spo2 = ?, temp = ?, "
            "status = ?, finished_at = ?, revision = revision + 1 "
            "WHERE id = ? AND revision = ? AND finished_at IS NULL",
            (json.dumps(messages), *vitals, status, finished_at, draft["id"], draft["revision"]),
        )
        if result.rowcount != 1:
            return False
        if finished_at:
            expediente_row = db.execute(
                "SELECT contenido FROM expedientes WHERE user_id = ? AND astronauta_id = ?",
                (draft["user_id"], draft["profile"]),
            ).fetchone()
            if expediente_row is None:
                raise ValueError("No se encontró el expediente del chequeo.")
            expediente = json.loads(expediente_row[0])
            record_id = f"chequeo-{uuid4().hex}"
            expediente["chequeos"].append(
                checkup_record(record_id, finished_at, messages, vitals, details, status)
            )
            db.execute(
                "UPDATE expedientes SET contenido = ? WHERE user_id = ?",
                (json.dumps(expediente, ensure_ascii=False), draft["user_id"]),
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
def expediente_para_archivo(path, user_id):
    with closing(sqlite3.connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        # Serializa la escritura de archivos con los cambios de SQLite.
        db.execute("BEGIN IMMEDIATE")
        expediente = read_expediente(db, user_id)
        if expediente is None:
            yield None, []
        else:
            yield expediente, read_history(db, user_id, expediente["_id"])
