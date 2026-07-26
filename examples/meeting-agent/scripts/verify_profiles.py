"""Verify meeting-agent model profiles via ModelServing API."""
import asyncio, httpx, os

async def main():
    ms_url = os.environ.get("MODEL_SERVING_URL", "http://localhost:10824").rstrip("/")
    ms_key = os.environ.get("MODELSERVING_API_KEY", "lakemind-modelserving-key")
    headers = {"Authorization": f"Bearer {ms_key}"}
    async with httpx.AsyncClient(base_url=ms_url, headers=headers, timeout=10) as c:
        for p in ["meeting-asr", "meeting-minutes", "meeting-knowledge-extract", "meeting-embedding"]:
            r = await c.get(f"/v1/profiles/{p}/resolve")
            if r.status_code == 200:
                data = r.json()
                print(f"  {p}: OK -> {data.get('model_name', '?')}")
            else:
                print(f"  {p}: FAIL {r.status_code} {r.text[:80]}")

asyncio.run(main())
