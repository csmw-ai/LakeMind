import asyncio, json, httpx
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession

async def remember(text, meta=None):
    async with streamable_http_client(
        "http://localhost:8401/mcp",
        http_client=httpx.AsyncClient(
            headers={"Authorization": "Bearer tk_9d377e74c0c14969"},
        ),
    ) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            await session.call_tool("add_memory", {
                "messages": [{"role": "user", "content": text}],
                "infer": False,
                "metadata": meta or {"source": "agent", "type": "session-summary"},
            })

asyncio.run(remember(
    "Meeting Agent v0.2.0 Golden Path E2E test PASSED 25/25. "
    "Backend running on localhost:9100 serving both API and frontend dist. "
    "All WP0-WP6 code implemented: registration/login, task CRUD, audio chunk upload with idempotency+conflict detection, "
    "SSE, templates, transcript, minutes, knowledge review/publish, pipeline service. "
    "Security isolation verified (user A/B isolation, unauthenticated denied). "
    "2 LLM Model Profiles resolve successfully (meeting-minutes/knowledge-extract). ASR+embedding via Ray Serve. "
    "Fixes applied: (1) lake_client.py import path .config -> ..config, "
    "(2) security.py invited_by FK violation - check principal exists before using as invited_by, "
    "(3) deployment status set to 'enabled' for profile resolve to work. "
    "Pipeline status FAILED is expected (dummy WAV silence, skill not published yet). "
    "Frontend accessible at http://localhost:9100."
))
print("Memory saved.")
