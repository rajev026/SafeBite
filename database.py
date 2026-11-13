"""SQLite storage: one table for user profiles, one for scan history."""
import json
import sqlite3
from config import DB_PATH


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                age INTEGER,
                email TEXT,
                diseases TEXT DEFAULT '[]',
                allergens TEXT DEFAULT '[]',
                ec_name TEXT, ec_phone TEXT, ec_email TEXT,
                created TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kind TEXT, label TEXT, status TEXT,
                allergens_found TEXT DEFAULT '[]',
                created TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def save_user(data, user_id=None):
    vals = (
        data["name"], data["age"], data["email"],
        json.dumps(data["diseases"]), json.dumps(data["allergens"]),
        data["ec_name"], data["ec_phone"], data["ec_email"],
    )
    with get_db() as db:
        if user_id:
            db.execute(
                """UPDATE users SET name=?, age=?, email=?, diseases=?, allergens=?,
                   ec_name=?, ec_phone=?, ec_email=? WHERE id=?""",
                vals + (user_id,),
            )
            return user_id
        cur = db.execute(
            """INSERT INTO users (name, age, email, diseases, allergens,
               ec_name, ec_phone, ec_email) VALUES (?,?,?,?,?,?,?,?)""",
            vals,
        )
        return cur.lastrowid


def get_user(user_id):
    if not user_id:
        return None
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        return None
    u = dict(row)
    u["diseases"] = json.loads(u["diseases"] or "[]")
    u["allergens"] = json.loads(u["allergens"] or "[]")
    return u


def add_scan(user_id, kind, label, status, allergens_found):
    with get_db() as db:
        db.execute(
            "INSERT INTO scans (user_id, kind, label, status, allergens_found) VALUES (?,?,?,?,?)",
            (user_id, kind, label[:120], status, json.dumps(allergens_found)),
        )


def recent_flagged_scans(user_id, limit=5):
    """Latest scans that contained one of the user's allergens (used by SOS)."""
    with get_db() as db:
        rows = db.execute(
            """SELECT label, status, allergens_found, created FROM scans
               WHERE user_id=? AND allergens_found != '[]'
               ORDER BY id DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["allergens_found"] = json.loads(d["allergens_found"])
        out.append(d)
    return out


def recent_scans(user_id, limit=30):
    """Scan history for the History panel."""
    with get_db() as db:
        rows = db.execute(
            "SELECT kind, label, status, allergens_found, created FROM scans "
            "WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["allergens_found"] = json.loads(d["allergens_found"])
        out.append(d)
    return out


def clear_scans(user_id):
    with get_db() as db:
        db.execute("DELETE FROM scans WHERE user_id=?", (user_id,))
