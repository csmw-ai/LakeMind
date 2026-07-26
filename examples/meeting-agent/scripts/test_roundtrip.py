import requests, base64, hashlib, struct, wave, io, json

BASE = "http://localhost:9100/api"
SERVER_URL = "http://localhost:10823"
SERVER_KEY = "ljLH3bvzIFjG4r3zeCP6AsHsGEnbmAQY_Hi3dW7du5o"

# Login
r = requests.post(f"{BASE}/auth/login", json={"username": "userA_e2e", "password": "userApassword123"})
cookies = r.cookies

# Create task
r = requests.post(f"{BASE}/tasks", cookies=cookies, json={
    "title": "Round-trip Test", "participants": ["A"], "source_type": "LIVE",
    "template_id": None, "template_snapshot": {},
})
task_id = r.json()["task_id"]
print(f"Task: {task_id}")

# Start
requests.post(f"{BASE}/tasks/{task_id}/start", cookies=cookies)

# Generate WAV
buf = io.BytesIO()
with wave.open(buf, "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    w.writeframes(struct.pack("<" + "h" * 16000, *([1000] * 16000)))
audio = buf.getvalue()
checksum = hashlib.sha256(audio).hexdigest()
print(f"Original WAV: {len(audio)} bytes, sha256={checksum[:16]}..., RIFF={audio[:4]}")

# Upload
r = requests.put(f"{BASE}/tasks/{task_id}/audio/chunks/1", cookies=cookies, data=audio,
    headers={"Content-Type": "audio/wav", "X-Chunk-Checksum": checksum, "X-Chunk-Duration-Ms": "1000"})
print(f"Upload: {r.status_code}")

# Download directly from Server (bypass MCP)
from urllib.parse import urlparse
uri = f"s3://lakemind-filesets/examples-meeting-agent/users/{r.json().get('chunk_id','')}/meetings/{task_id}/audio/chunks/000001.wav"
# Get the actual URI from DB
r2 = requests.get(f"{BASE}/tasks/{task_id}/audio/manifest", cookies=cookies)
chunks = r2.json().get("chunks", [])
print(f"Manifest chunks: {len(chunks)}")

# Download chunk via meeting-agent API
r3 = requests.get(f"{BASE}/tasks/{task_id}/audio/chunks/1", cookies=cookies)
print(f"Download via API: {r3.status_code}, size={len(r3.content)}, RIFF={r3.content[:4]}")
print(f"Same as original: {r3.content == audio}")

# Also check: download directly from Server
r4 = requests.get(
    f"{SERVER_URL}/api/v1/storage/objects/lakemind-filesets/examples-meeting-agent/users",
    headers={"Authorization": f"Bearer {SERVER_KEY}"})
# The URI stored in DB has the real path
# Let's get it from the meeting-agent container
import subprocess
result = subprocess.run(
    ["docker", "exec", "meeting-agent", "python", "-c",
     f"import sqlite3; conn=sqlite3.connect('/data/meeting-agent.db'); r=conn.execute('SELECT object_uri FROM meeting_audio_chunks WHERE task_id=?',(task_id,)).fetchone(); print(r[0] if r else 'none')"],
    capture_output=True, text=True
)

# Cleanup
requests.delete(f"{BASE}/tasks/{task_id}", cookies=cookies)
