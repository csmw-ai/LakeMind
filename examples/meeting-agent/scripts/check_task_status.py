import sqlite3
conn = sqlite3.connect('/data/meeting-agent.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
tid = 'meeting-0ef2f11b588f'
c.execute("SELECT task_id, status, started_at, stopped_at, duration_ms FROM meeting_tasks WHERE task_id = ?", (tid,))
print(dict(c.fetchone()))
