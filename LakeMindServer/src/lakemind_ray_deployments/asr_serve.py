"""ASR Ray Serve deployment."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import time

import librosa
from ray import serve

logger = logging.getLogger(__name__)

_TAG_PATTERN = re.compile(r"<\|[^|]+\|>")


def _clean_tags(text: str) -> str:
    return _TAG_PATTERN.sub("", text).strip()


@serve.deployment
class ASRDeployment:
    def __init__(self):
        import torch
        from funasr import AutoModel

        torch.set_num_threads(int(os.environ.get("ASR_INTRA_THREADS", "2")))
        torch.set_num_interop_threads(int(os.environ.get("ASR_INTER_THREADS", "1")))

        model_id = os.environ.get("ASR_MODEL", "iic/SenseVoiceSmall")
        vad_model = os.environ.get("ASR_VAD_MODEL", "fsmn-vad")

        kwargs = dict(
            model=model_id,
            disable_update=True,
            device=os.environ.get("ASR_DEVICE", "cpu"),
            disable_pbar=True,
            trust_remote_code=False,
        )
        if vad_model:
            kwargs["vad_model"] = vad_model

        self._model = AutoModel(**kwargs)
        self._language = os.environ.get("ASR_LANGUAGE", "zh")
        self._use_itn = os.environ.get("ASR_USE_ITN", "true").lower() == "true"
        logger.info("ASRDeployment loaded: %s (vad=%s)", model_id, vad_model or "off")

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> dict:
        t0 = time.time()
        tmp_dir = tempfile.mkdtemp(prefix="lakemind-asr-")
        tmp_path = os.path.join(tmp_dir, filename)
        wav_path = os.path.join(tmp_dir, "audio_16k.wav")
        try:
            with open(tmp_path, "wb") as f:
                f.write(audio_bytes)
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", tmp_path,
                    "-ar", "16000", "-ac", "1",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-f", "wav", wav_path,
                ],
                capture_output=True, timeout=30,
            )
            input_path = wav_path if os.path.exists(wav_path) and os.path.getsize(wav_path) > 44 else tmp_path

            result = self._model.generate(
                input=input_path,
                language=self._language,
                use_itn=self._use_itn,
            )
            raw_text = result[0]["text"] if result else ""
            text = _clean_tags(raw_text)

            audio, _ = librosa.load(input_path, sr=16000, mono=True, dtype="float32")
            duration_ms = int(len(audio) / 16)
            processing_ms = int((time.time() - t0) * 1000)

            return {
                "text": text,
                "raw_text": raw_text,
                "language": self._language,
                "duration_ms": duration_ms,
                "processing_ms": processing_ms,
            }
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
