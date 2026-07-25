from __future__ import annotations

import logging

from fastapi import FastAPI

from .config import load_config
from .gateway import ModelGateway
from .registry import ModelRegistry
from .services.embedding import EmbeddingManager
from .services.asr import ASRManager
from .api import chat, embeddings, audio, models, health, profiles

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    cfg = load_config()

    app = FastAPI(title="LakeMindModelServing", version="0.2.0")
    app.state.api_key = cfg.server.api_key

    embedding_mgr = EmbeddingManager(cache_dir=cfg.embedding.built_in.cache_dir)
    app.state.embedding_mgr = embedding_mgr

    asr_mgr = ASRManager(total_concurrency=int(getattr(cfg.asr, "total_concurrency", 2)))
    app.state.asr_mgr = asr_mgr

    gateway = ModelGateway(providers=[], gateway_config={
        "default_chat_model": cfg.gateway.default_chat_model,
        "default_embed_model": cfg.gateway.default_embed_model,
        "fallback": cfg.gateway.fallback,
        "cache": cfg.gateway.cache,
    })
    app.state.gateway = gateway

    dsn = f"host={cfg.registry.host} port={cfg.registry.port} dbname={cfg.registry.db} user={cfg.registry.user} password={cfg.registry.password}"
    registry = ModelRegistry(dsn=dsn, gateway=gateway,
                             embedding_mgr=embedding_mgr, asr_mgr=asr_mgr)
    app.state.registry = registry

    if registry.is_empty():
        logger.info("DB empty, seeding from yaml...")
        yaml_dict = _config_to_dict(cfg)
        registry.seed_from_yaml(yaml_dict)
    else:
        logger.info("DB has models, loading from DB...")

    registry.load_all_enabled()

    app.include_router(chat.router, tags=["chat"])
    app.include_router(embeddings.router, tags=["embeddings"])
    app.include_router(audio.router, tags=["audio"])
    app.include_router(models.router, tags=["models"])
    app.include_router(profiles.router, tags=["profiles"])
    app.include_router(health.router, tags=["health"])

    return app


def _config_to_dict(cfg) -> dict:
    import json
    def serialize(obj):
        if hasattr(obj, "__dict__"):
            return {k: serialize(v) for k, v in obj.__dict__.items()}
        if isinstance(obj, list):
            return [serialize(v) for v in obj]
        return obj

    return {
        "llm_providers": serialize(cfg.llm_providers),
        "embedding": {"built_in": serialize(cfg.embedding.built_in)},
        "asr": {"built_in": serialize(cfg.asr.built_in), "total_concurrency": cfg.asr.total_concurrency},
        "gateway": serialize(cfg.gateway),
    }
