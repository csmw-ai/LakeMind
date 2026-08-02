from __future__ import annotations
import base64
import json
import logging
from ..config import ASSET_MCP_URL, DATA_MCP_URL, MCP_TOKEN, SERVER_URL, SERVER_KEY, TENANT_ID, MS_URL, MS_KEY

logger = logging.getLogger("meeting-agent")


class MCPError(Exception):
    def __init__(self, stage: str, message: str, detail: str = ""):
        self.stage = stage
        self.message = message
        self.detail = detail
        super().__init__(f"[{stage}] {message}")


def _unwrap_exception(e: Exception) -> str:
    parts = [f"{type(e).__name__}: {e}"]
    if isinstance(e, BaseExceptionGroup):
        for sub in e.exceptions:
            parts.append(f"  -> {type(sub).__name__}: {sub}")
            if isinstance(sub, BaseExceptionGroup):
                for sub2 in sub.exceptions:
                    parts.append(f"    -> {type(sub2).__name__}: {sub2}")
    return "\n".join(parts)


async def _call_mcp(url: str, tool: str, arguments: dict, max_retries: int = 3) -> dict:
    from mcp.client.streamable_http import streamable_http_client
    from mcp import ClientSession
    import asyncio
    import httpx

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with streamable_http_client(
                url,
                http_client=httpx.AsyncClient(
                    headers={"Authorization": f"Bearer {MCP_TOKEN}"},
                    timeout=30,
                ),
                terminate_on_close=False,
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool, arguments=arguments)
                    if result.is_error:
                        err_text = result.content[0].text if result.content else "unknown error"
                        raise MCPError(tool, f"MCP tool returned error: {err_text}")
                    text = result.content[0].text if result.content else "{}"
                    return json.loads(text)
        except MCPError:
            raise
        except Exception as e:
            last_exc = e
            detail = _unwrap_exception(e)
            if attempt < max_retries - 1:
                logger.warning(f"MCP {tool} attempt {attempt + 1}/{max_retries} failed: {detail}")
                await asyncio.sleep(0.5 * (attempt + 1))
            else:
                raise MCPError(tool, f"MCP call failed (after {max_retries} retries): {detail}")
    raise MCPError(tool, f"MCP call failed: {_unwrap_exception(last_exc)}")


class LakeClient:
    async def close(self):
        pass

    async def s3_put(self, uri: str, data: bytes, token: str | None = None) -> dict:
        body_b64 = base64.b64encode(data).decode("ascii")
        try:
            return await _call_mcp(DATA_MCP_URL, "s3_put", {"uri": uri, "body_b64": body_b64})
        except MCPError:
            raise

    async def s3_get(self, uri: str, token: str | None = None) -> bytes:
        try:
            resp = await _call_mcp(DATA_MCP_URL, "s3_get", {"uri": uri})
            if "content_b64" in resp:
                return base64.b64decode(resp["content_b64"])
            content = resp.get("content", "")
            if content:
                return content.encode("utf-8")
            return b""
        except MCPError:
            raise
        except Exception as e:
            raise MCPError("s3_get", f"Failed to decode S3 object: {e}")

    async def s3_delete(self, uri: str, token: str | None = None) -> None:
        try:
            await _call_mcp(DATA_MCP_URL, "s3_delete", {"uri": uri})
        except MCPError as e:
            if "not found" not in e.message.lower() and "404" not in e.message:
                raise

    async def submit_job(self, skill_ref: str, inputs: dict, model_profile: str | None = None,
                          idempotency_key: str | None = None, token: str | None = None) -> dict:
        skill_uri = skill_ref.replace("lake://skills/", "s3://lakemind-filesets/" + TENANT_ID + "/skills/")
        version = "0.2.0"
        if "@" in skill_uri:
            skill_uri, version = skill_uri.rsplit("@", 1)
        skill_uri += f"-v{version}.zip"

        result_key = inputs.get("result_key", "")
        if result_key.startswith("asr"):
            job_name = "asr_chunk"
        elif result_key.startswith("minutes"):
            job_name = "minutes_generate"
        elif result_key.startswith("knowledge"):
            job_name = "knowledge_extract"
        else:
            job_name = "asr_chunk"

        try:
            return await _call_mcp(DATA_MCP_URL, "ray_submit_job", {
                "skill_uri": skill_uri,
                "job_name": job_name,
                "params": inputs,
                "env_overrides": {
                    "SERVER_API_URL": SERVER_URL,
                    "SERVER_API_KEY": SERVER_KEY,
                    "MODEL_SERVING_URL": MS_URL,
                    "MODELSERVING_API_KEY": MS_KEY,
                },
            })
        except MCPError:
            raise

    async def get_job(self, job_id: str, token: str | None = None) -> dict:
        try:
            return await _call_mcp(DATA_MCP_URL, "ray_job_status", {"job_id": job_id})
        except MCPError:
            raise

    async def get_job_result(self, job_id: str, token: str | None = None) -> dict:
        try:
            return await _call_mcp(DATA_MCP_URL, "ray_job_result", {"job_id": job_id})
        except MCPError:
            raise

    async def retry_job(self, job_id: str, token: str | None = None) -> dict:
        raise MCPError("retry_job", "Not supported via MCP")

    async def knowledge_ingest(self, name: str, content: str, kb_name: str = "meetings",
                                token: str | None = None) -> dict:
        try:
            return await _call_mcp(ASSET_MCP_URL, "ingest_knowledge", {
                "kb_name": kb_name,
                "concepts": [{"frontmatter": {"title": name, "type": "knowledge"}, "body": content}],
            })
        except MCPError:
            raise

    async def knowledge_search(self, query: str, kb_name: str = "meetings", top_k: int = 5,
                                token: str | None = None) -> dict:
        try:
            return await _call_mcp(ASSET_MCP_URL, "search_knowledge", {
                "query": query, "kb_name": kb_name, "top_k": top_k,
            })
        except MCPError:
            raise

    async def memory_add(self, messages: list[dict], metadata: dict | None = None,
                          token: str | None = None) -> dict:
        try:
            return await _call_mcp(ASSET_MCP_URL, "add_memory", {
                "messages": messages,
                "infer": False,
                "metadata": metadata or {},
            })
        except MCPError:
            raise

    async def memory_search(self, query: str, top_k: int = 5, token: str | None = None) -> dict:
        try:
            return await _call_mcp(ASSET_MCP_URL, "search_memory", {
                "query": query, "top_k": top_k,
            })
        except MCPError:
            raise

    async def create_asset(self, asset_type: str, name: str, metadata: dict | None = None,
                            token: str | None = None) -> dict:
        raise MCPError("create_asset", "Not supported via MCP — use register_skill instead")


lake = LakeClient()
