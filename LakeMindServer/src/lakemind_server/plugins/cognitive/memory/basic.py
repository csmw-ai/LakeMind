from __future__ import annotations
import json
import os
import time
import uuid
import hashlib
import threading
import psycopg2
import pyarrow as pa
import httpx


_EXTRACT_PROMPT = """Extract key facts from the following messages. Return a JSON object with a "memory" array. Each element has a "text" field with one concise factual statement.

Messages:
{messages_text}

Return only JSON, no markdown."""


class BasicMemory:
    def __init__(self, host: str = "lakemind-postgres", port: int = 5432,
                 db: str = "lakemind", user: str = "lakemind",
                 password: str = "lakemind_pass",
                 kv_host: str = "lakemind-valkey", kv_port: int = 6379,
                 lance_uri: str = "/data/lance",
                 embedding_model: str = "jinaai/jina-embeddings-v2-base-zh",
                 embedding_dim: int = 768,
                 model_serving_url: str = "http://lakemind-model-serving:10824",
                 model_serving_api_key: str = "lakemind-modelserving-key",
                 llm_model: str = "deepseek-v4-flash",
                 **kwargs):
        self._dsn = f"host={host} port={port} dbname={db} user={user} password={password}"
        self._kv_host = kv_host
        self._kv_port = kv_port
        self._lance_uri = lance_uri
        self._embed_dim = embedding_dim
        self._embed_model_name = embedding_model
        self._model_serving_url = model_serving_url.rstrip("/")
        self._model_serving_api_key = model_serving_api_key
        self._llm_model = llm_model
        self._redis = None
        self._llm = None
        self._history_ready = False
        self._lock = threading.Lock()
        self._lance_conns: dict = {}
        self._http_client = httpx.Client(timeout=30.0)
        self._ray_embed_handle = None
        self._ray_address = os.environ.get("LAKEMIND_RAY_ADDRESS", "ray-head:6379")

    def set_llm(self, llm):
        self._llm = llm

    def _ensure_redis(self):
        if self._redis is None:
            import redis
            self._redis = redis.Redis(host=self._kv_host, port=self._kv_port, decode_responses=True)

    def _embed(self, text: str) -> list[float]:
        if self._ray_embed_handle is None:
            import ray
            from ray import serve
            ray.init(address=self._ray_address, ignore_reinit_error=True)
            self._ray_embed_handle = serve.get_deployment_handle("embedding", "embedding-app")
        result = self._ray_embed_handle.embed.remote([text]).result()
        return result[0]

    def _ensure_history(self):
        if not self._history_ready:
            try:
                with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS memory_history (
                            id SERIAL PRIMARY KEY,
                            memory_id VARCHAR(64) NOT NULL,
                            agent_id VARCHAR(128) NOT NULL,
                            tenant_id VARCHAR(128) NOT NULL,
                            old_memory TEXT,
                            new_memory TEXT,
                            event VARCHAR(16) NOT NULL,
                            created_at TIMESTAMP DEFAULT NOW(),
                            is_deleted INT DEFAULT 0
                        )
                    """)
                    conn.commit()
                self._history_ready = True
            except Exception:
                pass

    def _record_history(self, agent_id: str, tenant_id: str, memory_id: str,
                        old_memory: str | None, new_memory: str | None, event: str):
        self._ensure_history()
        try:
            with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO memory_history (memory_id, agent_id, tenant_id, old_memory, new_memory, event) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (memory_id, agent_id, tenant_id, old_memory, new_memory, event)
                )
                conn.commit()
        except Exception:
            pass

    def _connect_lance(self, tenant_id: str, agent_id: str):
        import lancedb
        db_name = f"memory_{tenant_id}"
        if db_name not in self._lance_conns:
            self._lance_conns[db_name] = lancedb.connect(f"{self._lance_uri}/{db_name}")
        tbl_name = f"mem_{agent_id}"
        return self._lance_conns[db_name], tbl_name

    def _extract_facts(self, messages: list[dict]) -> list[str]:
        if not self._llm and not self._model_serving_url:
            texts = []
            for m in messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                if role != "system" and content:
                    texts.append(content)
            return texts

        messages_text = "\n".join(
            f"[{m.get('role', 'user')}]: {m.get('content', '')}" for m in messages
        )
        prompt = _EXTRACT_PROMPT.format(messages_text=messages_text)
        try:
            if self._llm:
                resp = self._llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0, max_tokens=512
                )
                content = resp.get("content", "")
            else:
                r = self._http_client.post(
                    f"{self._model_serving_url}/v1/chat/completions",
                    json={"model": self._llm_model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.0, "max_tokens": 512},
                    headers={"Authorization": f"Bearer {self._model_serving_api_key}"},
                )
                r.raise_for_status()
                result = r.json()
                content = result["choices"][0]["message"]["content"]
            import re
            content = re.sub(r"```json\s*", "", content)
            content = re.sub(r"```\s*$", "", content.strip())
            data = json.loads(content)
            facts = [m.get("text", "") for m in data.get("memory", []) if m.get("text")]
            return facts if facts else [messages_text]
        except Exception:
            texts = []
            for m in messages:
                content = m.get("content", "")
                if content:
                    texts.append(content)
            return texts

    def add(self, agent_id: str, tenant_id: str, messages: list[dict],
            metadata: dict | None = None, infer: bool = True,
            expiration_date: str | None = None,
            run_id: str | None = None) -> dict:
        if infer:
            facts = self._extract_facts(messages)
        else:
            facts = [m.get("content", "") for m in messages if m.get("content")]

        if not facts:
            return {"results": []}

        existing_hashes = set()
        with self._lock:
            try:
                with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
                    cur.execute(
                        "CREATE TABLE IF NOT EXISTS memory_hash_index ("
                        "tenant_id TEXT, agent_id TEXT, content_hash TEXT, memory_id TEXT, "
                        "UNIQUE(tenant_id, agent_id, content_hash))"
                    )
                    cur.execute(
                        "SELECT content_hash FROM memory_hash_index WHERE tenant_id = %s AND agent_id = %s",
                        (tenant_id, agent_id),
                    )
                    existing_hashes = {r[0] for r in cur.fetchall()}
            except Exception:
                pass

        results = []
        rows = []
        now = int(time.time())
        for text in facts:
            h = hashlib.md5(text.encode()).hexdigest()
            if h in existing_hashes:
                continue
            existing_hashes.add(h)
            memory_id = str(uuid.uuid4())
            vec = self._embed(text)
            row = {
                "memory_id": memory_id,
                "content": text,
                "hash": h,
                "metadata": json.dumps(metadata or {}, ensure_ascii=False),
                "run_id": run_id or "",
                "expiration_date": expiration_date or "",
                "vector": vec,
                "created_at": now,
                "updated_at": now,
            }
            rows.append(row)
            results.append({"id": memory_id, "memory": text, "event": "ADD"})
            self._record_history(agent_id, tenant_id, memory_id, None, text, "ADD")

        if rows:
            table_data = pa.Table.from_pylist(rows)
            with self._lock:
                conn, tbl_name = self._connect_lance(tenant_id, agent_id)
                if tbl_name in conn.table_names():
                    conn.open_table(tbl_name).add(table_data)
                else:
                    conn.create_table(tbl_name, data=table_data)
            try:
                with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
                    for r in rows:
                        cur.execute(
                            "INSERT INTO memory_hash_index (tenant_id, agent_id, content_hash, memory_id) "
                            "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                            (tenant_id, agent_id, r["hash"], r["memory_id"]),
                        )
            except Exception:
                pass

        return {"results": results}

    def search(self, agent_id: str, tenant_id: str, query: str,
               filters: dict | None = None, top_k: int = 10,
               threshold: float = 0.1, run_id: str | None = None) -> list[dict]:
        results = []
        qvec = self._embed(query)
        with self._lock:
            try:
                conn, tbl_name = self._connect_lance(tenant_id, agent_id)
                if tbl_name not in conn.table_names():
                    raw = []
                else:
                    tbl = conn.open_table(tbl_name)
                    q = tbl.search(qvec).metric("cosine").limit(top_k)
                    raw = q.to_list()
            except Exception:
                raw = []
        for r in raw:
            dist = r.get("_distance", 1.0)
            score = max(0.0, 1.0 - dist)
            if score < threshold:
                continue
            if run_id and r.get("run_id", "") != run_id:
                continue
            if filters:
                try:
                    meta = json.loads(r.get("metadata", "{}"))
                except Exception:
                    meta = {}
                skip = False
                for k, v in filters.items():
                    if meta.get(k) != v:
                        skip = True
                        break
                if skip:
                    continue
            results.append({
                "id": r.get("memory_id"),
                "memory": r.get("content"),
                "score": score,
                "metadata": json.loads(r.get("metadata", "{}")) if r.get("metadata") else {},
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            })

        try:
            self._ensure_redis()
            for key in self._redis.scan_iter(match=f"{tenant_id}:{agent_id}:short:*"):
                val = self._redis.get(key)
                if val:
                    d = json.loads(val)
                    if query.lower() in d.get("content", "").lower():
                        results.append({"id": key, "memory": d.get("content"), "score": 0.5,
                                        "metadata": {}, "created_at": d.get("ts", 0)})
        except Exception:
            pass

        return results[:top_k]

    def get(self, agent_id: str, tenant_id: str, memory_id: str) -> dict | None:
        with self._lock:
            try:
                conn, tbl_name = self._connect_lance(tenant_id, agent_id)
                if tbl_name not in conn.table_names():
                    return None
                tbl = conn.open_table(tbl_name)
                rows = tbl.search().where(f"memory_id = '{memory_id}'").limit(1).to_list()
            except Exception:
                return None
        if not rows:
            return None
        r = rows[0]
        return {
            "id": r.get("memory_id"),
            "memory": r.get("content"),
            "hash": r.get("hash"),
            "metadata": json.loads(r.get("metadata", "{}")) if r.get("metadata") else {},
            "run_id": r.get("run_id", ""),
            "expiration_date": r.get("expiration_date", ""),
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
        }

    def list_all(self, agent_id: str, tenant_id: str, filters: dict | None = None,
                 page: int = 1, page_size: int = 50,
                 run_id: str | None = None) -> dict:
        with self._lock:
            try:
                conn, tbl_name = self._connect_lance(tenant_id, agent_id)
                if tbl_name not in conn.table_names():
                    return {"count": 0, "results": []}
                tbl = conn.open_table(tbl_name)
                all_rows = tbl.to_arrow().to_pylist()
            except Exception:
                return {"count": 0, "results": []}
        if run_id:
            all_rows = [r for r in all_rows if r.get("run_id", "") == run_id]
        if filters:
            filtered = []
            for r in all_rows:
                try:
                    meta = json.loads(r.get("metadata", "{}"))
                except Exception:
                    meta = {}
                if all(meta.get(k) == v for k, v in filters.items()):
                    filtered.append(r)
            all_rows = filtered
        all_rows.sort(key=lambda r: r.get("created_at", 0), reverse=True)
        total = len(all_rows)
        start = (page - 1) * page_size
        end = start + page_size
        page_rows = all_rows[start:end]
        results = [
            {
                "id": r.get("memory_id"),
                "memory": r.get("content"),
                "metadata": json.loads(r.get("metadata", "{}")) if r.get("metadata") else {},
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
            for r in page_rows
        ]
        return {"count": total, "page": page, "page_size": page_size, "results": results}

    def update(self, agent_id: str, tenant_id: str, memory_id: str, content: str) -> dict:
        vec = self._embed(content)
        now = int(time.time())
        with self._lock:
            try:
                conn, tbl_name = self._connect_lance(tenant_id, agent_id)
                if tbl_name not in conn.table_names():
                    return {"status": "not_found"}
                tbl = conn.open_table(tbl_name)
                rows = tbl.search().where(f"memory_id = '{memory_id}'").limit(1).to_list()
                if not rows:
                    return {"status": "not_found"}
                old_content = rows[0].get("content")
                tbl.delete(f"memory_id = '{memory_id}'")
                updated_row = pa.Table.from_pylist([{
                    **rows[0],
                    "content": content,
                    "vector": vec,
                    "updated_at": now,
                }])
                tbl.add(updated_row)
            except Exception as e:
                return {"status": "error", "detail": str(e)}
        self._record_history(agent_id, tenant_id, memory_id, old_content, content, "UPDATE")
        return {"status": "ok", "id": memory_id, "memory": content}

    def delete(self, agent_id: str, tenant_id: str, memory_id: str) -> dict:
        with self._lock:
            try:
                conn, tbl_name = self._connect_lance(tenant_id, agent_id)
                if tbl_name not in conn.table_names():
                    return {"status": "not_found"}
                tbl = conn.open_table(tbl_name)
                rows = tbl.search().where(f"memory_id = '{memory_id}'").limit(1).to_list()
                if not rows:
                    return {"status": "not_found"}
                old_content = rows[0].get("content")
                tbl.delete(f"memory_id = '{memory_id}'")
            except Exception as e:
                return {"status": "error", "detail": str(e)}
        self._record_history(agent_id, tenant_id, memory_id, old_content, None, "DELETE")
        return {"status": "ok", "deleted": memory_id}

    def clear(self, agent_id: str, tenant_id: str, filters: dict | None = None,
              run_id: str | None = None) -> dict:
        deleted = 0
        to_delete = []
        with self._lock:
            try:
                conn, tbl_name = self._connect_lance(tenant_id, agent_id)
                if tbl_name not in conn.table_names():
                    return {"status": "ok", "deleted": 0}
                tbl = conn.open_table(tbl_name)
                if run_id and not filters:
                    before = tbl.count_rows()
                    tbl.delete(f"run_id = '{run_id}'")
                    deleted = before - tbl.count_rows()
                else:
                    all_rows = tbl.to_arrow().to_pylist()
                    to_delete = []
                    for r in all_rows:
                        if run_id and r.get("run_id", "") != run_id:
                            continue
                        if filters:
                            try:
                                meta = json.loads(r.get("metadata", "{}"))
                            except Exception:
                                meta = {}
                            if not all(meta.get(k) == v for k, v in filters.items()):
                                continue
                        to_delete.append(r)
                    for r in to_delete:
                        mid = r.get("memory_id")
                        tbl.delete(f"memory_id = '{mid}'")
                        deleted += 1
            except Exception:
                pass

        for r in to_delete:
            self._record_history(agent_id, tenant_id, r.get("memory_id"), r.get("content"), None, "DELETE")

        try:
            self._ensure_redis()
            for key in self._redis.scan_iter(match=f"{tenant_id}:{agent_id}:short:*"):
                self._redis.delete(key)
                deleted += 1
        except Exception:
            pass
        return {"status": "ok", "deleted": deleted}

    def history(self, agent_id: str, tenant_id: str, memory_id: str) -> list[dict]:
        self._ensure_history()
        try:
            with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT memory_id, old_memory, new_memory, event, created_at, is_deleted "
                    "FROM memory_history WHERE memory_id = %s AND agent_id = %s AND tenant_id = %s "
                    "ORDER BY created_at DESC",
                    (memory_id, agent_id, tenant_id)
                )
                rows = cur.fetchall()
            return [
                {
                    "memory_id": r[0],
                    "old_memory": r[1],
                    "new_memory": r[2],
                    "event": r[3],
                    "created_at": r[4].isoformat() if r[4] else None,
                    "is_deleted": r[5],
                }
                for r in rows
            ]
        except Exception:
            return []

    def health(self) -> bool:
        try:
            with psycopg2.connect(self._dsn) as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            return False
