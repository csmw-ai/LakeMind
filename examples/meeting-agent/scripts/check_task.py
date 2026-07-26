import sqlite3
conn = sqlite3.connect('/data/meeting-agent.db')
c = conn.cursor()
c.execute("SELECT task_id, status FROM meeting_tasks WHERE task_id = 'meeting-903d184f8ebc'")
r = c.fetchall()
print('task exists:', len(r) > 0, r)
c.execute("SELECT COUNT(*) FROM meeting_audio_chunks WHERE task_id = 'meeting-903d184f8ebc'")
print('chunks:', c.fetchone()[0])
