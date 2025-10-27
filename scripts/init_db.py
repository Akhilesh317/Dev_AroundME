import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_DIR = ROOT / "db"
DB_PATH = DB_DIR / "chat.db"
SCHEMA_PATH = DB_DIR / "schema.sql"

def main():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema not found at {SCHEMA_PATH}")

    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    # Connect and apply schema
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA foreign_keys = ON;")
        con.executescript(sql)
        con.commit()
    finally:
        con.close()

    print(f"✅ SQLite initialized at {DB_PATH}")

if __name__ == "__main__":
    main()
