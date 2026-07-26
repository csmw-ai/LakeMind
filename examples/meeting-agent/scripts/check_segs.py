import sqlite3
conn = sqlite3.connect('/data/meeting-agent.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
tid = 'meeting-0ef2f11b588f'
c.execute("SELECT segment_id, chunk_sequence, original_text, start_ms, end_ms FROM meeting_transcript_segments WHERE task_id = ? ORDER BY chunk_sequence", (tid,))
print("transcript segments:")
for r in c.fetchall():
    print(f"  seq={r['chunk_sequence']} [{r['start_ms']}-{r['end_ms']}ms] text={r['original_text'][:100]}")
