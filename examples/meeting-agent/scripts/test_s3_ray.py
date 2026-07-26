import requests, base64, hashlib, struct, wave, io

SERVER_URL = "http://localhost:10823"
SERVER_KEY = "ljLH3bvzIFjG4r3zeCP6AsHsGEnbmAQY_Hi3dW7du5o"
BASE = "http://localhost:9100/api"

# Login
r = requests.post(f"{BASE}/auth/login", json={"username": "userA_e2e", "password": "userApassword123"})
cookies = r.cookies

# Create task + upload WAV
r = requests.post(f"{BASE}/tasks", cookies=cookies, json={
    "title": "S3 Verify", "participants": ["A"], "source_type": "LIVE",
    "template_id": None, "template_snapshot": {},
})
task_id = r.json()["task_id"]
requests.post(f"{BASE}/tasks/{task_id}/start", cookies=cookies)

buf = io.BytesIO()
with wave.open(buf, "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(struct.pack("<" + "h" * 16000, *([1000] * 16000)))
audio = buf.getvalue()
checksum = hashlib.sha256(audio).hexdigest()
requests.put(f"{BASE}/tasks/{task_id}/audio/chunks/1", cookies=cookies, data=audio,
    headers={"Content-Type": "audio/wav", "X-Chunk-Checksum": checksum, "X-Chunk-Duration-Ms": "1000"})

# Get the actual S3 URI from meeting-agent's DB
import subprocess
result = subprocess.run(
    ["docker", "exec", "meeting-agent", "python", "-c",
     "import sqlite3; c=sqlite3.connect('/data/meeting-agent.db'); r=c.execute('SELECT object_uri FROM meeting_audio_chunks ORDER BY created_at DESC LIMIT 1').fetchone(); print(r[0] if r else 'none')"],
    capture_output=True, text=True, shell=True
)
chunk_uri = result.stdout.strip()
print(f"Chunk URI: {chunk_uri}")

# Now simulate what the Ray job does: download from Server REST API
from urllib.parse import urlparse
p = urlparse(chunk_uri)
url = f"{SERVER_URL}/api/v1/storage/objects/{p.netloc}/{p.path.lstrip('/')}"
r = requests.get(url, headers={"Authorization": f"Bearer {SERVER_KEY}"})
print(f"Server download: {r.status_code}, size={len(r.content)}")
print(f"First 20 hex: {r.content[:20].hex()}")
print(f"Is base64 text: {r.content[:4] == b'UklG' or r.content[:4] == b'RIFF'}")

# Try base64 decode (what lakemind_utils.py does)
try:
    decoded = base64.b64decode(r.content)
    print(f"Base64 decoded: size={len(decoded)}, RIFF={decoded[:4]}, matches original={decoded == audio}")
except Exception as e:
    print(f"Base64 decode failed: {e}")
    # Maybe it's already raw binary
    print(f"Raw content RIFF: {r.content[:4]}, matches original={r.content == audio}")

# Now test: send the decoded audio to ModelServing ASR
if 'decoded' in dir():
    test_audio = decoded
else:
    test_audio = r.content

r2 = requests.post("http://localhost:10824/v1/audio/transcriptions",
    headers={"Authorization": "Bearer lakemind-modelserving-key"},
    files={"file": ("audio.wav", test_audio, "audio/wav")},
    timeout=30)
print(f"\nASR result: {r2.status_code} {r2.text[:200]}")

requests.delete(f"{BASE}/tasks/{task_id}", cookies=cookies)
