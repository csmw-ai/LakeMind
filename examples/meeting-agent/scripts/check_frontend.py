import requests
r1 = requests.get("http://localhost:9100/")
print(f"index.html: {r1.status_code} ({len(r1.text)} bytes)")
# Find JS asset name
import re
js_match = re.search(r'src="(/assets/[^"]+)"', r1.text)
if js_match:
    js_url = js_match.group(1)
    r2 = requests.get(f"http://localhost:9100{js_url}")
    print(f"JS bundle:  {r2.status_code} ({len(r2.content)} bytes)")
# Check CSS
css_match = re.search(r'href="(/assets/[^"]+\.css)"', r1.text)
if css_match:
    css_url = css_match.group(1)
    r3 = requests.get(f"http://localhost:9100{css_url}")
    print(f"CSS bundle: {r3.status_code} ({len(r3.content)} bytes)")
