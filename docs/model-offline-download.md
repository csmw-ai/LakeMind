# 模型离线下载指南

> LakeMind **禁止运行时下载模型**。所有模型（ASR、Embedding）必须在部署前预下载到持久化存储，运行时只从本地路径加载。模型缺失时返回错误，不触发下载。

---

## 需要预下载的模型

| 模型 | 用途 | 来源 | 大小 | 本地路径 |
|------|------|------|------|----------|
| SenseVoiceSmall | ASR 语音识别 | ModelScope (`iic/SenseVoiceSmall`) | ~900 MB | `LakeMindModelServing/data/asr-models/asr/sensevoice-small` |
| fsmn-vad | 语音活动检测 (VAD) | ModelScope (`iic/speech_fsmn_vad_zh-cn-16k-common-pytorch`) | ~5 MB | `LakeMindModelServing/data/asr-models/asr/fsmn-vad` |
| jina-embeddings-v2-base-zh | 文本嵌入 | HuggingFace (`jinaai/jina-embeddings-v2-base-zh`) | ~160 MB | `LakeMindModelServing/data/fastembed_cache` |

> **LLM 模型不需要预下载** — LLM 通过 litellm 网关调用外部 API（如华为云 ModelArts、OpenAI、DeepSeek），只需配置 API Key。

---

## 下载步骤

### 1. 安装下载工具

```bash
pip install modelscope fastembed
```

### 2. 下载 ASR 模型（SenseVoice）

```bash
python -c "
from modelscope import snapshot_download
snapshot_download(
    'iic/SenseVoiceSmall',
    local_dir='LakeMindModelServing/data/asr-models/asr/sensevoice-small'
)
print('SenseVoice model downloaded.')
"
```

验证下载：

```bash
ls LakeMindModelServing/data/asr-models/asr/sensevoice-small/
# 应包含: model.pt, config.yaml, chn_jitn_map.txt, ...
```

### 3. 下载 VAD 模型（fsmn-vad）

```bash
python -c "
from modelscope import snapshot_download
snapshot_download(
    'iic/speech_fsmn_vad_zh-cn-16k-common-pytorch',
    local_dir='LakeMindModelServing/data/asr-models/asr/fsmn-vad'
)
print('VAD model downloaded.')
"
```

验证下载：

```bash
ls LakeMindModelServing/data/asr-models/asr/fsmn-vad/
# 应包含: model.pt, vad.yaml, ...
```

### 4. 下载 Embedding 模型（fastembed）

```bash
python -c "
from fastembed import TextEmbedding
model = TextEmbedding(
    model_name='jinaai/jina-embeddings-v2-base-zh',
    cache_dir='LakeMindModelServing/data/fastembed_cache'
)
# 触发实际下载
list(model.embed(['初始化模型缓存']))
print('Embedding model cached.')
"
```

验证下载：

```bash
ls LakeMindModelServing/data/fastembed_cache/
# 应包含: models--jinaai--jina-embeddings-v2-base-zh/ 目录
```

---

## 模型加载机制

预下载的模型通过 Docker volume 挂载到容器内：

```
LakeMindModelServing/data/asr-models/    →  容器内 /models          (model-serving + ray-worker)
LakeMindModelServing/data/fastembed_cache/  →  容器内 /data/fastembed_cache  (model-serving + ray-worker)
```

相关环境变量（已在 `docker-compose.yml` 中配置）：

| 变量 | 值 | 作用 |
|------|-----|------|
| `HF_HUB_OFFLINE` | `1` | 禁止 HuggingFace 运行时下载 |
| `MODELSCOPE_CACHE` | `/models/funasr_cache` | ModelScope 缓存路径 |
| `ASR_MODEL` | `iic/SenseVoiceSmall` | ASR 模型 ID |
| `ASR_VAD_MODEL` | `fsmn-vad` | VAD 模型名称 |
| `EMBEDDING_MODEL` | `jinaai/jina-embeddings-v2-base-zh` | Embedding 模型 |
| `EMBEDDING_CACHE_DIR` | `/data/fastembed_cache` | Embedding 缓存路径 |

---

## 国产镜像加速

ModelScope 下载在国内通常较快。如遇网络问题，可配置代理：

```bash
# ModelScope 镜像源（通常不需要，ModelScope 本身在国内）
export MODELSCOPE_DOMAIN=modelscope.cn

# HuggingFace 镜像源（fastembed 使用）
export HF_ENDPOINT=https://hf-mirror.com
```

---

## 一键下载脚本

将以下内容保存为 `scripts/download_models.py` 并运行：

```python
"""LakeMind 模型离线下载脚本"""
import os
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
```

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `modelscope` import 失败 | 未安装 | `pip install modelscope` |
| 下载超时 | 网络问题 | 配置代理或重试 |
| ASR Job FAILED: model not found | 模型路径不对 | 确认目录结构匹配上表 |
| Ray worker OOM | 模型加载内存不足 | 确保 Docker 内存 ≥ 8GB |
| `fastembed` 下载到默认缓存 | `cache_dir` 未指定 | 确认 `EMBEDDING_CACHE_DIR` 指向正确路径 |
