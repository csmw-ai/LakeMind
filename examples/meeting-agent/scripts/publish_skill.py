import asyncio
import io
import json
import os
import zipfile
import sys
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SERVER_URL = os.environ.get("SERVER_API_URL", "http://localhost:10823").rstrip("/")
SERVER_KEY = os.environ.get("SERVER_API_KEY", "")
TENANT_ID = os.environ.get("TENANT_ID", "examples-meeting-agent")
S3_BUCKET = os.environ.get("S3_BUCKET", "lakemind-filesets")


def pack_skill() -> bytes:
    skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "meeting-processing")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(skills_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, skills_dir).replace("\\", "/")
                zf.write(fpath, arcname)
    return buf.getvalue()


async def main():
    zip_bytes = pack_skill()
    print(f"skill zip: {len(zip_bytes)} bytes")

    headers = {"Authorization": f"Bearer {SERVER_KEY}", "X-Tenant-Id": TENANT_ID}
    async with httpx.AsyncClient(base_url=SERVER_URL, headers=headers, timeout=30) as client:
        skill_s3_uri = f"s3://{S3_BUCKET}/{TENANT_ID}/skills/meeting-processing-v0.2.0.zip"
        from urllib.parse import urlparse
        p = urlparse(skill_s3_uri)
        put_url = f"/api/v1/storage/objects/{p.netloc}/{p.path.lstrip('/')}"
        resp = await client.put(put_url, content=zip_bytes)
        if resp.status_code in (200, 201):
            print(f"[OK] uploaded skill to {skill_s3_uri}")
        else:
            print(f"[FAIL] upload: {resp.status_code} {resp.text}")

        manifest_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                      "skills", "meeting-processing", "manifest.yaml")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_content = f.read()

        import yaml
        manifest = yaml.safe_load(manifest_content)

        existing = (await client.get("/api/v1/skills")).json()
        skill_id = None
        for s in existing.get("items", []):
            if s.get("name") == "meeting-processing":
                skill_id = s.get("asset_id") or s.get("skill_id")
                break

        if not skill_id:
            body = {
                "manifest": manifest,
                "code_package": {"s3_uri": skill_s3_uri, "size_bytes": len(zip_bytes)},
                "trust_level": "demo",
            }
            resp = await client.post("/api/v1/skills/register", json=body)
            if resp.status_code == 200:
                skill_id = resp.json().get("asset_id")
                print(f"[OK] registered skill: {skill_id}")
            else:
                print(f"[FAIL] register: {resp.status_code} {resp.text}")
                return
        else:
            body = {
                "manifest": manifest,
                "code_package": {"s3_uri": skill_s3_uri, "size_bytes": len(zip_bytes)},
                "trust_level": "demo",
            }
            resp = await client.put(f"/api/v1/skills/{skill_id}", json=body)
            if resp.status_code == 200:
                print(f"[OK] updated skill: {skill_id}")
            else:
                print(f"[SKIP] update: {resp.status_code} {resp.text}")

        resp = await client.post(f"/api/v1/skills/{skill_id}/publish")
        if resp.status_code == 200:
            print(f"[OK] published skill: {skill_id}")
        else:
            print(f"[SKIP] publish: {resp.status_code} {resp.text}")


if __name__ == "__main__":
    asyncio.run(main())
