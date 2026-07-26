import sqlite3
conn = sqlite3.connect('/data/meeting-agent.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
tid = 'meeting-0ef2f11b588f'

c.execute("SELECT version, status, substr(content_markdown,1,500) as preview, created_at FROM meeting_minutes_versions WHERE task_id = ? ORDER BY version", (tid,))
print("=== MINUTES ===")
for r in c.fetchall():
    print(f"v{r['version']} ({r['status']}) @ {r['created_at']}")
    print(r['preview'])
    print("---")

c.execute("SELECT stage, status, job_id, error_message, started_at, finished_at FROM meeting_stage_runs WHERE task_id = ? ORDER BY created_at DESC LIMIT 15", (tid,))
print("\n=== STAGE RUNS (recent 15) ===")
for r in c.fetchall():
    print(f"  {r['stage']:20s} {r['status']:12s} job={r['job_id']}  err={str(r['error_message'])[:80] if r['error_message'] else ''}")

c.execute("SELECT COUNT(*) as n FROM meeting_transcript_segments WHERE task_id = ?", (tid,))
print(f"\ntranscript segments: {c.fetchone()['n']}")

c.execute("SELECT chunk_sequence, asr_status FROM meeting_audio_chunks WHERE task_id = ? AND asr_status = 'SUCCEEDED' ORDER BY chunk_sequence", (tid,))
rows = c.fetchall()
print(f"succeeded chunks: {len(rows)}, seqs: {[r['chunk_sequence'] for r in rows[:20]]}...")
