import sqlite3
conn = sqlite3.connect('/data/meeting-agent.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT task_id, title, status, started_at, stopped_at FROM meeting_tasks ORDER BY created_at DESC LIMIT 5")
print("tasks:")
for r in c.fetchall():
    print(dict(r))
c.execute("SELECT COUNT(*) as n, MAX(sequence_no) as max_seq FROM meeting_audio_chunks WHERE task_id = 'meeting-903d184f8ebc'")
r = c.fetchone()
print(f"\nchunks: count={r['n']}, max_seq={r['max_seq']}")
c.execute("SELECT COUNT(*) as n FROM meeting_audio_chunks WHERE task_id = 'meeting-903d184f8ebc' AND asr_status = 'RUNNING'")
print(f"asr RUNNING: {c.fetchone()['n']}")
c.execute("SELECT COUNT(*) as n FROM meeting_audio_chunks WHERE task_id = 'meeting-903d184f8ebc' AND asr_status = 'FAILED'")
print(f"asr FAILED: {c.fetchone()['n']}")
c.execute("SELECT COUNT(*) as n FROM meeting_audio_chunks WHERE task_id = 'meeting-903d184f8ebc' AND asr_status = 'SUCCEEDED'")
print(f"asr SUCCEEDED: {c.fetchone()['n']}")
