import sqlite3
conn = sqlite3.connect('/data/meeting-agent.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("tables:", tables)
c.execute('SELECT COUNT(*) as n FROM meeting_transcript_segments')
print('transcript segments:', c.fetchone()['n'])
c.execute('PRAGMA table_info(meeting_audio_chunks)')
print('audio_chunks cols:', [r[1] for r in c.fetchall()])
c.execute('SELECT * FROM meeting_audio_chunks ORDER BY sequence_no DESC LIMIT 5')
print('recent chunks:')
for r in c.fetchall():
    print(dict(r))
c.execute('SELECT stage, status, job_id, error_message FROM meeting_stage_runs ORDER BY created_at DESC LIMIT 10')
print('recent stage runs:')
for r in c.fetchall():
    print(dict(r))
