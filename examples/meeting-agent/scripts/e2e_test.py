"""Golden Path E2E test for Meeting Agent v0.2.0"""
import hashlib
import json
import time
import requests

BASE = "http://localhost:9100/api"
results = []

def check(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    results.append((name, ok, detail))
    print(f"  [{status}] {name} {detail}")

def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()

print("=== Golden Path E2E Test ===\n")

# Step 1: Register user A
print("--- Step 1: Register userA ---")
r = requests.post(f"{BASE}/auth/register", json={
    "username": "userA_e2e", "password": "userApassword123", "display_name": "User A"
})
if r.status_code == 409:
    r = requests.post(f"{BASE}/auth/login", json={"username": "userA_e2e", "password": "userApassword123"})
    check("Login userA (existing)", r.status_code == 200, f"status={r.status_code}")
else:
    check("Register userA", r.status_code == 200, f"status={r.status_code}")
cookies_a = r.cookies

# Step 2: Get /auth/me
print("--- Step 2: Get /auth/me ---")
r = requests.get(f"{BASE}/auth/me", cookies=cookies_a)
check("auth/me userA", r.status_code == 200 and "principal_id" in r.json(), f"principal={r.json().get('principal_id','?')[:20]}")
principal_a = r.json()["principal_id"]

# Step 3: List templates
print("--- Step 3: List templates ---")
r = requests.get(f"{BASE}/templates", cookies=cookies_a)
templates = r.json().get("items", [])
check("List templates", len(templates) >= 5, f"count={len(templates)}")
template = templates[0] if templates else None

# Step 4: Create task
print("--- Step 4: Create task ---")
r = requests.post(f"{BASE}/tasks", cookies=cookies_a, json={
    "title": "E2E Test Meeting",
    "participants": ["Alice", "Bob"],
    "source_type": "LIVE",
    "template_id": template["template_id"] if template else None,
    "template_snapshot": template["config"] if template else {},
})
check("Create task", r.status_code == 200, f"status={r.status_code}")
task_id = r.json()["task_id"]
print(f"  task_id: {task_id}")

# Step 5: Start recording
print("--- Step 5: Start recording ---")
r = requests.post(f"{BASE}/tasks/{task_id}/start", cookies=cookies_a)
check("Start recording", r.status_code == 200, f"status={r.status_code}")

# Step 6: Upload audio chunks (simulate with dummy audio)
print("--- Step 6: Upload audio chunks ---")
import struct, wave, io
for seq in range(1, 4):
    buf = io.BytesIO()
    with wave.open(buf, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack('<' + 'h'*1600, *([1000]*1600)))
    audio = buf.getvalue()
    checksum = hashlib.sha256(audio).hexdigest()
    r = requests.put(
        f"{BASE}/tasks/{task_id}/audio/chunks/{seq}",
        cookies=cookies_a, data=audio,
        headers={"Content-Type": "audio/wav", "X-Chunk-Checksum": checksum, "X-Chunk-Duration-Ms": "1000"},
    )
    check(f"Upload chunk {seq}", r.status_code == 200, f"size={len(audio)}")

# Step 7: Idempotent re-upload (same sequence + checksum)
print("--- Step 7: Idempotent re-upload ---")
r = requests.put(
    f"{BASE}/tasks/{task_id}/audio/chunks/1",
    cookies=cookies_a, data=audio,
    headers={"Content-Type": "audio/wav", "X-Chunk-Checksum": checksum, "X-Chunk-Duration-Ms": "1000"},
)
check("Idempotent re-upload", r.status_code == 200 and r.json().get("duplicate") == True, f"duplicate={r.json().get('duplicate')}")

# Step 8: Conflict upload (same sequence, different checksum)
print("--- Step 8: Conflict upload ---")
fake_checksum = "0" * 64
r = requests.put(
    f"{BASE}/tasks/{task_id}/audio/chunks/1",
    cookies=cookies_a, data=b"different",
    headers={"Content-Type": "audio/wav", "X-Chunk-Checksum": fake_checksum, "X-Chunk-Duration-Ms": "1000"},
)
check("Conflict upload returns 409", r.status_code == 409, f"status={r.status_code}")

# Step 9: Get manifest
print("--- Step 9: Get manifest ---")
r = requests.get(f"{BASE}/tasks/{task_id}/audio/manifest", cookies=cookies_a)
check("Get manifest", r.status_code == 200 and len(r.json()["chunks"]) == 3, f"chunks={len(r.json()['chunks'])}")

# Step 10: Stop recording
print("--- Step 10: Stop recording ---")
r = requests.post(f"{BASE}/tasks/{task_id}/stop", cookies=cookies_a)
check("Stop recording", r.status_code == 200, f"status={r.status_code} {r.json()}")

# Step 11: Wait for processing
print("--- Step 11: Wait for processing ---")
for i in range(30):
    r = requests.get(f"{BASE}/tasks/{task_id}", cookies=cookies_a)
    status = r.json()["status"]
    if status in ("REVIEW_REQUIRED", "COMPLETED", "FAILED"):
        break
    time.sleep(2)
check("Processing completed", status in ("REVIEW_REQUIRED", "COMPLETED", "FAILED"), f"final_status={status}")

# Step 12: Get transcript
print("--- Step 12: Get transcript ---")
r = requests.get(f"{BASE}/tasks/{task_id}/transcript", cookies=cookies_a)
segments = r.json().get("segments", [])
check("Get transcript", r.status_code == 200, f"segments={len(segments)}")

# Step 13: Get minutes
print("--- Step 13: Get minutes ---")
r = requests.get(f"{BASE}/tasks/{task_id}/minutes", cookies=cookies_a)
versions = r.json().get("versions", [])
check("Get minutes", r.status_code == 200, f"versions={len(versions)}")

# Step 14: Get knowledge
print("--- Step 14: Get knowledge ---")
r = requests.get(f"{BASE}/tasks/{task_id}/knowledge", cookies=cookies_a)
items = r.json().get("items", [])
check("Get knowledge", r.status_code == 200, f"items={len(items)}")

# Step 15: Accept + publish knowledge (if any items)
print("--- Step 15: Accept + publish knowledge ---")
if items:
    item_id = items[0]["item_id"]
    r = requests.post(f"{BASE}/tasks/{task_id}/knowledge/{item_id}/accept", cookies=cookies_a)
    check("Accept knowledge item", r.status_code == 200, f"status={r.status_code}")
    r = requests.post(f"{BASE}/tasks/{task_id}/knowledge/publish", cookies=cookies_a)
    check("Publish knowledge", r.status_code == 200, f"published={len(r.json().get('published', []))}")
else:
    check("Accept + publish knowledge", True, "no items to publish (skipped)")

# === Security tests ===
print("\n=== Security Tests ===")

# Step 16: Register user B
print("--- Step 16: Register userB ---")
r = requests.post(f"{BASE}/auth/register", json={
    "username": "userB_e2e", "password": "userBpassword123", "display_name": "User B"
})
if r.status_code == 409:
    r = requests.post(f"{BASE}/auth/login", json={"username": "userB_e2e", "password": "userBpassword123"})
    check("Login userB (existing)", r.status_code == 200, f"status={r.status_code}")
else:
    check("Register userB", r.status_code == 200, f"status={r.status_code}")
cookies_b = r.cookies

# Step 17: User B cannot see user A's task
print("--- Step 17: User B isolation ---")
r = requests.get(f"{BASE}/tasks/{task_id}", cookies=cookies_b)
check("User B cannot see user A task", r.status_code == 404, f"status={r.status_code}")

r = requests.get(f"{BASE}/tasks", cookies=cookies_b)
b_tasks = r.json().get("items", [])
check("User B has no tasks from A", all(t["task_id"] != task_id for t in b_tasks), f"b_tasks={len(b_tasks)}")

# Step 18: User B cannot upload chunks to user A's task
print("--- Step 18: User B cannot access user A audio ---")
r = requests.put(
    f"{BASE}/tasks/{task_id}/audio/chunks/99",
    cookies=cookies_b, data=b"fake",
    headers={"Content-Type": "audio/wav", "X-Chunk-Checksum": "0"*64},
)
check("User B cannot upload to A task", r.status_code == 404, f"status={r.status_code}")

# Step 19: User B cannot get user A's transcript
r = requests.get(f"{BASE}/tasks/{task_id}/transcript", cookies=cookies_b)
check("User B cannot get A transcript", r.status_code == 404, f"status={r.status_code}")

# Step 20: Unauthenticated access
print("--- Step 20: Unauthenticated access ---")
r = requests.get(f"{BASE}/tasks/{task_id}")
check("Unauthenticated access denied", r.status_code == 401, f"status={r.status_code}")

# === Cleanup ===
print("\n=== Cleanup ===")
# Step 21: Delete task
print("--- Step 21: Delete task ---")
r = requests.delete(f"{BASE}/tasks/{task_id}", cookies=cookies_a)
check("Delete task", r.status_code == 200, f"status={r.status_code}")

r = requests.get(f"{BASE}/tasks/{task_id}", cookies=cookies_a)
check("Task deleted", r.status_code == 404, f"status={r.status_code}")

# === Summary ===
print("\n=== Summary ===")
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total = len(results)
print(f"Total: {total}, Passed: {passed}, Failed: {failed}")
if failed:
    print("\nFailed tests:")
    for name, ok, detail in results:
        if not ok:
            print(f"  - {name}: {detail}")
