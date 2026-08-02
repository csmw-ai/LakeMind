import asyncio
import io
import json
import os
import zipfile
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lakemind_client import LakeMindClient

SKILL_NAME = "meeting-processing"
TENANT_ID = os.environ.get("TENANT_ID", "examples-meeting-agent")
S3_BUCKET = "lakemind-filesets"
SKILL_S3_URI = f"s3://{S3_BUCKET}/{TENANT_ID}/skills/{SKILL_NAME}.zip"


def pack_skill() -> bytes:
    skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "meeting-processing")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(skills_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, skills_dir).replace("\\", "/")
                zf.write(fpath, arcname)
                print(f"  + {arcname}")
    return buf.getvalue()


async def health_checks(client: LakeMindClient):
    print("\n--- Health Checks ---")
    ok = True

    try:
        resp = await client._http.get(
            f"{client.ms_url}/v1/models",
            headers={"Authorization": f"Bearer {client.ms_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            models = [m["id"] for m in resp.json().get("data", [])]
            print(f"  [OK] ModelServing /v1/models: {len(models)} models available")
        else:
            print(f"  [FAIL] ModelServing /v1/models: HTTP {resp.status_code}")
            ok = False
    except Exception as e:
        print(f"  [FAIL] ModelServing unreachable: {e}")
        ok = False

    try:
        resp = await client._http.get(
            f"{client.server_url}/api/v1/system/health",
            headers={"Authorization": f"Bearer {client.server_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            health = resp.json()
            dist_ok = health.get("distributed", False)
            print(f"  [OK] LakeMindServer health: distributed={dist_ok}")
            if not dist_ok:
                print("  [WARN] Ray distributed engine not available — jobs will fail")
        else:
            print(f"  [FAIL] LakeMindServer health: HTTP {resp.status_code}")
            ok = False
    except Exception as e:
        print(f"  [FAIL] LakeMindServer unreachable: {e}")
        ok = False

    try:
        from mcp.client.streamable_http import streamablehttp_client
        from mcp import ClientSession
        async with streamablehttp_client(
            client.data_mcp_url,
            headers={"Authorization": f"Bearer {client.mcp_token}"},
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]
                print(f"  [OK] DataMCP connected: {len(tool_names)} tools")
    except Exception as e:
        print(f"  [FAIL] DataMCP unreachable: {e}")
        ok = False

    if not ok:
        print("\n  Some services are not ready. Start them before running the agent.")
        sys.exit(1)
    print("--- Health Checks Passed ---\n")


async def main():
    zip_bytes = pack_skill()
    print(f"\nskill zip size: {len(zip_bytes)} bytes")

    client = LakeMindClient()
    try:
        await health_checks(client)

        result = await client.s3_put(SKILL_S3_URI, zip_bytes)
        print(f"uploaded to S3: {SKILL_S3_URI}")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        exists = await client.s3_exists(SKILL_S3_URI)
        print(f"verified exists: {exists}")

        print(f"\nskill_uri for ray_submit_job: lake://skills/{SKILL_NAME}")
        print(f"  (resolved to s3://{S3_BUCKET}/{TENANT_ID}/skills/{SKILL_NAME}.zip)")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
