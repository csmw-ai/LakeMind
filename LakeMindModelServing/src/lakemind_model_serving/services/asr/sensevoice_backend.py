from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import time
from typing import Any

import librosa

from .base import ASRStatus, ASRResult

logger = logging.getLogger(__name__)

_TAG_PATTERN = re.compile(r"<\|[^|]+\|>")


def _clean_tags(text: str) -> str:
    return _TAG_PATTERN.sub("", text).strip()


class SenseVoiceBackend:
    def __init__(self, model_id: str, model_path: str,
                 config: dict | None = None):
        self._model_id = model_id
        self._model_path = model_path
        self._config = config or {}
        self._model: Any = None
        self._status = ASRStatus.MISSING
        self._error: str | None = None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def provider(self) -> str:
        return "sensevoice-funasr"

    @property
    def status(self) -> ASRStatus:
        return self._status

    @property
    def error(self) -> str | None:
        return self._error

    def register(self):
        self._status = ASRStatus.MISSING
        self._error = None

    def load(self):
        if self._model is not None:
            return
        self._status = ASRStatus.LOADING
        self._error = None
        try:
            from funasr import AutoModel

            self._model = AutoModel(
                model="iic/SenseVoiceSmall",
                disable_update=True,
                device=self._config.get("device", "cpu"),
                disable_pbar=True,
                trust_remote_code=False,
            )
            self._status = ASRStatus.READY
            logger.info("SenseVoice funasr loaded: %s", self._model_id)
        except Exception as exc:
            self._status = ASRStatus.FAILED
            self._error = str(exc)
            self._model = None
            raise

    def ready(self) -> bool:
        return self._status == ASRStatus.READY

    def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        use_itn: bool = True,
        initial_prompt: str | None = None,
        hotwords: list[str] | None = None,
    ) -> ASRResult:
        if self._model is None:
            self.load()
        t0 = time.time()

        lang_str = (language or self._config.get("language", "zh")).lower()
        itn = use_itn if use_itn is not None else self._config.get("use_itn", True)

        result = self._model.generate(
            input=audio_path,
            language=lang_str,
            use_itn=itn,
        )

        raw_text = result[0]["text"] if result else ""
        text = _clean_tags(raw_text)

        processing_ms = int((time.time() - t0) * 1000)

        audio, _ = librosa.load(audio_path, sr=16000, mono=True, dtype="float32")
        duration_ms = int(len(audio) / 16)

        return ASRResult(
            text=text,
            raw_text=raw_text,
            language=lang_str,
            model=self._model_id,
            provider=self.provider,
            duration_ms=duration_ms,
            processing_ms=processing_ms,
        )

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        language: str | None = None,
    ) -> ASRResult:
        tmp_dir = tempfile.mkdtemp(prefix="lakemind-sensevoice-")
        tmp_path = os.path.join(tmp_dir, filename)
        try:
            with open(tmp_path, "wb") as f:
                f.write(audio_bytes)
            return self.transcribe(tmp_path, language=language)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
