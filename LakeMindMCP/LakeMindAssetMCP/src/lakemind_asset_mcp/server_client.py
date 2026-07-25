"""REST API 客户端 — MCP 通过此客户端访问 LakeMindServer 全部数据能力。"""
from __future__ import annotations

import os
from typing import Any

import httpx


class ServerClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self._base_url = (base_url or os.environ.get("SERVER_API_URL", "http://lakemind-server-api:10823")).rstrip("/")
        self._api_key = api_key or os.environ.get("SERVER_API_KEY", "lakemind-internal-api-key")
        self._ms_url = os.environ.get("MODEL_SERVING_URL", "http://lakemind-model-serving:10824").rstrip("/")
        self._ms_key = os.environ.get("MODELSERVING_API_KEY", "lakemind-modelserving-key")
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(30.0, connect=5.0),
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
            )
        return self._client

    def _headers(self) -> dict[str, str]:
        from .context import get_identity
        try:
            ident = get_identity()
            return {
                "Authorization": f"Bearer {self._api_key}",
                "X-Tenant-Id": ident.tenant_id,
                "X-Agent-Id": ident.agent_id,
                "X-Scopes": ",".join(ident.scopes),
            }
        except LookupError:
            return {"Authorization": f"Bearer {self._api_key}"}

    async def get(self, path: str, **kwargs) -> dict | bytes:
        r = await self.client.get(path, headers=self._headers(), **kwargs)
        r.raise_for_status()
        if r.headers.get("content-type", "").startswith("application/json"):
            return r.json()
        return r.content

    async def post(self, path: str, json: dict | None = None, **kwargs) -> dict:
        r = await self.client.post(path, headers=self._headers(), json=json, **kwargs)
        r.raise_for_status()
        return r.json()

    async def put(self, path: str, content: bytes | None = None, json: dict | None = None, **kwargs) -> dict:
        headers = self._headers()
        if content is not None:
            headers["Content-Type"] = "application/octet-stream"
        r = await self.client.put(path, headers=headers, content=content, json=json, **kwargs)
        r.raise_for_status()
        return r.json()

    async def delete(self, path: str, **kwargs) -> dict:
        r = await self.client.delete(path, headers=self._headers(), **kwargs)
        r.raise_for_status()
        return r.json()

    async def head(self, path: str, **kwargs) -> bool:
        r = await self.client.head(path, headers=self._headers(), **kwargs)
        return r.status_code == 200

    # ── System ──
    async def health(self) -> dict:
        return await self.get("/api/v1/system/health")

    async def nodes(self) -> dict:
        return await self.get("/api/v1/system/nodes")

    async def metrics(self) -> dict:
        return await self.get("/api/v1/system/metrics")

    # ── Objects ──
    async def object_put(self, bucket: str, key: str, body: bytes) -> dict:
        return await self.put(f"/api/v1/storage/objects/{bucket}/{key}", content=body)

    async def object_get(self, bucket: str, key: str) -> bytes:
        return await self.get(f"/api/v1/storage/objects/{bucket}/{key}")

    async def object_exists(self, bucket: str, key: str) -> bool:
        return await self.head(f"/api/v1/storage/objects/{bucket}/{key}")

    async def object_delete(self, bucket: str, key: str) -> dict:
        return await self.delete(f"/api/v1/storage/objects/{bucket}/{key}")

    async def object_list(self, bucket: str, prefix: str = "", limit: int = 1000) -> dict:
        return await self.get(f"/api/v1/storage/objects/{bucket}", params={"prefix": prefix, "limit": limit})

    # ── Tables (Iceberg) ──
    async def table_create(self, namespace: str, table: str, schema: dict, location: str | None = None) -> dict:
        return await self.post("/api/v1/storage/tables/", json={"namespace": namespace, "table": table, "schema": schema, "location": location})

    async def table_list(self, namespace: str) -> dict:
        return await self.get(f"/api/v1/storage/tables/{namespace}")

    async def table_describe(self, namespace: str, table: str) -> dict:
        return await self.get(f"/api/v1/storage/tables/{namespace}/{table}")

    async def table_drop(self, namespace: str, table: str) -> dict:
        return await self.delete(f"/api/v1/storage/tables/{namespace}/{table}")

    async def table_append(self, namespace: str, table: str, rows: list[dict]) -> dict:
        return await self.post(f"/api/v1/storage/tables/{namespace}/{table}/append", json={"rows": rows})

    async def table_overwrite(self, namespace: str, table: str, rows: list[dict]) -> dict:
        return await self.post(f"/api/v1/storage/tables/{namespace}/{table}/overwrite", json={"rows": rows})

    async def table_scan(self, namespace: str, table: str, columns: str | None = None, filter: str | None = None, limit: int | None = None) -> dict:
        params = {}
        if columns: params["columns"] = columns
        if filter: params["filter"] = filter
        if limit is not None: params["limit"] = limit
        return await self.get(f"/api/v1/storage/tables/{namespace}/{table}/scan", params=params)

    # ── Vectors (LanceDB) ──
    async def vector_create(self, db: str, name: str, data: list[dict], mode: str = "overwrite") -> dict:
        return await self.post(f"/api/v1/storage/vectors/{db}", json={"name": name, "data": data, "mode": mode})

    async def vector_list(self, db: str) -> dict:
        return await self.get(f"/api/v1/storage/vectors/{db}")

    async def vector_describe(self, db: str, name: str) -> dict:
        return await self.get(f"/api/v1/storage/vectors/{db}/{name}")

    async def vector_scan(self, db: str, name: str, limit: int = 100) -> list[dict]:
        resp = await self.get(f"/api/v1/storage/vectors/{db}/{name}/scan", params={"limit": limit})
        return resp.get("results", [])

    async def vector_add(self, db: str, name: str, data: list[dict]) -> dict:
        return await self.post(f"/api/v1/storage/vectors/{db}/{name}/add", json={"data": data})

    async def vector_search(self, db: str, name: str, query_vec: list[float], top_k: int = 5, filter: str | None = None) -> dict:
        return await self.post(f"/api/v1/storage/vectors/{db}/{name}/search", json={"query_vec": query_vec, "top_k": top_k, "filter": filter})

    # ── KV (Valkey) ──
    async def kv_set(self, key: str, value: str, ttl: int | None = None) -> dict:
        return await self.put(f"/api/v1/storage/kv/{key}", json={"value": value, "ttl": ttl})

    async def kv_get(self, key: str) -> dict:
        return await self.get(f"/api/v1/storage/kv/{key}")

    async def kv_delete(self, key: str) -> dict:
        return await self.delete(f"/api/v1/storage/kv/{key}")

    async def kv_scan(self, pattern: str = "*", limit: int = 1000) -> dict:
        return await self.get("/api/v1/storage/kv/", params={"pattern": pattern, "limit": limit})

    # ── Graph ──
    async def graph_add_node(self, graph: str, node_id: str, label: str, properties: dict, tenant_id: str = "default") -> dict:
        return await self.post(f"/api/v1/storage/graph/{graph}/nodes", json={"node_id": node_id, "label": label, "properties": properties, "tenant_id": tenant_id})

    async def graph_add_edge(self, graph: str, edge_id: str, src: str, dst: str, rel: str, properties: dict = None, tenant_id: str = "default") -> dict:
        return await self.post(f"/api/v1/storage/graph/{graph}/edges", json={"edge_id": edge_id, "src": src, "dst": dst, "rel": rel, "properties": properties or {}, "tenant_id": tenant_id})

    async def graph_query_nodes(self, graph: str, tenant_id: str = "default", label: str | None = None) -> dict:
        params = {"tenant_id": tenant_id}
        if label: params["label"] = label
        return await self.get(f"/api/v1/storage/graph/{graph}/nodes", params=params)

    async def graph_query_edges(self, graph: str, src: str, tenant_id: str = "default") -> dict:
        return await self.get(f"/api/v1/storage/graph/{graph}/edges", params={"src": src, "tenant_id": tenant_id})

    async def graph_delete_node(self, graph: str, node_id: str, tenant_id: str = "default") -> dict:
        return await self.delete(f"/api/v1/storage/graph/{graph}/nodes/{node_id}", params={"tenant_id": tenant_id})

    # ── SQL (DuckDB) ──
    async def sql_execute(self, sql: str, tables: dict | None = None) -> dict:
        return await self.post("/api/v1/compute/sql/", json={"sql": sql, "tables": tables})

    # ── Jobs ──
    async def job_submit(self, func: str, args: dict = None) -> dict:
        return await self.post("/api/v1/jobs", json={"skill_ref": func, "inputs": args or {}})

    async def job_status(self, job_id: str) -> dict:
        return await self.get(f"/api/v1/jobs/{job_id}")

    async def job_result(self, job_id: str) -> dict:
        return await self.get(f"/api/v1/jobs/{job_id}/result")

    # ── Embedding ──
    async def embed(self, texts: list[str]) -> dict:
        resp = await self.client.post(
            f"{self._ms_url}/v1/embeddings",
            headers={"Authorization": f"Bearer {self._ms_key}"},
            json={"model": os.environ.get("EMBEDDING_PROFILE", "meeting-embedding"), "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()
        return {"vectors": [item["embedding"] for item in data["data"]]}

    # ── Memory (mem0-style) ──
    async def memory_add(self, messages: list[dict], metadata: dict | None = None,
                         infer: bool = True, expiration_date: str | None = None,
                         run_id: str | None = None) -> dict:
        return await self.post("/api/v1/cognitive/memory/add", json={
            "messages": messages, "metadata": metadata, "infer": infer,
            "expiration_date": expiration_date, "run_id": run_id})

    async def memory_search(self, query: str, filters: dict | None = None,
                            top_k: int = 10, threshold: float = 0.1,
                            run_id: str | None = None) -> dict:
        return await self.post("/api/v1/cognitive/memory/search", json={
            "query": query, "filters": filters, "top_k": top_k,
            "threshold": threshold, "run_id": run_id})

    async def memory_get(self, memory_id: str) -> dict:
        return await self.get(f"/api/v1/cognitive/memory/{memory_id}")

    async def memory_list(self, filters: dict | None = None, page: int = 1,
                          page_size: int = 50, run_id: str | None = None) -> dict:
        return await self.post("/api/v1/cognitive/memory/list", json={
            "filters": filters, "page": page, "page_size": page_size, "run_id": run_id})

    async def memory_update(self, memory_id: str, content: str) -> dict:
        return await self.put(f"/api/v1/cognitive/memory/{memory_id}", json={"content": content})

    async def memory_delete(self, memory_id: str) -> dict:
        return await self.delete(f"/api/v1/cognitive/memory/{memory_id}")

    async def memory_clear(self, filters: dict | None = None, run_id: str | None = None) -> dict:
        return await self.post("/api/v1/cognitive/memory/clear", json={"filters": filters, "run_id": run_id})

    async def memory_history(self, memory_id: str) -> dict:
        return await self.get(f"/api/v1/cognitive/memory/{memory_id}/history")

    # ── Metadata ──
    async def tenant_create(self, tenant_id: str, name: str) -> dict:
        return await self.post("/api/v1/metadata/tenants", json={"tenant_id": tenant_id, "name": name})

    async def tenant_list(self) -> dict:
        return await self.get("/api/v1/metadata/tenants")

    async def tenant_update(self, tenant_id: str, name: str | None = None, status: str | None = None) -> dict:
        body = {}
        if name: body["name"] = name
        if status: body["status"] = status
        return await self.put(f"/api/v1/metadata/tenants/{tenant_id}", json=body)

    async def tenant_delete(self, tenant_id: str) -> dict:
        return await self.delete(f"/api/v1/metadata/tenants/{tenant_id}")

    async def user_create(self, username: str, tenant_id: str, role: str = "user") -> dict:
        return await self.post("/api/v1/metadata/users", json={"username": username, "tenant_id": tenant_id, "role": role})

    async def user_list(self, tenant_id: str | None = None) -> dict:
        params = {}
        if tenant_id: params["tenant_id"] = tenant_id
        return await self.get("/api/v1/metadata/users", params=params)

    async def user_update(self, user_id: str, username: str | None = None, role: str | None = None, status: str | None = None) -> dict:
        body = {}
        if username: body["username"] = username
        if role: body["role"] = role
        if status: body["status"] = status
        return await self.put(f"/api/v1/metadata/users/{user_id}", json=body)

    async def user_delete(self, user_id: str) -> dict:
        return await self.delete(f"/api/v1/metadata/users/{user_id}")

    async def token_issue(self, agent_id: str, tenant_id: str, scopes: list[str]) -> dict:
        return await self.post("/api/v1/metadata/tokens", json={"agent_id": agent_id, "tenant_id": tenant_id, "scopes": scopes})

    async def token_list(self, tenant_id: str | None = None, agent_id: str | None = None) -> dict:
        params = {}
        if tenant_id: params["tenant_id"] = tenant_id
        if agent_id: params["agent_id"] = agent_id
        return await self.get("/api/v1/metadata/tokens", params=params)

    async def token_revoke(self, token: str) -> dict:
        return await self.delete(f"/api/v1/metadata/tokens/{token}")

    async def asset_type_register(self, type: str, yaml_def: str) -> dict:
        return await self.post("/api/v1/metadata/asset-types", json={"type": type, "yaml_def": yaml_def})

    async def asset_type_list(self) -> dict:
        return await self.get("/api/v1/metadata/asset-types")

    async def asset_type_unregister(self, type: str) -> dict:
        return await self.delete(f"/api/v1/metadata/asset-types/{type}")
