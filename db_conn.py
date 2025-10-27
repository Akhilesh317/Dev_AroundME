"""
Lightweight SQLite connection helper for AroundMe.

Usage:
    from db_conn import get_conn
    con = get_conn()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM conversations")
"""

import sqlite3
from pathlib import Path
from typing import Iterator, Optional

# Path to db/chat.db regardless of where this file is run from
DB_PATH = (Path(__file__).resolve().parent / "db" / "chat.db").resolve()

def get_conn() -> sqlite3.Connection:
    """Return a SQLite3 connection with Row factory and foreign keys on."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    return con

def ensure_ok() -> None:
    """Quick sanity check—raises if tables are missing."""
    with get_conn() as con:
        cur = con.cursor()
        need = {"conversations", "messages", "tool_calls"}
        have = {r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        missing = need - have
        if missing:
            raise RuntimeError(f"Missing tables: {missing}")

# Simple CLI test
if __name__ == "__main__":
    try:
        ensure_ok()
        with get_conn() as con:
            cur = con.cursor()
            counts = {}
            for t in ("conversations", "messages", "tool_calls"):
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                counts[t] = cur.fetchone()[0]
        print(f"✅ DB OK at {DB_PATH}")
        print("Counts:", counts)
    except Exception as e:
        print("❌ DB check failed:", e)
        raise
