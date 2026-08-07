#!/usr/bin/env python3
"""LakeMind 模型离线下载脚本 — ASR + VAD + Embedding。"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "LakeMindModelServing" / "data"


def download_asr():
    from modelscope import snapshot_download
    asr_dir = BASE / "asr-models" / "asr"
    asr_dir.mkdir(parents=True, exist_ok=True)

    print("[1/3] Downloading SenseVoiceSmall (~900MB)...")
    snapshot_download("iic/SenseVoiceSmall", local_dir=str(asr_dir / "sensevoice-small"))
    print("  OK")

    print("[2/3] Downloading fsmn-vad (~5MB)...")
    snapshot_download("iic/speech_fsmn_vad_zh-cn-16k-common-pytorch", local_dir=str(asr_dir / "fsmn-vad"))
    print("  OK")


def download_embedding():
    print("[3/3] Downloading jina-embeddings-v2-base-zh (~160MB)...")
    cache_dir = BASE / "fastembed_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    from fastembed import TextEmbedding
    model = TextEmbedding(
        model_name="jinaai/jina-embeddings-v2-base-zh",
        cache_dir=str(cache_dir),
    )
    list(model.embed(["init"]))
    print("  OK")


if __name__ == "__main__":
    download_asr()
    download_embedding()
    print("\nAll models downloaded. Ready to start LakeMind.")
