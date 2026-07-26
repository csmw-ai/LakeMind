import asyncio, json
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async def test():
    async with streamablehttp_client("http://localhost:8402/mcp", headers={"Authorization": "Bearer meeting-agent-mcp-token"}) as (r,w,_):
        async with ClientSession(r,w) as s:
            await s.initialize()
            tools = await s.list_tools()
            names = [t.name for t in tools.tools]
            print(f"DataMCP: {len(names)} tools")
            print(f"  ray_submit_job: {'ray_submit_job' in names}")
            print(f"  s3_put: {'s3_put' in names}")

    async with streamablehttp_client("http://localhost:8401/mcp", headers={"Authorization": "Bearer meeting-agent-mcp-token"}) as (r,w,_):
        async with ClientSession(r,w) as s:
            await s.initialize()
            tools = await s.list_tools()
            names = [t.name for t in tools.tools]
            print(f"AssetMCP: {len(names)} tools")
            print(f"  add_memory: {'add_memory' in names}")
            print(f"  ingest_knowledge: {'ingest_knowledge' in names}")

asyncio.run(test())
