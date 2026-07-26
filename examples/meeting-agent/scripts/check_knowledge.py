import sqlite3, json
conn = sqlite3.connect('/data/meeting-agent.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
tid = 'meeting-0ef2f11b588f'

c.execute("SELECT item_id, item_type, title, body, tags, confidence, review_status FROM meeting_knowledge_items WHERE task_id = ? ORDER BY created_at", (tid,))
print("=== KNOWLEDGE ITEMS ===")
for r in c.fetchall():
    tags = json.loads(r['tags']) if r['tags'] else []
    print(f"\n[{r['item_type']}] {r['title']}")
    print(f"  body: {r['body'][:150]}")
    print(f"  tags: {tags}  confidence: {r['confidence']}  status: {r['review_status']}")

c.execute("SELECT task_id, status FROM meeting_tasks WHERE task_id = ?", (tid,))
print(f"\n=== TASK STATUS: {dict(c.fetchone())} ===")
