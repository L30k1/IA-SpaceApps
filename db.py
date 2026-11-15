import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from database.expedientes import SIGNOS, fecha_utc
from volt import CAMPO_VOLT, avanzar


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
        if "clave_edicion_hash" not in {columna[1] for columna in db.execute("PRAGMA table_info(users)")}:
            db.execute("ALTER TABLE users ADD COLUMN clave_edicion_hash TEXT")
        if "es_admin" not in {columna[1] for columna in db.execute("PRAGMA table_info(users)")}:
            db.execute("ALTER TABLE users ADD COLUMN es_admin INTEGER NOT NULL DEFAULT 0")
        if "inicio_visible" not in {columna[1] for columna in db.execute("PRAGMA table_info(psych_chat)")}:
            db.execute("ALTER TABLE psych_chat ADD COLUMN inicio_visible INTEGER NOT NULL DEFAULT 0")


def create_user(path, password_hash, expediente, clave_edicion_hash=None):
    with closing(sqlite3.connect(path)) as db, db:
        # Las sesiones existentes guardan el ID. Una cuenta nueva nunca debe reutilizarlo.
        user_id = db.execute(
            "UPDATE secuencia_usuarios SET ultimo = MAX(ultimo, (SELECT COALESCE(MAX(id), 0) FROM users)) + 1 "
            "WHERE id = 1 RETURNING ultimo"
        ).fetchone()[0]
        # La columna email es obligatoria en las bases SQLite existentes.
        db.execute(
            "INSERT INTO users (id, email, name, password_hash, clave_edicion_hash) VALUES (?, ?, ?, ?, ?)",
            (user_id, f"astronauta:{expediente['_id']}", expediente["astronauta"]["nombre"],
             password_hash, clave_edicion_hash),
        )
        db.execute(
            "INSERT INTO expedientes (user_id, astronauta_id, contenido) VALUES (?, ?, ?)",
            (user_id, expediente["_id"], json.dumps(expediente)),
        )
        return user_id


def credenciales_edicion(path, user_id):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        return db.execute("SELECT password_hash, clave_edicion_hash FROM users WHERE id = ?", (user_id,)).fetchone()


def configurar_llave_edicion(path, user_id, clave_hash):
    with closing(sqlite3.connect(path)) as db, db:
        resultado = db.execute(
            "UPDATE users SET clave_edicion_hash = ? WHERE id = ? AND clave_edicion_hash IS NULL",
            (clave_hash, user_id),
        )
        return resultado.rowcount == 1


def expediente_for_user(path, user_id):
    with closing(sqlite3.connect(path)) as db:
        return read_expediente(db, user_id)


def es_administrador(path, user_id):
    with closing(sqlite3.connect(path)) as db:
        return db.execute("SELECT 1 FROM users WHERE id = ? AND es_admin = 1", (user_id,)).fetchone() is not None


def cuentas_administracion(path, identificador, desplazamiento, limite):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        consulta = """
            SELECT users.id, users.name, users.email, users.es_admin, expedientes.astronauta_id
            FROM users LEFT JOIN expedientes ON expedientes.user_id = users.id
        """
        parametros = ()
        if identificador:
            consulta += " WHERE expedientes.astronauta_id = ?"
            parametros = (identificador,)
        return db.execute(consulta + " ORDER BY users.id DESC LIMIT ? OFFSET ?",
                          (*parametros, limite, desplazamiento)).fetchall()


def cuenta_administracion(path, user_id):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        fila = db.execute("""
            SELECT users.id, users.name, users.email, users.es_admin, expedientes.astronauta_id,
                   expedientes.contenido
            FROM users LEFT JOIN expedientes ON expedientes.user_id = users.id
            WHERE users.id = ?
        """, (user_id,)).fetchone()
        if fila is None:
            return None
        cuenta = dict(fila)
        cuenta["expediente"] = json.loads(cuenta.pop("contenido") or "null")
        return cuenta


