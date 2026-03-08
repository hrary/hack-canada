import sqlite3

conn = sqlite3.connect("tariffs.db")
conn.row_factory = sqlite3.Row

tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)

for tname in tables:
    cols = conn.execute(f"PRAGMA table_info({tname})").fetchall()
    print(f"\n=== {tname} ===")
    print("Columns:", [(c["name"], c["type"]) for c in cols])
    count = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
    print(f"Rows: {count}")
    sample = conn.execute(f"SELECT * FROM {tname} LIMIT 5").fetchall()
    for s in sample:
        print(dict(s))

conn.close()
