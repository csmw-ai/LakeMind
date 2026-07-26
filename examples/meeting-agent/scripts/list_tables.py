import sqlite3
conn = sqlite3.connect('/data/meeting.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("tables:", [r[0] for r in c.fetchall()])
