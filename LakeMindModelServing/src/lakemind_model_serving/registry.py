from __future__ import annotations

import json
import logging
import os
import base64
import threading
import time
import uuid
import psycopg2
import httpx

logger = logging.getLogger(__name__)


_MASTER_KEY = None
_MASTER_KEY_LOADED = False


def _get_master_key():
    global _MASTER_KEY, _MASTER_KEY_LOADED
    if not _MASTER_KEY_LOADED:
        key_b64 = os.environ.get("LAKEMIND_MASTER_KEY", "")
        if key_b64:
            raw = base64.b64decode(key_b64)
            if len(raw) == 32:
                _MASTER_KEY = raw
        _MASTER_KEY_LOADED = True
    return _MASTER_KEY


def _encrypt_api_key(plaintext: str) -> str:
    if not plaintext:
        return ""
    key = _get_master_key()
    if not key:
        return plaintext
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(key)
    iv = os.urandom(12)
    ct = aesgcm.encrypt(iv, plaintext.encode(), b"")
    return "enc:" + base64.b64encode(iv + ct).decode()


def _decrypt_api_key(stored: str) -> str:
    if not stored or not stored.startswith("enc:"):
        return stored or ""
    key = _get_master_key()
    if not key:
        return ""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(key)
    raw = base64.b64decode(stored[4:])
    iv, ct = raw[:12], raw[12:]
    return aesgcm.decrypt(iv, ct, b"").decode()


def _ulid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:26]}"


