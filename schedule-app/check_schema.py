import sqlite3, os
conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), 'schedule.db'))
for r in conn.execute('SELECT sql FROM sqlite_master WHERE type="table"').fetchall():
    print(r[0])
    print()