def eliminar_cuenta(path, administrador, usuario):
    if type(usuario) is not int or administrador == usuario:
        return False
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute(
            "SELECT 1 FROM users WHERE id = ? AND es_admin = 1", (administrador,),
        ).fetchone() is None:
            return False
        db.execute("UPDATE secuencia_usuarios SET ultimo = MAX(ultimo, (SELECT MAX(id) FROM users)) WHERE id = 1")
        if db.execute("DELETE FROM users WHERE id = ?", (usuario,)).rowcount == 0:
            return False
        db.execute("DELETE FROM checkup_details WHERE checkup_id IN (SELECT id FROM checkups WHERE user_id = ?)",
                   (usuario,))
        for tabla in ("checkups", "psych_chat", "emergency_chat", "volt_drafts", "expedientes"):
            db.execute(f"DELETE FROM {tabla} WHERE user_id = ?", (usuario,))

        # Usa el mismo bloqueo de escritura que la exportación del expediente.
        carpeta = Path(f"{path}.expedientes").resolve() / str(usuario)
        if carpeta.resolve() != carpeta:
            raise OSError("La carpeta del expediente apunta fuera de la ruta esperada.")
        if carpeta.exists():
            rmtree(carpeta)
        return True


def actualizar_datos_expediente(path, user_id, aplicar):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        expediente = read_expediente(db, user_id)
        if expediente is None:
            return False
        actualizado = aplicar(expediente)
        db.execute("UPDATE expedientes SET contenido = ? WHERE user_id = ?",
                   (json.dumps(actualizado, ensure_ascii=False), user_id))
        return True


def read_expediente(db, user_id):
    row = db.execute("SELECT contenido FROM expedientes WHERE user_id = ?", (user_id,)).fetchone()
    return json.loads(row[0]) if row else None


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
        registros = expediente.get(CAMPO_VOLT, [])
        siguiente, registro, completado = avanzar(borrador, registros, accion, identificador, respuestas, ahora)
        if registro is not None:
            expediente[CAMPO_VOLT] = [*registros, registro]
            db.execute(
                "UPDATE expedientes SET contenido = ? WHERE user_id = ?",
                (json.dumps(expediente, ensure_ascii=False), user_id),
            )
        if siguiente is None:
            if borrador is not None:
                db.execute("DELETE FROM volt_drafts WHERE user_id = ?", (user_id,))
        elif siguiente is not borrador:
            db.execute(
                "INSERT INTO volt_drafts VALUES (?, ?) ON CONFLICT (user_id) DO UPDATE SET contenido = excluded.contenido",
                (user_id, json.dumps(siguiente)),
            )
        return completado


def save_expediente_report(path, user_id, campo, registro, *campos):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        expediente = read_expediente(db, user_id)
        if expediente is None:
            return False
        registros = expediente.setdefault(campo, [])
        for anterior in registros:
            if anterior["id"] == registro["id"]:
                return all(anterior.get(nombre) == registro.get(nombre) for nombre in campos)
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


def psych_chat(path, user_id, emergencia=False, *, incluir_archivo=False):
    tabla = "emergency_chat" if emergencia else "psych_chat"
    with closing(sqlite3.connect(path)) as db:
        row = db.execute(f"SELECT revision, mensajes, inicio_visible FROM {tabla} WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return 0, []
        return row[0], json.loads(row[1])[0 if incluir_archivo else row[2]:]


def save_psych_chat(path, user_id, revision, turnos, emergencia=False):
    tabla = "emergency_chat" if emergencia else "psych_chat"
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if revision == 0:
            actualizado = db.execute(
                f"INSERT INTO {tabla} (user_id, revision, mensajes) SELECT id, 1, ? FROM users WHERE id = ? "
                "ON CONFLICT (user_id) DO NOTHING",
                (json.dumps(turnos, ensure_ascii=False), user_id),
            )
        else:
            row = db.execute(f"SELECT mensajes FROM {tabla} WHERE user_id = ? AND revision = ?",
                             (user_id, revision)).fetchone()
            if row is None:
                return False
            contenido = json.dumps([*json.loads(row[0]), *turnos], ensure_ascii=False)
            actualizado = db.execute(
                f"UPDATE {tabla} SET mensajes = ?, revision = revision + 1 "
                "WHERE user_id = ? AND revision = ?",
                (contenido, user_id, revision),
            )
        return actualizado.rowcount == 1


def limpiar_psych_chat(path, user_id, revision):
    with closing(sqlite3.connect(path)) as db, db:
        actualizado = db.execute(
            "UPDATE psych_chat SET inicio_visible = json_array_length(mensajes), revision = revision + 1 "
            "WHERE user_id = ? AND revision = ?", (user_id, revision),
        )
        return actualizado.rowcount == 1


def find_user_by_astronauta(path, astronauta_id):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        return db.execute(
            "SELECT users.id, users.password_hash, "
            "COALESCE(json_extract(expedientes.contenido, '$.astronauta.nombre'), users.name) AS name FROM expedientes "
            "JOIN users ON users.id = expedientes.user_id WHERE expedientes.astronauta_id = ?",
            (astronauta_id,),
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
