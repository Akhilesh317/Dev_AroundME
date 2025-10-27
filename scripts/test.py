import sqlite3
con = sqlite3.connect("db/chat.db")
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("tables:", tables)
for t in ("conversations","messages","tool_calls"):
    cur.execute("PRAGMA table_info(%s)" % t)
    cols = [r[1] for r in cur.fetchall()]
    print(f"{t} columns:", cols)
con.close()
