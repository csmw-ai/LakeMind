"""Deploy Ray Serve deployments — all code inline to avoid cross-module import issues."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import ray
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
        import librosa
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


def main():
    ray_address = os.environ.get("LAKEMIND_RAY_ADDRESS", "ray://lakemind-ray-head:10001")
    for attempt in range(30):
        try:
            ray.init(address=ray_address, ignore_reinit_error=True)
            break
        except Exception as e:
            print(f"Waiting for Ray cluster... ({attempt + 1}/30) {e}")
            time.sleep(5)
    else:
        print("ERROR: Could not connect to Ray cluster after 150s")
        sys.exit(1)

    serve.start(detached=True)

    asr_replicas = int(os.environ.get("ASR_NUM_REPLICAS", "1"))
    embed_replicas = int(os.environ.get("EMBEDDING_NUM_REPLICAS", "1"))
    asr_cpus = float(os.environ.get("ASR_REPLICA_CPUS", "2"))
    embed_cpus = float(os.environ.get("EMBEDDING_REPLICA_CPUS", "1"))

    serve.run(ASRDeployment.options(
        name="asr",
        num_replicas=asr_replicas,
        ray_actor_options={"num_cpus": asr_cpus},
    ).bind(), name="asr-app", route_prefix="/asr")
    print(f"ASR deployment: {asr_replicas} replicas x {asr_cpus} CPU")

    serve.run(EmbeddingDeployment.options(
        name="embedding",
        num_replicas=embed_replicas,
        ray_actor_options={"num_cpus": embed_cpus},
    ).bind(), name="embedding-app", route_prefix="/embedding")
    print(f"Embedding deployment: {embed_replicas} replicas x {embed_cpus} CPU")

    for _ in range(30):
        status = serve.status()
        apps = status.applications
        asr_ok = "asr-app" in apps and apps["asr-app"].status.name == "RUNNING"
        embed_ok = "embedding-app" in apps and apps["embedding-app"].status.name == "RUNNING"
        if asr_ok and embed_ok:
            break
        time.sleep(2)
    else:
        print("WARNING: deployments not fully ready after 60s")

    print(serve.status())
    print("Ray Serve deployments ready.")

    while True:
        time.sleep(60)
        try:
            status = serve.status()
            apps = status.applications
            asr_ok = "asr-app" in apps and apps["asr-app"].status.name == "RUNNING"
            embed_ok = "embedding-app" in apps and apps["embedding-app"].status.name == "RUNNING"
            if not (asr_ok and embed_ok):
                print(f"Watchdog: apps missing (asr={asr_ok}, embed={embed_ok}), redeploying...")
                serve.run(ASRDeployment.options(
                    name="asr", num_replicas=asr_replicas,
                    ray_actor_options={"num_cpus": asr_cpus},
                ).bind(), name="asr-app", route_prefix="/asr")
                serve.run(EmbeddingDeployment.options(
                    name="embedding", num_replicas=embed_replicas,
                    ray_actor_options={"num_cpus": embed_cpus},
                ).bind(), name="embedding-app", route_prefix="/embedding")
                print("Watchdog: redeploy triggered.")
        except Exception as e:
            print(f"Watchdog: status check failed: {e}")


if __name__ == "__main__":
    main()
