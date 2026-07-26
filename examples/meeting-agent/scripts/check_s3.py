import requests, base64, hashlib

SERVER_URL = "http://localhost:10823"
SERVER_KEY = "ljLH3bvzIFjG4r3zeCP6AsHsGEnbmAQY_Hi3dW7du5o"

uri = "s3://lakemind-filesets/examples-meeting-agent/users/prn_01KXRBJ03NR21A6MFTBJHF8WTD/meetings/meeting-85355b009915/audio/chunks/000067.webm"
from urllib.parse import urlparse
p = urlparse(uri)
url = f"{SERVER_URL}/api/v1/storage/objects/{p.netloc}/{p.path.lstrip('/')}"

r = requests.get(url, headers={"Authorization": f"Bearer {SERVER_KEY}"})
print(f"Download: {r.status_code}, size={len(r.content)}")
print(f"First 40 bytes hex: {r.content[:40].hex()}")
print(f"First 40 chars: {r.content[:40]}")

try:
    decoded = base64.b64decode(r.content)
    print(f"\nBase64 decoded: size={len(decoded)}")
    print(f"First 20 bytes hex: {decoded[:20].hex()}")
    print(f"Is WebM: {decoded[:4] == bytes([0x1a, 0x45, 0xdf, 0xa3])}")
except Exception as e:
    print(f"Base64 decode failed: {e}")
