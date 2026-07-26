import sqlite3, json
conn = sqlite3.connect('/data/meeting-agent.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
tid = 'meeting-f50ab11849e8'
c.execute("SELECT * FROM meeting_tasks WHERE task_id = ?", (tid,))
r = c.fetchone()
if r:
    print("task:", dict(r))
else:
    print("task NOT FOUND")
c.execute("SELECT COUNT(*) as n FROM meeting_audio_chunks WHERE task_id = ?", (tid,))
print("chunks:", c.fetchone()['n'])
c.execute("SELECT COUNT(*) as n FROM meeting_transcript_segments WHERE task_id = ?", (tid,))
print("segments:", c.fetchone()['n'])
c.execute("SELECT COUNT(*) as n FROM meeting_minutes_versions WHERE task_id = ?", (tid,))
print("minutes:", c.fetchone()['n'])
c.execute("SELECT COUNT(*) as n FROM meeting_knowledge_items WHERE task_id = ?", (tid,))
print("knowledge:", c.fetchone()['n'])
