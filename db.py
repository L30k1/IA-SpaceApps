import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from database.expedientes import SIGNOS, fecha_utc


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


def update_password(path, user_id, password_hash):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


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
    return {
        **{field: details.get(field) or None for field in ("mision_id", "fase", "motivo", "actividad")},
        "id": record_id,
        "fecha_hora": fecha.isoformat(),
        "resultado_simulador": status,
        "mediciones": [
            {"tipo": tipo, "valor": valor, "unidad": unidad}
            for (tipo, (_, unidad)), valor in zip(SIGNOS.items(), vitals)
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
