import base64
import json
import os
import logging

import httpx

logger = logging.getLogger(__name__)


class LakeMindClient:
    """
    LakeMind MCP client for the meeting-agent example.

    All data operations go through MCP (Agent 唯一入口):
      - S3 / Ray jobs / Iceberg tables → DataMCP (:8402)
      - Knowledge / Memory → AssetMCP (:8401)
    Health checks and model management use direct HTTP (not data operations).
    """
    def __init__(
        self,
        server_url: str | None = None,
        server_key: str | None = None,
        model_serving_url: str | None = None,
        model_serving_key: str | None = None,
        asset_mcp_url: str | None = None,
        data_mcp_url: str | None = None,
        mcp_token: str | None = None,
        tenant_id: str | None = None,
    ):
        self.server_url = (server_url or os.environ.get("SERVER_API_URL", "http://localhost:10823")).rstrip("/")
        self.server_key = server_key or os.environ.get("SERVER_API_KEY", "lakemind-internal-api-key")
        self.ms_url = (model_serving_url or os.environ.get("MODEL_SERVING_URL", "http://localhost:10824")).rstrip("/")
        self.ms_key = model_serving_key or os.environ.get("MODELSERVING_API_KEY", "lakemind-modelserving-key")
        self.asset_mcp_url = asset_mcp_url or os.environ.get("ASSET_MCP_URL", "http://localhost:8401/mcp")
        self.data_mcp_url = data_mcp_url or os.environ.get("DATA_MCP_URL", "http://localhost:8402/mcp")
        self.mcp_token = mcp_token or os.environ.get("MCP_TOKEN", "meeting-agent-mcp-token")
        self.tenant_id = tenant_id or os.environ.get("TENANT_ID", "examples-meeting-agent")
        self.skill_uri = os.environ.get("SKILL_URI", "lake://skills/meeting-processing")
        self._http = httpx.AsyncClient(timeout=120)

    async def close(self):
        await self._http.aclose()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.server_key}",
            "X-Tenant-Id": self.tenant_id,
        }

    # ── MCP helper ──────────────────────────────────────────────

    async def _call_mcp(self, url: str, tool: str, arguments: dict) -> dict:
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import httpx

        async with streamable_http_client(
            url,
            http_client=httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.mcp_token}"},
            ),
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments=arguments)
                if result.is_error:
                    raise RuntimeError(f"MCP tool {tool} error: {result.content}")
                text = result.content[0].text if result.content else "{}"
                return json.loads(text)

    # ── S3 (DataMCP) ────────────────────────────────────────────

    async def s3_put(self, uri: str, data: bytes) -> dict:
        body_b64 = base64.b64encode(data).decode("ascii")
        return await self._call_mcp(self.data_mcp_url, "s3_put", {"uri": uri, "body_b64": body_b64})

    async def s3_get(self, uri: str) -> bytes:
        resp = await self._call_mcp(self.data_mcp_url, "s3_get", {"uri": uri})
        if "content_b64" in resp:
            return base64.b64decode(resp["content_b64"])
        content = resp.get("content", "")
        return content.encode("utf-8") if content else b""

    async def s3_exists(self, uri: str) -> bool:
        try:
            await self._call_mcp(self.data_mcp_url, "s3_get", {"uri": uri})
            return True
        except Exception:
            return False

    # ── Ray Jobs (DataMCP) ──────────────────────────────────────

    async def submit_job(self, job_name: str, params: dict, task_id: str = "") -> dict:
        return await self._call_mcp(self.data_mcp_url, "ray_submit_job", {
            "skill_uri": self.skill_uri,
            "job_name": job_name,
            "params": params,
            "task_id": task_id,
            "env_overrides": {},
            "resources": {},
        })

    async def get_job_status(self, job_id: str) -> dict:
        return await self._call_mcp(self.data_mcp_url, "ray_job_status", {"job_id": job_id})

    async def list_jobs(self, status: str = "") -> dict:
        return await self._call_mcp(self.data_mcp_url, "ray_job_list", {"status": status})

    async def poll_job(self, job_id: str, interval: float = 1.5, timeout: float = 120) -> dict:
        import asyncio
        deadline = asyncio.get_event_loop().time() + timeout
        max_retries = 3
        while True:
            retry = 0
            while retry < max_retries:
                try:
                    status = await self.get_job_status(job_id)
                    break
                except Exception as e:
                    retry += 1
                    if retry >= max_retries:
                        raise
                    logger.warning("poll_job %s: transient error (retry %d/%d): %r", job_id, retry, max_retries, e)
                    await asyncio.sleep(interval * retry)
            else:
                raise RuntimeError(f"poll_job {job_id}: exhausted retries")
            s = status.get("status", "")
            if s in ("SUCCEEDED", "STOPPED", "FAILED", "completed", "cancelled", "failed"):
                return status
            if asyncio.get_event_loop().time() > deadline:
                try:
                    await self._call_mcp(self.data_mcp_url, "ray_job_cancel", {"job_id": job_id})
                    logger.warning("poll_job %s: timed out after %ss, cancelled job", job_id, timeout)
                except Exception:
                    logger.warning("poll_job %s: timed out after %ss, cancel failed", job_id, timeout)
                raise TimeoutError(f"job {job_id} timed out after {timeout}s (last status: {s})")
            await asyncio.sleep(interval)

    # ── Knowledge Search (AssetMCP) ─────────────────────────────

    async def search_knowledge(self, query: str, kb_name: str | None = None, top_k: int = 5) -> dict:
        args = {"query": query, "top_k": top_k}
        if kb_name:
            args["kb_name"] = kb_name
        resp = await self._call_mcp(self.asset_mcp_url, "search_knowledge", args)
        return {"query": query, "hits": resp.get("results", []), "count": resp.get("count", len(resp.get("results", [])))}

    # ── Memory (AssetMCP) ───────────────────────────────────────

    async def add_memory(self, messages: list[dict], metadata: dict | None = None) -> dict:
        args = {"messages": messages, "infer": False}
        if metadata:
            args["metadata"] = metadata
        return await self._call_mcp(self.asset_mcp_url, "add_memory", args)

    # ── Iceberg table management (DataMCP) ──────────────────────

    async def ensure_tenant(self, tenant_id: str, name: str) -> dict:
        return {"tenant_id": tenant_id, "name": name, "note": "tenant assumed pre-existing"}

    async def create_table(self, namespace: str, table: str, schema: dict[str, str]) -> dict:
        return await self._call_mcp(self.data_mcp_url, "create_table", {
            "name": table, "schema": schema,
        })

    async def table_exists(self, namespace: str, table: str) -> bool:
        resp = await self._call_mcp(self.data_mcp_url, "list_tables", {})
        tables = resp.get("tables", [])
        return table in tables

    async def append_rows(self, namespace: str, table: str, rows: list[dict]) -> dict:
        return await self._call_mcp(self.data_mcp_url, "write_table", {
            "table": table, "rows": rows, "mode": "append",
        })

    async def scan_table(self, namespace: str, table: str, limit: int = 1000) -> list[dict]:
        resp = await self._call_mcp(self.data_mcp_url, "query_table", {
            "table": table, "limit": limit,
        })
        return resp.get("rows", [])

    # ── Audio conversion (agent responsibility) ─────────────────

    @staticmethod
    def convert_to_wav(audio: bytes) -> bytes:
        import tempfile, subprocess
        if audio[:4] == b'RIFF':
            return audio
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as inf:
            inf.write(audio)
            in_path = inf.name
        out_path = in_path + ".wav"
        try:
            ffmpeg_bin = os.environ.get("FFMPEG_PATH", "ffmpeg")
            result = subprocess.run(
                [ffmpeg_bin, "-y", "-i", in_path, "-f", "wav", "-ar", "16000", "-ac", "1", out_path],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0 or not os.path.exists(out_path):
                logger.warning("ffmpeg conversion failed: %s", result.stderr[:200])
                return audio
            with open(out_path, "rb") as f:
                return f.read()
        except Exception as e:
            logger.warning("ffmpeg exception: %s", e)
            return audio
        finally:
            for p in (in_path, out_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass
