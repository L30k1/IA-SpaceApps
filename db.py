import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone


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
        row = db.execute("SELECT contenido FROM expedientes WHERE user_id = ?", (user_id,)).fetchone()
        return json.loads(row[0]) if row else None


def find_user(path, email):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        return db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


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
        db.execute(
            "INSERT INTO checkup_details (checkup_id, contenido) VALUES (?, ?) "
            "ON CONFLICT (checkup_id) DO UPDATE SET contenido = excluded.contenido",
            (draft["id"], json.dumps(details)),
        )
        return True


def history(path, user_id, profile):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        return db.execute(
            "SELECT checkups.*, checkup_details.contenido AS details "
            "FROM checkups LEFT JOIN checkup_details ON checkup_id = checkups.id "
            "WHERE user_id = ? AND profile = ? AND finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 20",
            (user_id, profile),
        ).fetchall()
