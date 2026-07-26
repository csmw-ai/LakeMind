import sqlite3
conn = sqlite3.connect('/data/meeting-agent.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
tid = 'meeting-6f2f2057bc8f'
c.execute('SELECT COUNT(*) as n FROM meeting_audio_chunks WHERE task_id = ?', (tid,))
print('chunks:', c.fetchone()['n'])
c.execute('SELECT asr_status, COUNT(*) as n FROM meeting_audio_chunks WHERE task_id = ? GROUP BY asr_status', (tid,))
for r in c.fetchall():
    print(f'  {r["asr_status"]}: {r["n"]}')
c.execute('SELECT COUNT(*) as n FROM meeting_transcript_segments WHERE task_id = ?', (tid,))
print('segments:', c.fetchone()['n'])
c.execute('SELECT COUNT(*) as n FROM meeting_minutes_versions WHERE task_id = ?', (tid,))
print('minutes:', c.fetchone()['n'])
c.execute('SELECT COUNT(*) as n FROM meeting_knowledge_items WHERE task_id = ?', (tid,))
print('knowledge:', c.fetchone()['n'])
c.execute("SELECT stage, status FROM meeting_stage_runs WHERE task_id = ? AND stage != 'asr' ORDER BY created_at DESC LIMIT 10", (tid,))
print('non-asr stages:')
for r in c.fetchall():
    print(f'  {r["stage"]} {r["status"]}')
