"""Embedding Ray Serve deployment."""
from __future__ import annotations

import logging
import os

from ray import serve

logger = logging.getLogger(__name__)


@serve.deployment
class EmbeddingDeployment:
    def __init__(self):
        from fastembed import TextEmbedding

        model_name = os.environ.get("EMBEDDING_MODEL", "jinaai/jina-embeddings-v2-base-zh")
        cache_dir = os.environ.get("EMBEDDING_CACHE_DIR", "/data/fastembed_cache")
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
        logger.info("EmbeddingDeployment loaded: %s", model_name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [[float(x) for x in v] for v in self._model.embed(texts)]
