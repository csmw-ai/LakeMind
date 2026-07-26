import requests, hashlib, struct, wave, io, time, json

BASE = "http://localhost:9100/api"

# Login
r = requests.post(f"{BASE}/auth/login", json={"username": "userA_e2e", "password": "userApassword123"})
cookies = r.cookies
print("Login:", r.status_code)

# Create task
r = requests.post(f"{BASE}/tasks", cookies=cookies, json={
    "title": "ASR Debug Test", "participants": ["A"], "source_type": "LIVE",
    "template_id": None, "template_snapshot": {},
})
task_id = r.json()["task_id"]
print("Task:", task_id)

# Start recording
requests.post(f"{BASE}/tasks/{task_id}/start", cookies=cookies)

# Generate a real WAV with some audio data (tone, not silence)
buf = io.BytesIO()
with wave.open(buf, "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    # Generate 3 seconds of audio with varying amplitude (not pure silence)
    samples = []
    for i in range(16000 * 3):
        import math
        val = int(8000 * math.sin(2 * math.pi * 440 * i / 16000))
        samples.append(val)
    w.writeframes(struct.pack("<" + "h" * len(samples), *samples))
audio = buf.getvalue()
checksum = hashlib.sha256(audio).hexdigest()
print(f"Audio: {len(audio)} bytes, checksum: {checksum[:16]}...")

# Upload chunk
r = requests.put(f"{BASE}/tasks/{task_id}/audio/chunks/1", cookies=cookies, data=audio,
    headers={"Content-Type": "audio/wav", "X-Chunk-Checksum": checksum, "X-Chunk-Duration-Ms": "3000"})
print("Chunk upload:", r.status_code, r.json())

# Wait for ASR to process (check every 3s for up to 120s)
for i in range(40):
    time.sleep(3)
    r = requests.get(f"{BASE}/tasks/{task_id}/transcript", cookies=cookies)
    segs = r.json().get("segments", [])
    r2 = requests.get(f"{BASE}/tasks/{task_id}", cookies=cookies)
    status = r2.json()["status"]
    err = r2.json().get("error_message", "")
    print(f"  [{i*3}s] status={status} segments={len(segs)} err={err[:80] if err else 'none'}")
    if segs or status in ("FAILED", "REVIEW_REQUIRED", "COMPLETED"):
        break

# Check final transcript
r = requests.get(f"{BASE}/tasks/{task_id}/transcript", cookies=cookies)
segs = r.json().get("segments", [])
print(f"\nFinal transcript: {len(segs)} segments")
for s in segs:
    print(f"  seg: {s.get('original_text', '')[:100]}")

# Cleanup
requests.delete(f"{BASE}/tasks/{task_id}", cookies=cookies)
