"""
register_skill.py — 打包 lakemind-connector Skill 并注册到 LakeMind

流程:
    1. 打包 skills/lakemind-connector/ 为 zip
    2. 上传到 S3: s3://lakemind-filesets/opencode/skills/lakemind-connector.zip
    3. 向量化 SKILL.md 并存入 LanceDB (供其他 Agent 检索发现)

用法:
    python scripts/register_skill.py
"""

import asyncio
import io
import json
import os
import sys
import time
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "lakemind-connector"))
from connector import LakeMindConnector

SKILL_NAME = "lakemind-connector"
TENANT_ID = "opencode"
S3_BUCKET = "lakemind-filesets"
SKILL_S3_URI = f"s3://{S3_BUCKET}/{TENANT_ID}/skills/{SKILL_NAME}.zip"


def pack_skill() -> bytes:
    skill_dir = os.path.join(os.path.dirname(__file__), "..", "skills", "lakemind-connector")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(skill_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fname in files:
                if fname.endswith(".pyc"):
                    continue
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, skill_dir)
                zf.write(fpath, arcname)
                print(f"  + {arcname}")
    return buf.getvalue()


async def main():
    print("=== Pack Skill ===")
    zip_bytes = pack_skill()
    print(f"  zip size: {len(zip_bytes)} bytes")

    conn = LakeMindConnector()
    try:
        print("\n=== Health Check ===")
        try:
            health = await conn.platform_health()
            print(f"  [OK] platform healthy")
        except Exception as e:
            print(f"  [FAIL] platform health: {e}")
            return

        print("\n=== Upload to S3 ===")
        key = f"{TENANT_ID}/skills/{SKILL_NAME}.zip"
        try:
            r = await conn.s3_put(S3_BUCKET, key, zip_bytes)
            print(f"  [OK] uploaded: s3://{S3_BUCKET}/{key}")
        except Exception as e:
            print(f"  [FAIL] upload: {e}")
            return

        print("\n=== Register in Vector DB ===")
        skill_doc = (
            "lakemind-connector: LakeMind MCP 连接器 Skill。"
            "让 AI Agent 通过 MCP 协议接入 LakeMind 平台，存取认知资产（知识、记忆）。"
            "封装 AssetMCP(记忆)、AdminMCP(租户)、ModelServing(Embedding/LLM)、Server(向量存储) 全部接口。"
            "Agent 检索到本 Skill 后在自身运行时执行，LakeMind 不执行。"
        )
        try:
            vec = await conn.embed(skill_doc)
            data = [{
                "concept_id": f"skill_{SKILL_NAME}_{int(time.time())}",
                "type": "agent_skill",
                "title": f"Skill: {SKILL_NAME}",
                "description": skill_doc[:500],
                "tags": ["skill", "mcp", "connector", "lakemind"],
                "s3_uri": SKILL_S3_URI,
                "vector": vec,
                "created_at": time.time(),
            }]
            r = await conn._http.post(
                f"{conn.server_url}/api/v1/storage/vectors/{conn._db}",
                headers=conn._server_headers,
                json={"name": "skill_vectors", "data": data, "mode": "append"},
            )
            if r.status_code == 500:
                r = await conn._http.post(
                    f"{conn.server_url}/api/v1/storage/vectors/{conn._db}",
                    headers=conn._server_headers,
                    json={"name": "skill_vectors", "data": data, "mode": "overwrite"},
                )
            r.raise_for_status()
            print(f"  [OK] registered in vector DB: skill_vectors")
        except Exception as e:
            print(f"  [FAIL] vector register: {e}")

        print("\n=== Verify ===")
        try:
            search_vec = await conn.embed("lakemind connector skill")
            r = await conn._http.post(
                f"{conn.server_url}/api/v1/storage/vectors/{conn._db}/skill_vectors/search",
                headers=conn._server_headers,
                json={"query_vec": search_vec, "top_k": 3},
            )
            hits = r.json().get("results", [])
            print(f"  search 'lakemind connector skill': {len(hits)} hits")
            for h in hits:
                print(f"    [{h.get('_distance', 0):.4f}] {h.get('title', '')}")
        except Exception as e:
            print(f"  [FAIL] verify search: {e}")

        print(f"\n=== Done ===")
        print(f"  Skill: {SKILL_NAME}")
        print(f"  S3:    {SKILL_S3_URI}")
        print(f"  Agent retrieves via: search_skill('{SKILL_NAME}') -> get_skill('{SKILL_NAME}')")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
