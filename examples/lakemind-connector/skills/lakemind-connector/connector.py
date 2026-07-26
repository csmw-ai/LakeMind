"""
LakeMind 连接器 — 通过 MCP (AssetMCP + AdminMCP) + ModelServing + Server REST 存取认知资产。

架构:
    AssetMCP (:8401)  → 知识/记忆/技能/本体 (23 tools, MCP protocol)
    AdminMCP (:8403)  → 租户/Token/健康 (17 tools, MCP protocol)
    ModelServing (:10824) → Embedding / LLM / ASR (REST API)
    Server (:10823)   → 向量存储 / S3 / Ray jobs (REST API)
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import time
import zipfile
from urllib.parse import urlparse

import httpx
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = ("SUCCEEDED", "STOPPED", "FAILED", "completed", "cancelled", "failed")
_ASR_TAG_RE = re.compile(r"<\s*\|[^|]*\|\s*>")


class LakeMindConnector:
    """LakeMind 统一连接器，封装 MCP + REST 全部接口。"""

    def __init__(
        self,
        asset_mcp_url: str | None = None,
        admin_mcp_url: str | None = None,
        server_url: str | None = None,
        server_key: str | None = None,
        model_serving_url: str | None = None,
        model_serving_key: str | None = None,
        tenant_token: str | None = None,
        admin_token: str | None = None,
        tenant_id: str = "opencode",
    ):
        self.asset_mcp_url = asset_mcp_url or os.environ.get("ASSET_MCP_URL", "http://localhost:8401/mcp")
        self.admin_mcp_url = admin_mcp_url or os.environ.get("ADMIN_MCP_URL", "http://localhost:8403/mcp")
        self.server_url = (server_url or os.environ.get("SERVER_API_URL", "http://localhost:10823")).rstrip("/")
        self.server_key = server_key or os.environ.get("SERVER_API_KEY", "lakemind-internal-api-key")
        self.ms_url = (model_serving_url or os.environ.get("MODEL_SERVING_URL", "http://localhost:10824")).rstrip("/")
        self.ms_key = model_serving_key or os.environ.get("MODELSERVING_API_KEY", "lakemind-modelserving-key")
        self.tenant_token = tenant_token or os.environ.get("OPENCODE_TOKEN", "tk_9d377e74c0c14969")
        self.admin_token = admin_token or os.environ.get("ADMIN_TOKEN", "test-steward-token")
        self.tenant_id = tenant_id or os.environ.get("TENANT_ID", "opencode")

        self._http = httpx.AsyncClient(timeout=120)
        self._embedding_model = "jina-embeddings-v2-base-zh"
        self._llm_model = "deepseek-v4-flash"

    async def close(self):
        await self._http.aclose()

    @property
    def _db(self) -> str:
        return f"tenant_{self.tenant_id}"

    def _table(self, kb_name: str) -> str:
        return f"kb_{kb_name}"

    @property
    def _server_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.server_key}", "X-Tenant-Id": self.tenant_id}

    @property
    def _ms_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.ms_key}"}

    # ── MCP 调用 ──────────────────────────────────────────────

    async def _call_asset_mcp(self, tool: str, arguments: dict) -> dict:
        async with streamablehttp_client(
            self.asset_mcp_url, headers={"Authorization": f"Bearer {self.tenant_token}"}
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments=arguments)
                if result.isError:
                    raise RuntimeError(f"AssetMCP {tool}: {result.content}")
                return json.loads(result.content[0].text)

    async def _call_admin_mcp(self, tool: str, arguments: dict) -> dict:
        async with streamablehttp_client(
            self.admin_mcp_url, headers={"Authorization": f"Bearer {self.admin_token}"}
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments=arguments)
                if result.isError:
                    raise RuntimeError(f"AdminMCP {tool}: {result.content}")
                return json.loads(result.content[0].text)

    async def list_mcp_tools(self) -> dict:
        result = {}
        for name, url, token in [
            ("AssetMCP", self.asset_mcp_url, self.tenant_token),
            ("AdminMCP", self.admin_mcp_url, self.admin_token),
        ]:
            async with streamablehttp_client(url, headers={"Authorization": f"Bearer {token}"}) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    result[name] = [t.name for t in tools.tools]
        return result

    # ── Embedding & LLM (ModelServing) ────────────────────────

    async def embed(self, text: str) -> list[float]:
        r = await self._http.post(
            f"{self.ms_url}/v1/embeddings",
            headers=self._ms_headers,
            json={"model": self._embedding_model, "input": [text]},
        )
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]

    async def llm_chat(self, system_prompt: str, user_content: str) -> str:
        r = await self._http.post(
            f"{self.ms_url}/v1/chat/completions",
            headers=self._ms_headers,
            json={
                "model": self._llm_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    # ── 知识 (向量存储, Server REST) ──────────────────────────

    async def store_knowledge(self, kb_name: str, concepts: list[dict]) -> int:
        table = self._table(kb_name)
        data = []
        for c in concepts:
            fm = c.get("frontmatter", {})
            title = fm.get("title", c.get("title", ""))
            body = c.get("body", "")
            text = f"{title}\n{body}"
            vec = await self.embed(text)
            data.append({
                "concept_id": fm.get("resource", f"{kb_name}_{int(time.time() * 1000000)}_{len(data)}"),
                "type": fm.get("type", c.get("type", "knowledge")),
                "title": title,
                "description": body[:500],
                "tags": fm.get("tags", c.get("tags", [])),
                "s3_uri": "",
                "vector": vec,
                "created_at": time.time(),
            })

        add_url = f"{self.server_url}/api/v1/storage/vectors/{self._db}/{table}/add"
        create_url = f"{self.server_url}/api/v1/storage/vectors/{self._db}"
        r = await self._http.post(add_url, headers=self._server_headers, json={"data": data})
        if r.status_code == 404:
            r = await self._http.post(
                create_url, headers=self._server_headers,
                json={"name": table, "data": data, "mode": "overwrite"},
            )
        r.raise_for_status()
        logger.info("[OK] store_knowledge: %d concepts -> %s", len(data), table)
        return len(data)

    async def search_knowledge(self, query: str, kb_name: str, top_k: int = 5) -> list[dict]:
        table = self._table(kb_name)
        vec = await self.embed(query)
        r = await self._http.post(
            f"{self.server_url}/api/v1/storage/vectors/{self._db}/{table}/search",
            headers=self._server_headers,
            json={"query_vec": vec, "top_k": top_k},
        )
        if r.status_code in (404, 500):
            return []
        r.raise_for_status()
        return r.json().get("results", [])

    async def describe_knowledge(self, kb_name: str) -> dict:
        table = self._table(kb_name)
        r = await self._http.get(
            f"{self.server_url}/api/v1/storage/vectors/{self._db}/{table}",
            headers=self._server_headers,
        )
        r.raise_for_status()
        return r.json()

    async def scan_knowledge(self, kb_name: str, limit: int = 100) -> list[dict]:
        table = self._table(kb_name)
        r = await self._http.get(
            f"{self.server_url}/api/v1/storage/vectors/{self._db}/{table}/scan",
            headers=self._server_headers,
            params={"limit": limit},
        )
        r.raise_for_status()
        return r.json().get("results", [])

    async def list_knowledge_bases(self) -> list[str]:
        r = await self._http.get(
            f"{self.server_url}/api/v1/storage/vectors/{self._db}",
            headers=self._server_headers,
        )
        r.raise_for_status()
        return [t for t in r.json().get("tables", []) if t.startswith("kb_")]

    # ── 记忆 (AssetMCP) ───────────────────────────────────────

    async def add_memory(self, messages: list[dict], metadata: dict | None = None) -> dict:
        args = {"messages": messages, "infer": False}
        if metadata:
            args["metadata"] = metadata
        return await self._call_asset_mcp("add_memory", args)

    async def search_memory(self, query: str, top_k: int = 5) -> dict:
        return await self._call_asset_mcp("search_memory", {"query": query, "top_k": top_k})

    async def list_memory(self, page: int = 1, page_size: int = 20) -> dict:
        return await self._call_asset_mcp("list_memory", {"page": page, "page_size": page_size})

    async def get_memory(self, memory_id: str) -> dict:
        return await self._call_asset_mcp("get_memory", {"memory_id": memory_id})

    async def delete_memory(self, memory_id: str) -> dict:
        return await self._call_asset_mcp("delete_memory", {"memory_id": memory_id})

    async def clear_memory(self) -> dict:
        return await self._call_asset_mcp("clear_memory", {})

    # ── 租户管理 (AdminMCP) ───────────────────────────────────

    async def create_tenant(self, tenant_id: str, name: str, description: str = "") -> dict:
        return await self._call_admin_mcp("create_tenant", {
            "tenant_id": tenant_id, "name": name, "description": description,
        })

    async def issue_token(self, tenant_id: str, agent_id: str, scopes: list[str]) -> dict:
        return await self._call_admin_mcp("issue_token", {
            "tenant_id": tenant_id, "agent_id": agent_id, "scopes": scopes,
        })

    async def list_tenants(self) -> dict:
        return await self._call_admin_mcp("list_tenants", {})

    async def platform_health(self) -> dict:
        return await self._call_admin_mcp("get_platform_health", {})

    # ── S3 (Server REST) ──────────────────────────────────────

    async def s3_put(self, bucket: str, key: str, data: bytes) -> dict:
        r = await self._http.put(
            f"{self.server_url}/api/v1/storage/objects/{bucket}/{key}",
            content=data, headers=self._server_headers,
        )
        r.raise_for_status()
        return r.json()

    async def s3_get(self, bucket: str, key: str) -> bytes:
        r = await self._http.get(
            f"{self.server_url}/api/v1/storage/objects/{bucket}/{key}",
            headers=self._server_headers,
        )
        r.raise_for_status()
        return r.content

    async def s3_list(self, bucket: str, prefix: str = "") -> dict:
        r = await self._http.get(
            f"{self.server_url}/api/v1/storage/objects/{bucket}",
            headers=self._server_headers, params={"prefix": prefix},
        )
        r.raise_for_status()
        return r.json()

    # ── S3 URI-based API (s3://bucket/key) ────────────────────

    @staticmethod
    def _parse_s3_uri(uri: str) -> tuple[str, str]:
        p = urlparse(uri)
        return p.netloc, p.path.lstrip("/")

    async def s3_put_uri(self, uri: str, data: bytes) -> dict:
        bucket, key = self._parse_s3_uri(uri)
        return await self.s3_put(bucket, key, data)

    async def s3_get_uri(self, uri: str) -> bytes:
        bucket, key = self._parse_s3_uri(uri)
        return await self.s3_get(bucket, key)

    async def s3_exists_uri(self, uri: str) -> bool:
        bucket, key = self._parse_s3_uri(uri)
        r = await self._http.head(
            f"{self.server_url}/api/v1/storage/objects/{bucket}/{key}",
            headers=self._server_headers,
        )
        return r.status_code == 200

    # ── ASR (ModelServing) ────────────────────────────────────

    async def asr(self, audio: bytes, filename: str = "audio.wav") -> dict:
        r = await self._http.post(
            f"{self.ms_url}/v1/audio/transcriptions",
            headers=self._ms_headers,
            files={"file": (filename, audio, "audio/wav")},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()

    @staticmethod
    def clean_asr_text(text: str) -> str:
        text = _ASR_TAG_RE.sub("", text)
        return re.sub(r"\s+", " ", text).strip()

    # ── Ray Jobs (Server REST) ────────────────────────────────

    async def submit_job(
        self,
        skill_uri: str,
        job_name: str,
        params: dict,
        env_overrides: dict | None = None,
        resources: dict | None = None,
        task_id: str = "",
    ) -> dict:
        r = await self._http.post(
            f"{self.server_url}/api/v1/compute/jobs/submit",
            headers=self._server_headers,
            json={
                "skill_uri": skill_uri,
                "job_name": job_name,
                "params": params,
                "env_overrides": env_overrides or {},
                "resources": resources or {},
                "task_id": task_id,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    async def get_job_status(self, job_id: str) -> dict:
        r = await self._http.get(
            f"{self.server_url}/api/v1/compute/jobs/{job_id}",
            headers=self._server_headers,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    async def get_job_result(self, job_id: str) -> dict:
        r = await self._http.get(
            f"{self.server_url}/api/v1/compute/jobs/{job_id}/result",
            headers=self._server_headers,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    async def cancel_job(self, job_id: str) -> dict:
        r = await self._http.post(
            f"{self.server_url}/api/v1/compute/jobs/{job_id}/cancel",
            headers=self._server_headers,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    async def list_jobs(self, status: str = "") -> dict:
        params = {}
        if status:
            params["status"] = status
        r = await self._http.get(
            f"{self.server_url}/api/v1/compute/jobs",
            headers=self._server_headers,
            params=params,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    async def poll_job(self, job_id: str, interval: float = 1.5, timeout: float = 120) -> dict:
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            status = await self.get_job_status(job_id)
            s = status.get("status", "")
            if s in _TERMINAL_STATUSES:
                return status
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError(f"job {job_id} timed out after {timeout}s (last status: {s})")
            await asyncio.sleep(interval)

    async def submit_and_wait(
        self,
        skill_uri: str,
        job_name: str,
        params: dict,
        interval: float = 1.5,
        timeout: float = 120,
    ) -> dict:
        job = await self.submit_job(skill_uri, job_name, params)
        return await self.poll_job(job["job_id"], interval=interval, timeout=timeout)

    # ── Skill Packaging ───────────────────────────────────────

    @staticmethod
    def pack_skill(skill_dir: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(skill_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    arcname = os.path.relpath(fpath, skill_dir).replace("\\", "/")
                    zf.write(fpath, arcname)
        return buf.getvalue()

    async def upload_skill(self, skill_dir: str, skill_name: str, bucket: str = "lakemind-filesets") -> str:
        zip_data = self.pack_skill(skill_dir)
        key = f"{self.tenant_id}/skills/{skill_name}.zip"
        await self.s3_put(bucket, key, zip_data)
        uri = f"s3://{bucket}/{key}"
        logger.info("[OK] skill uploaded: %s (%d bytes)", uri, len(zip_data))
        return uri

    # ── Health Check ──────────────────────────────────────────

    async def check_health(self) -> dict:
        result = {}
        try:
            r = await self._http.get(f"{self.ms_url}/v1/models", headers=self._ms_headers, timeout=10)
            models = [m["id"] for m in r.json().get("data", [])] if r.status_code == 200 else []
            result["model_serving"] = {"ok": r.status_code == 200, "models": models}
        except Exception as e:
            result["model_serving"] = {"ok": False, "error": str(e)}

        try:
            r = await self._http.get(
                f"{self.server_url}/api/v1/system/health",
                headers=self._server_headers, timeout=10,
            )
            health = r.json() if r.status_code == 200 else {}
            result["server"] = {"ok": r.status_code == 200, "distributed": health.get("distributed", False)}
        except Exception as e:
            result["server"] = {"ok": False, "error": str(e)}

        try:
            r = await self._http.get(self.asset_mcp_url, timeout=5)
            result["asset_mcp"] = {"ok": True}
        except Exception as e:
            result["asset_mcp"] = {"ok": False, "error": str(e)}

        result["all_ok"] = all(v.get("ok", False) for v in result.values() if isinstance(v, dict))
        return result