class ModelRegistry:
    """ms_models + ms_model_profiles CRUD with hot-reload to runtime engines."""

    def __init__(self, dsn: str, gateway=None, embedding_mgr=None, asr_mgr=None):
        self._dsn = dsn
        self._gateway = gateway
        self._embedding_mgr = embedding_mgr
        self._asr_mgr = asr_mgr
        self._lock = threading.Lock()
        self._ensure_tables()

    def _conn(self):
        return psycopg2.connect(self._dsn)

    def _ensure_tables(self):
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ms_models (
                    model_id         TEXT PRIMARY KEY,
                    name             TEXT NOT NULL UNIQUE,
                    model_type       TEXT NOT NULL,
                    provider         TEXT NOT NULL,
                    source           TEXT NOT NULL DEFAULT 'external',
                    litellm_model    TEXT,
                    api_key          TEXT,
                    base_url         TEXT,
                    model_path       TEXT,
                    model_config     JSONB DEFAULT '{}',
                    capabilities     JSONB DEFAULT '[]',
                    context_length   INTEGER,
                    embedding_dim    INTEGER,
                    status           TEXT NOT NULL DEFAULT 'enabled',
                    health_status    TEXT NOT NULL DEFAULT 'unknown',
                    priority         INTEGER NOT NULL DEFAULT 100,
                    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ms_models_type ON ms_models(model_type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ms_models_status ON ms_models(status)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ms_model_profiles (
                    profile_id         TEXT PRIMARY KEY,
                    name               TEXT NOT NULL UNIQUE,
                    model_type         TEXT NOT NULL,
                    model_id           TEXT NOT NULL REFERENCES ms_models(model_id),
                    fallback_model_id  TEXT REFERENCES ms_models(model_id),
                    tenant_id          TEXT,
                    description        TEXT,
                    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ms_profiles_name ON ms_model_profiles(name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ms_profiles_tenant ON ms_model_profiles(tenant_id)")
            conn.commit()

    # ── helpers ──

    def _row_to_dict(self, row, columns):
        d = dict(zip(columns, row))
        if "api_key" in d and d["api_key"]:
            d["api_key"] = _decrypt_api_key(d["api_key"])
        return d

    def _query(self, sql, params=None, one=False):
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, params or ())
            cols = [desc[0] for desc in cur.description] if cur.description else []
            if one:
                row = cur.fetchone()
                return self._row_to_dict(row, cols) if row else None
            return [self._row_to_dict(r, cols) for r in cur.fetchall()]

    def _execute(self, sql, params=None):
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, params or ())
            conn.commit()

    # ── model CRUD ──

    def is_empty(self) -> bool:
        return self._query("SELECT COUNT(*) AS cnt FROM ms_models", one=True)["cnt"] == 0

    def list_models(self, model_type: str | None = None) -> list[dict]:
        if model_type:
            return self._query("SELECT * FROM ms_models WHERE model_type = %s ORDER BY priority, created_at", (model_type,))
        return self._query("SELECT * FROM ms_models ORDER BY priority, created_at")

    def get_model(self, model_id: str) -> dict | None:
        return self._query("SELECT * FROM ms_models WHERE model_id = %s", (model_id,), one=True)

    def get_model_by_name(self, name: str) -> dict | None:
        return self._query("SELECT * FROM ms_models WHERE name = %s", (name,), one=True)

    def create_model(self, name: str, model_type: str, provider: str,
                     source: str = "external", litellm_model: str = "",
                     api_key: str = "", base_url: str = "",
                     model_path: str = "", model_config: dict | None = None,
                     capabilities: list | None = None, context_length: int | None = None,
                     embedding_dim: int | None = None, priority: int = 100,
                     status: str = "enabled") -> dict:
        model_id = _ulid("mdl")
        enc_key = _encrypt_api_key(api_key)
        self._execute(
            """INSERT INTO ms_models
               (model_id, name, model_type, provider, source, litellm_model, api_key, base_url,
                model_path, model_config, capabilities, context_length, embedding_dim, priority, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (model_id, name, model_type, provider, source, litellm_model, enc_key, base_url,
             model_path, json.dumps(model_config or {}), json.dumps(capabilities or []),
             context_length, embedding_dim, priority, status),
        )
        model = self.get_model(model_id)
        if model and model["status"] == "enabled":
            self._hot_load(model)
        return model

    def update_model(self, model_id: str, **fields) -> dict:
        existing = self.get_model(model_id)
        if not existing:
            raise ValueError("MODEL_NOT_FOUND")
        allowed = {"name", "model_type", "provider", "source", "litellm_model", "api_key",
                    "base_url", "model_path", "model_config", "capabilities",
                    "context_length", "embedding_dim", "priority", "status"}
        sets, params = [], []
        for k, v in fields.items():
            if k not in allowed or v is None:
                continue
            if k == "api_key":
                v = _encrypt_api_key(v)
            if k in ("model_config", "capabilities"):
                v = json.dumps(v)
            sets.append(f"{k} = %s")
            params.append(v)
        if not sets:
            return existing
        sets.append("updated_at = now()")
        params.append(model_id)
        self._execute(f"UPDATE ms_models SET {', '.join(sets)} WHERE model_id = %s", tuple(params))

        self._hot_unload(model_id)
        model = self.get_model(model_id)
        if model and model["status"] == "enabled":
            self._hot_load(model)
        return model

    def delete_model(self, model_id: str) -> dict:
        model = self.get_model(model_id)
        if not model:
            raise ValueError("MODEL_NOT_FOUND")
        self._hot_unload(model_id)
        self._execute("DELETE FROM ms_model_profiles WHERE model_id = %s OR fallback_model_id = %s", (model_id, model_id))
        self._execute("DELETE FROM ms_models WHERE model_id = %s", (model_id,))
        return model

    def enable_model(self, model_id: str) -> dict:
        self._execute("UPDATE ms_models SET status = 'enabled', updated_at = now() WHERE model_id = %s", (model_id,))
        model = self.get_model(model_id)
        if model:
            self._hot_load(model)
        return model

    def disable_model(self, model_id: str) -> dict:
        self._hot_unload(model_id)
        self._execute("UPDATE ms_models SET status = 'disabled', updated_at = now() WHERE model_id = %s", (model_id,))
        return self.get_model(model_id)

    def test_model(self, model_id: str) -> dict:
        model = self.get_model(model_id)
        if not model:
            raise ValueError("MODEL_NOT_FOUND")

        result = {
            "model_id": model_id, "name": model["name"],
            "model_type": model["model_type"], "source": model["source"],
            "success": False, "latency_ms": None, "error": None, "response_preview": None,
        }

        try:
            t0 = time.time()
            if model["model_type"] == "chat":
                payload = {"model": model["name"], "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
                headers = {"Authorization": f"Bearer {model.get('api_key', '')}", "Content-Type": "application/json"}
                url = model.get("base_url", "")
                if url and "/v1/chat" not in url:
                    url = url.rstrip("/") + "/v1/chat/completions"
                r = httpx.post(url or "", json=payload, headers=headers, timeout=30)
                result["status_code"] = r.status_code
                result["success"] = r.status_code < 400
                result["response_preview"] = r.text[:500]
            elif model["model_type"] == "embedding" and model["source"] == "local":
                if self._embedding_mgr:
                    vecs, dim = self._embedding_mgr.embed(["test"], model["name"])
                    result["success"] = len(vecs) > 0 and dim > 0
                    result["response_preview"] = f"dim={dim}"
                else:
                    result["error"] = "EmbeddingManager not available"
            elif model["model_type"] == "asr" and model["source"] == "local":
                status = self._asr_mgr.get_status(model["name"]) if self._asr_mgr else None
                result["success"] = status is not None
                result["response_preview"] = f"status={status}"
            else:
                result["success"] = True
                result["response_preview"] = "external model, skip probe"
            result["latency_ms"] = int((time.time() - t0) * 1000)
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"

        new_health = "healthy" if result["success"] else "unhealthy"
        self._execute("UPDATE ms_models SET health_status = %s WHERE model_id = %s", (new_health, model_id))
        result["health_status"] = new_health
        return result

    # ── hot reload core ──

    def _hot_load(self, model: dict):
        name = model["name"]
        mtype = model["model_type"]
        source = model["source"]

        try:
            if mtype == "chat" and self._gateway:
                self._gateway.register_model({
                    "model_id": name,
                    "litellm_model": model.get("litellm_model") or f"{model.get('provider', 'openai')}/{name}",
                    "api_key": model.get("api_key", ""),
                    "base_url": model.get("base_url", ""),
                })
            elif mtype == "embedding" and source == "local" and self._embedding_mgr:
                self._embedding_mgr.register(
                    name=name, dim=model.get("embedding_dim", 0),
                    model_path=model.get("model_path"),
                )
            elif mtype == "asr" and source == "local" and self._asr_mgr:
                cfg = model.get("model_config", {})
                if isinstance(cfg, str):
                    cfg = json.loads(cfg)
                cfg["provider"] = model.get("provider", "faster-whisper")
                self._asr_mgr.register(model_id=name, model_path=model.get("model_path", ""), config=cfg)
            elif source == "external" and self._gateway:
                self._gateway.register_model({
                    "model_id": name,
                    "litellm_model": model.get("litellm_model") or f"{model.get('provider', 'openai')}/{name}",
                    "api_key": model.get("api_key", ""),
                    "base_url": model.get("base_url", ""),
                })
            logger.info("Hot-loaded model: %s (%s/%s)", name, mtype, source)
        except Exception as e:
            logger.error("Failed to hot-load model %s: %s", name, e)

    def _hot_unload(self, model_id: str):
        model = self.get_model(model_id)
        if not model:
            return
        name = model["name"]
        mtype = model["model_type"]
        source = model["source"]

        try:
            if mtype == "chat" and self._gateway:
                self._gateway.deregister_model(name)
            elif mtype == "embedding" and source == "local" and self._embedding_mgr:
                self._embedding_mgr.unregister(name)
            elif mtype == "asr" and source == "local" and self._asr_mgr:
                self._asr_mgr.unregister(name)
            elif source == "external" and self._gateway and mtype != "chat":
                self._gateway.deregister_model(name)
            logger.info("Hot-unloaded model: %s", name)
        except Exception as e:
            logger.error("Failed to hot-unload model %s: %s", name, e)

    def load_all_enabled(self):
        models = self.list_models()
        enabled = [m for m in models if m["status"] == "enabled"]
        for model in enabled:
            self._hot_load(model)
        logger.info("Loaded %d enabled models from DB", len(enabled))

    # ── profile CRUD ──

    def list_profiles(self) -> list[dict]:
        return self._query("""
            SELECT p.*, m.name AS model_name, m.provider AS model_provider,
                   fb.name AS fallback_name
            FROM ms_model_profiles p
            JOIN ms_models m ON p.model_id = m.model_id
            LEFT JOIN ms_models fb ON p.fallback_model_id = fb.model_id
            ORDER BY p.name
        """)

    def get_profile(self, profile_id: str) -> dict | None:
        return self._query("SELECT * FROM ms_model_profiles WHERE profile_id = %s", (profile_id,), one=True)

    def create_profile(self, name: str, model_type: str, model_id: str,
                       fallback_model_id: str | None = None, tenant_id: str | None = None,
                       description: str | None = None) -> dict:
        profile_id = _ulid("prf")
        self._execute(
            """INSERT INTO ms_model_profiles
               (profile_id, name, model_type, model_id, fallback_model_id, tenant_id, description)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (profile_id, name, model_type, model_id, fallback_model_id, tenant_id, description),
        )
        return self.get_profile(profile_id)

    def update_profile(self, profile_id: str, **fields) -> dict:
        existing = self.get_profile(profile_id)
        if not existing:
            raise ValueError("PROFILE_NOT_FOUND")
        allowed = {"name", "model_type", "model_id", "fallback_model_id", "tenant_id", "description"}
        sets, params = [], []
        for k, v in fields.items():
            if k not in allowed or v is None:
                continue
            sets.append(f"{k} = %s")
            params.append(v)
        if not sets:
            return existing
        sets.append("updated_at = now()")
        params.append(profile_id)
        self._execute(f"UPDATE ms_model_profiles SET {', '.join(sets)} WHERE profile_id = %s", tuple(params))
        return self.get_profile(profile_id)

    def delete_profile(self, profile_id: str) -> dict:
        existing = self.get_profile(profile_id)
        if not existing:
            raise ValueError("PROFILE_NOT_FOUND")
        self._execute("DELETE FROM ms_model_profiles WHERE profile_id = %s", (profile_id,))
        return existing

    def resolve_profile(self, profile_name: str, tenant_id: str | None = None) -> dict | None:
        row = self._query(
            """SELECT p.*, m.name AS model_name, m.model_type, m.provider,
                      m.source, m.litellm_model, m.api_key, m.base_url,
                      m.model_path, m.embedding_dim, m.model_config
               FROM ms_model_profiles p
               JOIN ms_models m ON p.model_id = m.model_id
               WHERE p.name = %s
                 AND (p.tenant_id IS NULL OR p.tenant_id = %s)
                 AND m.status = 'enabled'""",
            (profile_name, tenant_id), one=True,
        )
        return row

    # ── seed from yaml ──

    def seed_from_yaml(self, cfg):
        imported = {"models": 0, "profiles": 0}

        for provider in cfg.get("llm_providers", []):
            api_key = provider.get("api_key", "")
            base_url = provider.get("base_url", "")
            for m in provider.get("models", []):
                name = m["id"]
                if self.get_model_by_name(name):
                    continue
                self.create_model(
                    name=name, model_type="chat", provider=provider.get("type", "openai"),
                    source="external",
                    litellm_model=m.get("litellm_model", f"{provider.get('type', 'openai')}/{name}"),
                    api_key=api_key, base_url=base_url,
                    capabilities=m.get("tags", ["chat"]),
                    context_length=m.get("context"),
                    priority=provider.get("priority", 100),
                )
                imported["models"] += 1

        emb = cfg.get("embedding", {}).get("built_in", {})
        if emb.get("enabled"):
            name = emb.get("model", "jinaai/jina-embeddings-v2-base-zh")
            if not self.get_model_by_name(name):
                self.create_model(
                    name=name, model_type="embedding", provider=emb.get("provider", "fastembed"),
                    source="local", embedding_dim=emb.get("dim", 768),
                    model_path=emb.get("cache_dir"),
                    capabilities=["embed"], priority=1,
                )
                imported["models"] += 1
            alias = "jina-embeddings-v2-base-zh"
            if alias != name and not self.get_model_by_name(alias):
                self.create_model(
                    name=alias, model_type="embedding", provider=emb.get("provider", "fastembed"),
                    source="local", embedding_dim=emb.get("dim", 768),
                    model_path=emb.get("cache_dir"),
                    capabilities=["embed"], priority=1,
                )
                imported["models"] += 1

        asr_cfg = cfg.get("asr", {}).get("built_in", {})
        if asr_cfg.get("enabled"):
            name = asr_cfg.get("model_alias", "whisper-small")
            if not self.get_model_by_name(name):
                self.create_model(
                    name=name, model_type="asr", provider=asr_cfg.get("provider", "faster-whisper"),
                    source="local", model_path=asr_cfg.get("model_path", ""),
                    model_config={
                        "provider": asr_cfg.get("provider", "sensevoice-funasr"),
                        "language": asr_cfg.get("language", "zh"),
                        "device": asr_cfg.get("device", "cpu"),
                        "compute_type": asr_cfg.get("compute_type", "int8"),
                        "cpu_threads": asr_cfg.get("cpu_threads", 4),
                        "num_workers": asr_cfg.get("num_workers", 1),
                        "concurrency": asr_cfg.get("concurrency", 2),
                        "beam_size": asr_cfg.get("beam_size", 1),
                        "vad_filter": asr_cfg.get("vad_filter", False),
                        "intra_threads": asr_cfg.get("intra_threads", 2),
                        "inter_threads": asr_cfg.get("inter_threads", 1),
                        "use_itn": asr_cfg.get("use_itn", True),
                        "vad": asr_cfg.get("vad", False),
                    },
                    capabilities=["transcribe"], priority=1,
                )
                imported["models"] += 1

        gw = cfg.get("gateway", {})
        all_models = self.list_models()
        if all_models:
            chat_model = next((m for m in all_models if m["model_type"] == "chat"), None)
            emb_model = next((m for m in all_models if m["model_type"] == "embedding"), None)
            asr_model = next((m for m in all_models if m["model_type"] == "asr"), None)

            if chat_model and not self.resolve_profile("default-chat"):
                self.create_profile(name="default-chat", model_type="chat", model_id=chat_model["model_id"])
                imported["profiles"] += 1
            if emb_model and not self.resolve_profile("default-embedding"):
                self.create_profile(name="default-embedding", model_type="embedding", model_id=emb_model["model_id"])
                imported["profiles"] += 1
            if asr_model and not self.resolve_profile("default-asr"):
                self.create_profile(name="default-asr", model_type="asr", model_id=asr_model["model_id"])
                imported["profiles"] += 1
            if asr_model and not self.resolve_profile("meeting-asr"):
                self.create_profile(name="meeting-asr", model_type="asr", model_id=asr_model["model_id"])
                imported["profiles"] += 1

            if not self.resolve_profile("default") and chat_model:
                self.create_profile(name="default", model_type="chat", model_id=chat_model["model_id"])
                imported["profiles"] += 1

        logger.info("Seeded %d models, %d profiles from yaml", imported["models"], imported["profiles"])
        return imported

    def health(self) -> bool:
        try:
            with self._conn() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            return False
