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
                hr INTEGER NOT NULL DEFAULT 62,
                spo2 INTEGER NOT NULL DEFAULT 99,
                temp REAL NOT NULL DEFAULT 36.6,
                status TEXT,
                finished_at TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS open_checkup
            ON checkups (user_id, profile) WHERE finished_at IS NULL;
        """)


def create_user(path, email, name, password_hash):
    with closing(sqlite3.connect(path)) as db, db:
        return db.execute(
            "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
            (email, name, password_hash),
        ).lastrowid


def find_user(path, email):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        return db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def open_checkup(path, user_id, profile, greeting):
    with closing(sqlite3.connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute(
            "INSERT INTO checkups (user_id, profile, messages) VALUES (?, ?, ?) "
            "ON CONFLICT (user_id, profile) WHERE finished_at IS NULL DO NOTHING",
            (user_id, profile, json.dumps([greeting])),
        )
        return db.execute(
            "SELECT * FROM checkups WHERE user_id = ? AND profile = ? AND finished_at IS NULL",
            (user_id, profile),
        ).fetchone()


def save_turn(path, draft, messages, vitals, status=None):
    finished_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC") if status else None
    with closing(sqlite3.connect(path)) as db, db:
        result = db.execute(
            "UPDATE checkups SET messages = ?, hr = ?, spo2 = ?, temp = ?, "
            "status = ?, finished_at = ?, revision = revision + 1 "
            "WHERE id = ? AND revision = ? AND finished_at IS NULL",
            (json.dumps(messages), *vitals, status, finished_at, draft["id"], draft["revision"]),
        )
        return result.rowcount == 1


def history(path, user_id, profile):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        return db.execute(
            "SELECT * FROM checkups WHERE user_id = ? AND profile = ? AND finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 20",
            (user_id, profile),
        ).fetchall()
