from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Protocol


class ASRStatus(str, enum.Enum):
    DISABLED = "disabled"
    MISSING = "missing"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"


@dataclass
class ASRSegment:
    start_ms: int
    end_ms: int
    text: str


@dataclass
class ASRResult:
    text: str
    raw_text: str
    language: str | None
    model: str
    provider: str
    duration_ms: int
    processing_ms: int
    segments: list[ASRSegment] = field(default_factory=list)


class ASRBackend(Protocol):
    def load(self) -> None: ...
    def ready(self) -> bool: ...
    def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        use_itn: bool = True,
        initial_prompt: str | None = None,
        hotwords: list[str] | None = None,
    ) -> ASRResult: ...
