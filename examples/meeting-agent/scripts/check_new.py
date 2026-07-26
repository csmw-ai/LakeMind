import sqlite3
conn = sqlite3.connect('/data/meeting-agent.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
tid = 'meeting-0ef2f11b588f'
c.execute(f"SELECT COUNT(*) as n FROM meeting_audio_chunks WHERE task_id = ?", (tid,))
print('chunks:', c.fetchone()['n'])
c.execute(f"SELECT asr_status, COUNT(*) as n FROM meeting_audio_chunks WHERE task_id = ? GROUP BY asr_status", (tid,))
for r in c.fetchall():
    print(f"  {r['asr_status']}: {r['n']}")
c.execute(f"SELECT COUNT(*) as n FROM meeting_transcript_segments WHERE task_id = ?", (tid,))
print('transcript segments:', c.fetchone()['n'])
c.execute(f"SELECT COUNT(*) as n FROM meeting_minutes_versions WHERE task_id = ?", (tid,))
print('minutes versions:', c.fetchone()['n'])
c.execute(f"SELECT COUNT(*) as n FROM meeting_knowledge_items WHERE task_id = ?", (tid,))
print('knowledge items:', c.fetchone()['n'])
