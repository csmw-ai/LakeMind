from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from .base import ASRStatus, ASRResult
from .sensevoice_backend import SenseVoiceBackend

logger = logging.getLogger(__name__)


class ASRRouter:
    def __init__(self, total_concurrency: int = 2):
        self._backends: dict[str, Any] = {}
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._lock = threading.Lock()
        self._global_concurrency = total_concurrency
        self._global_sem: asyncio.Semaphore | None = None

    def _ensure_global_sem(self):
        if self._global_sem is None:
            self._global_sem = asyncio.Semaphore(self._global_concurrency)

    def register(self, model_id: str, model_path: str, config: dict | None = None):
        cfg = config or {}
        provider = cfg.get("provider", "sensevoice-funasr")
        concurrency = cfg.get("concurrency", 1)

        if provider in ("sensevoice-onnx", "sensevoice-funasr"):
            backend = SenseVoiceBackend(model_id, model_path, cfg)
        else:
            raise ValueError(f"Unsupported ASR provider: {provider}")

        backend.register()
        with self._lock:
            self._backends[model_id] = backend
            self._semaphores[model_id] = asyncio.Semaphore(concurrency)
        logger.info(
            "ASR registered: %s (provider=%s, concurrency=%d, status=%s)",
            model_id, provider, concurrency, backend.status.value,
        )

    def unregister(self, model_id: str):
        with self._lock:
            self._backends.pop(model_id, None)
            self._semaphores.pop(model_id, None)
            logger.info("ASR unregistered: %s", model_id)

    def list_registered(self) -> list[str]:
        return list(self._backends.keys())

    def list_loaded(self) -> list[str]:
        return [mid for mid, b in self._backends.items() if b.ready()]

    def get_status(self, model_id: str) -> ASRStatus:
        backend = self._backends.get(model_id)
        return backend.status if backend else ASRStatus.MISSING

    def get_error(self, model_id: str) -> str | None:
        backend = self._backends.get(model_id)
        return backend.error if backend else None

    def get_provider(self, model_id: str) -> str:
        backend = self._backends.get(model_id)
        return backend.provider if backend else "unknown"

    def health(self) -> bool:
        return any(b.ready() for b in self._backends.values())

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        model_id: str,
        filename: str = "audio.wav",
        language: str | None = None,
    ) -> ASRResult:
        backend = self._backends.get(model_id)
        if not backend:
            raise RuntimeError(f"ASR model not registered: {model_id}")
        return backend.transcribe_bytes(audio_bytes, filename=filename, language=language)

    async def async_transcribe(
        self,
        audio_bytes: bytes,
        model_id: str,
        filename: str = "audio.wav",
        language: str | None = None,
    ) -> ASRResult:
        self._ensure_global_sem()
        backend = self._backends.get(model_id)
        if not backend:
            raise RuntimeError(f"ASR model not registered: {model_id}")

        model_sem = self._semaphores.get(model_id, asyncio.Semaphore(1))
        async with self._global_sem:
            async with model_sem:
                return await asyncio.to_thread(
                    backend.transcribe_bytes,
                    audio_bytes,
                    filename=filename,
                    language=language,
                )
