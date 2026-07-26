import asyncio
import sys
sys.path.insert(0, "/app/backend")
from app.services.pipeline_service import PipelineService
from app.security import AuthContext

async def main():
    ctx = AuthContext(
        principal_id="prn_01KXRBJ03NR21A6MFTBJHF8WTD",
        tenant_id="examples-meeting-agent",
        token="",
        roles=["user"],
        capabilities=[],
    )
    await PipelineService.run_final(ctx, "meeting-0ef2f11b588f")
    print("DONE")

asyncio.run(main())
