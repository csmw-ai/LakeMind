"""Seed model profiles for Meeting Agent into LakeMindModelServing.

Uses the unified ModelServing API (POST /v1/models, POST /v1/profiles).
No restart required — models are hot-loaded.
"""
from __future__ import annotations
import asyncio
import os
import httpx

MS_URL = os.environ.get("MODEL_SERVING_URL", "http://localhost:10824").rstrip("/")
MS_KEY = os.environ.get("MODELSERVING_API_KEY", "lakemind-modelserving-key")

PROFILES = [
    {"name": "meeting-asr", "model_type": "asr", "model_name": "sensevoice-small",
     "description": "ASR for meeting transcription"},
    {"name": "meeting-minutes", "model_type": "chat", "model_name": "deepseek-v4-flash",
     "description": "LLM for meeting minutes"},
    {"name": "meeting-knowledge-extract", "model_type": "chat", "model_name": "deepseek-v4-flash",
     "description": "LLM for knowledge extraction"},
    {"name": "meeting-embedding", "model_type": "embedding", "model_name": "jinaai/jina-embeddings-v2-base-zh",
     "description": "Embedding for meeting knowledge"},
]


async def main():
    headers = {"Authorization": f"Bearer {MS_KEY}"}
    async with httpx.AsyncClient(base_url=MS_URL, headers=headers, timeout=30) as client:
        existing_models = (await client.get("/v1/models")).json()
        model_map = {m["name"]: m for m in existing_models.get("data", [])}
        print(f"Existing models: {list(model_map.keys())}")

        existing_profiles = (await client.get("/v1/profiles")).json()
        profile_map = {p["name"]: p for p in existing_profiles.get("data", [])}

        for p in PROFILES:
            model = model_map.get(p["model_name"])
            if not model:
                print(f"  [FAIL] model '{p['model_name']}' not found in ModelServing")
                continue

            if p["name"] in profile_map:
                existing = profile_map[p["name"]]
                if existing.get("model_id") == model["model_id"]:
                    print(f"  [SKIP] profile '{p['name']}' already -> {p['model_name']}")
                    continue
                resp = await client.put(f"/v1/profiles/{existing['profile_id']}", json={
                    "model_id": model["model_id"],
                })
                if resp.status_code == 200:
                    print(f"  [OK] updated profile '{p['name']}' -> {p['model_name']}")
                else:
                    print(f"  [FAIL] update profile '{p['name']}': {resp.status_code} {resp.text[:80]}")
                continue

            resp = await client.post("/v1/profiles", json={
                "name": p["name"],
                "model_type": p["model_type"],
                "model_id": model["model_id"],
                "description": p["description"],
            })
            if resp.status_code == 200:
                print(f"  [OK] created profile '{p['name']}' -> {p['model_name']}")
            else:
                print(f"  [FAIL] create profile '{p['name']}': {resp.status_code} {resp.text[:80]}")

        print("\n--- Verify ---")
        for p in PROFILES:
            resp = await client.get(f"/v1/profiles/{p['name']}/resolve")
            if resp.status_code == 200:
                data = resp.json()
                print(f"  [OK] {p['name']} -> {data.get('model_name', '?')}")
            else:
                print(f"  [FAIL] {p['name']}: {resp.status_code}")


if __name__ == "__main__":
    asyncio.run(main())
