# LakeMindModelServing 设计方案

> 独立模型服务模块，从 LakeMindServer 抽离 LLM 网关，扩展为统一的模型服务平面。
> 待批准后实施。

---

## 1. 定位

LakeMindModelServing 是 LakeMind 的**一级模型服务模块**，与 LakeMindServer 并列。

| 职责 | 说明 |
|------|------|
| 统一模型网关 | litellm 作为顶层路由，统一 LLM chat/embedding 调用接口 |
| 自带嵌入服务 | fastembed 本地嵌入（jina-embeddings-v2-base-zh, dim=768），ONNX CPU |
| 自带 ASR 服务 | faster-whisper 本地语音识别（faster-whisper-small，多语种），INT8 CPU |
| 外部模型注册 | 运行时注册外部 LLM / embedding / ASR provider，无需重启 |
| OpenAI 兼容 API | 对外暴露 OpenAI 兼容接口，降低接入成本 |

**不是**：Agent 执行平台、模型训练平台、模型微调平台。

---

## 2. 架构

### 2.1 在 LakeMind 中的位置

```
┌─────────────────────────────────────────────────────────────┐
│                      运行平面                                │
│  Agent ──→ AssetMCP (:8401)                                 │
│  Steward ─→ DataMCP  (:8402) · AdminMCP (:8403)            │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────────────┐
│                      数据平面                                │
│  LakeMindServer (:10823)          LakeMindModelServing (:10824) │
│  REST API + 9 引擎                统一模型服务                  │
│  SeaweedFS · PG · Valkey          litellm + fastembed + faster-whisper │
│  Ray (调用 ModelServing)          外部模型注册                  │
└─────────────────────────────────────────────────────────────┘
```

LakeMindServer 从 11 引擎降为 9 引擎（移除 `cognitive.llm` 和 `cognitive.embedding`），
所有 LLM / embedding / ASR 调用走 LakeMindModelServing。

### 2.2 内部分层

```
┌─────────────────────────────────────────────────────┐
│              OpenAI 兼容 REST API (:10824)            │
│  /v1/chat/completions  /v1/embeddings  /v1/audio/...  │
│  /v1/models  /v1/models/register  /health             │
├─────────────────────────────────────────────────────┤
│                   litellm Router                      │
│          统一路由 · fallback · 负载均衡 · 缓存          │
├──────────┬──────────┬──────────┬────────────────────┤
│  LLM     │ Embedding│   ASR    │   模型注册管理      │
│  Providers│ Service  │ Service  │   (runtime CRUD)   │
│          │          │          │                    │
│ OpenAI   │ fastembed│faster-whis│  PG 持久化注册表    │
│ Anthropic│ (本地CPU)│ (本地CPU) │  热加载到 litellm  │
│ Ollama   │ 外部API  │ 外部API  │                    │
│ ModelArts│          │          │                    │
│ ...      │          │          │                    │
└──────────┴──────────┴──────────┴────────────────────┘
```

### 2.3 设计原则

1. **litellm 为顶层** — 所有 LLM 调用经 litellm Router 路由，不手写 provider 适配
2. **自带轻量服务** — embedding 和 ASR 优先本地 CPU 运行，零外部依赖可启动
3. **OpenAI 兼容** — 外部消费者无需学习新 API，标准 OpenAI SDK 直连
4. **可扩展** — 外部模型运行时注册，无需重启服务
5. **单一端口** — :10824 暴露全部能力，简单部署

---

## 3. 技术栈

| 组件 | 选型 | 许可证 | 用途 |
|------|------|--------|------|
| 模型网关 | **litellm** | MIT | 统一 LLM 路由、fallback、负载均衡 |
| Web 框架 | **FastAPI** | MIT | REST API 服务 |
| 本地嵌入 | **fastembed** | Apache 2.0 | jina-embeddings-v2-base-zh, ONNX CPU, dim=768 |
| 本地 ASR | **faster-whisper** | MIT | faster-whisper-small，多语种语音识别，INT8 CPU |
| 元数据 | **PostgreSQL** | PostgreSQL License (BSD-like) | 模型注册表持久化（复用 LakeMindServer 的 PG 实例） |
| 配置 | **PyYAML + Pydantic** | MIT/BSD | YAML 配置 + 环境变量插值 |

> 全开源组件，符合项目技术栈锁定要求。

### 3.1 为什么选 litellm

| 对比项 | 当前 GatewayLLM | litellm |
|--------|----------------|---------|
| Provider 支持 | 3 种（手写） | 100+ 种（内置） |
| Fallback | 手写链式 | 声明式配置 |
| 负载均衡 | 无 | 内置 |
| 缓存 | 无 | 内置 Redis/内存缓存 |
| 流式响应 | 不支持 | 原生支持 |
| 维护成本 | 自维护 | 社区维护（活跃） |
| 代码量 | ~350 行 | 0 行（pip install） |

### 3.2 为什么选 faster-whisper

| 对比项 | faster-whisper | FunASR | whisper.cpp |
|--------|-----------------|---------------------|-------------|
| 许可证 | MIT | 自定义 FunASR License | MIT |
| 中文识别 | 一般 | 优秀（阿里达摩院） | 一般 |
| 多语种 | 支持 99 | 支持 50+ | 支持 99 |
| CPU 性能 | 快（CTranslate2 INT8） | 快 | 最快（C++） |
| Python 集成 | 原生 | 原生 | 需 binding |
| 模型大小 | ~244MB (small) | ~234MB (Small) | ~147MB (base) |

选 faster-whisper：MIT 许可、原生 Python、CPU INT8 可用、无外部依赖（不耦合 ModelScope）。

---

## 4. API 设计

### 4.1 OpenAI 兼容端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/chat/completions` | LLM 对话补全（litellm 路由） |
| POST | `/v1/embeddings` | 文本嵌入（本地 fastembed 或外部 API） |
| POST | `/v1/audio/transcriptions` | 语音转文字（本地 faster-whisper 或外部 API） |
| GET | `/v1/models` | 列出全部已注册模型 |

### 4.2 管理端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/models/register` | 注册外部模型（运行时热加载） |
| DELETE | `/v1/models/{model_id}` | 注销模型 |
| GET | `/v1/models/{model_id}` | 查看模型详情 |
| GET | `/health` | 健康检查（各子服务状态） |
| GET | `/v1/models/types` | 列出支持的模型类型（llm/embedding/asr） |

### 4.3 认证

```
Authorization: Bearer ${MODELSERVING_API_KEY}
```

默认 `lakemind-modelserving-key`，通过环境变量覆盖。

### 4.4 请求示例

**Chat（OpenAI 兼容）**：
```json
POST /v1/chat/completions
{
  "model": "deepseek-v4-flash",
  "messages": [{"role": "user", "content": "你好"}],
  "temperature": 0.7,
  "max_tokens": 512
}
```

**Embedding（OpenAI 兼容）**：
```json
POST /v1/embeddings
{
  "model": "jina-embeddings-v2-base-zh",
  "input": ["文本1", "文本2"]
}
→ {
  "data": [
    {"embedding": [0.1, 0.2, ...], "index": 0},
    {"embedding": [0.3, 0.4, ...], "index": 1}
  ],
  "model": "jina-embeddings-v2-base-zh",
  "usage": {"prompt_tokens": 4, "total_tokens": 4}
}
```

**ASR（OpenAI 兼容）**：
```
POST /v1/audio/transcriptions
Content-Type: multipart/form-data
file: audio.wav
model: whisper-small
language: auto
→ {"text": "识别出的文字内容", "model": "whisper-small"}
```

**注册外部模型**：
```json
POST /v1/models/register
{
  "model_id": "gpt-4o",
  "type": "llm",
  "provider": "openai",
  "litellm_model": "openai/gpt-4o",
  "api_key": "sk-xxx",
  "tags": ["chat"],
  "context_window": 128000
}
```

---

## 5. 配置设计

### 5.1 models.yaml

```yaml
server:
  host: "0.0.0.0"
  port: 10824
  api_key: "lakemind-modelserving-key"

# ── litellm 路由配置 ──
gateway:
  default_chat_model: "deepseek-v4-flash"
  default_embed_model: "jina-embeddings-v2-base-zh"
  fallback:
    chat: ["deepseek-v4-flash"]
    embed: ["jina-embeddings-v2-base-zh"]
  cache: false

# ── LLM Providers ──
llm_providers:
  - name: "modelarts"
    type: "openai"
    base_url: "https://api.modelarts-maas.com/openai/v1"
    api_key: "${MAAS_API_KEY}"
    models:
      - id: "deepseek-v4-flash"
        litellm_model: "openai/deepseek-v4-flash"
        context: 64000
        tags: [chat]
    priority: 1
  # ── OpenAI ──
  # - name: "openai"
  #   type: "openai"
  #   api_key: "${OPENAI_API_KEY}"
  #   models:
  #     - id: "gpt-4o-mini"
  #       litellm_model: "openai/gpt-4o-mini"
  #       context: 128000
  #       tags: [chat]
  #   priority: 2
  # ── Anthropic ──
  # - name: "anthropic"
  #   type: "anthropic"
  #   api_key: "${ANTHROPIC_API_KEY}"
  #   models:
  #     - id: "claude-3-haiku-20240307"
  #       litellm_model: "anthropic/claude-3-haiku-20240307"
  #       context: 200000
  #       tags: [chat]
  #   priority: 3
  # ── Ollama 本地 ──
  # - name: "ollama"
  #   type: "ollama"
  #   base_url: "http://host.docker.internal:11434"
  #   models:
  #     - id: "qwen2.5:7b"
  #       litellm_model: "ollama/qwen2.5:7b"
  #       context: 32768
  #       tags: [chat]
  #   priority: 4

# ── 嵌入服务 ──
embedding:
  built_in:
    enabled: true
    provider: "fastembed"
    model: "jinaai/jina-embeddings-v2-base-zh"
    dim: 768
    cache_dir: "/data/fastembed_cache"
  external: []
    # - model_id: "text-embedding-3-small"
    #   provider: "openai"
    #   litellm_model: "openai/text-embedding-3-small"
    #   api_key: "${OPENAI_API_KEY}"
    #   dim: 1536

# ── ASR 服务 ──
asr:
  built_in:
    enabled: true
    provider: "faster-whisper"
    model: "Systran/faster-whisper-small"
    language: "auto"
    cache_dir: "/data/faster-whisper_cache"
  external: []
    # - model_id: "whisper-api"
    #   endpoint: "https://api.openai.com/v1/audio/transcriptions"
    #   api_key: "${OPENAI_API_KEY}"

# ── PostgreSQL（模型注册表持久化，复用 Server 实例）──
registry:
  host: "lakemind-postgres"
  port: 5432
  db: "lakemind"
  user: "lakemind"
  password: "lakemind_pass"
```

### 5.2 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MODELSERVING_API_KEY` | `lakemind-modelserving-key` | API 认证密钥 |
| `MAAS_API_KEY` | — | ModelArts API Key |
| `OPENAI_API_KEY` | — | OpenAI API Key（可选） |
| `ANTHROPIC_API_KEY` | — | Anthropic API Key（可选） |
| `LAKE_CONFIG` | `/etc/lakemind/models.yaml` | 配置文件路径 |

---

## 6. 模块结构

```
LakeMindModelServing/
├── DESIGN.md                      # 本文件
├── docker-compose.yml             # 独立 compose
├── Dockerfile                     # python:3.12-slim + litellm + fastembed + faster-whisper
├── pyproject.toml                 # 依赖声明
├── .env.example                   # 环境变量模板
├── config/
│   └── models.yaml                # 模型服务配置
├── data/
│   ├── fastembed_cache/           # fastembed 模型缓存
│   └── faster-whisper_cache/       # faster-whisper 模型缓存
└── src/
    └── lakemind_model_serving/
        ├── __init__.py
        ├── __main__.py            # 入口：uvicorn 启动
        ├── app.py                 # FastAPI app + 路由注册 + 中间件
        ├── config.py              # Pydantic 配置模型 + YAML 加载
        ├── auth.py                # Bearer Token 认证中间件
        ├── gateway.py             # litellm Router 封装
        ├── registry.py            # 模型注册表（PG 持久化 + 热加载）
        ├── api/
        │   ├── __init__.py
        │   ├── chat.py            # /v1/chat/completions
        │   ├── embeddings.py      # /v1/embeddings
        │   ├── audio.py           # /v1/audio/transcriptions
        │   ├── models.py          # /v1/models + register + delete
        │   └── health.py          # /health
        └── services/
            ├── __init__.py
            ├── embedding.py       # fastembed 本地嵌入服务
            └── asr.py             # faster-whisper 本地语音识别服务
```

---

## 7. 核心实现设计

### 7.1 litellm Router 封装（gateway.py）

```python
import litellm
from litellm import Router

class ModelGateway:
    def __init__(self, config: dict):
        self._router = Router(
            model_list=self._build_model_list(config["llm_providers"]),
            fallbacks=self._build_fallbacks(config["gateway"]),
            num_retries=2,
            timeout=30,
        )

    def chat(self, messages, model, temperature=0.7, max_tokens=0, stream=False):
        return self._router.completion(
            model=model, messages=messages,
            temperature=temperature, max_tokens=max_tokens,
            stream=stream,
        )

    def embed(self, texts, model):
        return self._router.embedding(model=model, input=texts)

    def list_models(self):
        return self._router.get_model_names()

    def register_model(self, model_config: dict):
        self._router.add_deployment(model_config)
```

### 7.2 本地嵌入服务（services/embedding.py）

```python
class EmbeddingService:
    def __init__(self, model_name, dim, cache_dir):
        self._model = None
        self._model_name = model_name
        self._dim = dim
        self._cache_dir = cache_dir

    def _ensure_model(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(
                model_name=self._model_name,
                cache_dir=self._cache_dir,
            )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_model()
        return [[float(x) for x in v] for v in self._model.embed(texts)]

    def health(self) -> bool:
        try:
            import fastembed
            return True
        except Exception:
            return False
```

### 7.3 本地 ASR 服务（services/asr.py）

```python
class ASRService:
    def __init__(self, model_name, language, cache_dir):
        self._model = None
        self._model_name = model_name
        self._language = language
        self._cache_dir = cache_dir

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                model_size_or_path=self._model_name,
                device="cpu",
                compute_type="int8",
            )

    def transcribe(self, audio_path: str) -> str:
        self._ensure_model()
        segments, _info = self._model.transcribe(audio_path, language=self._language)
        return "".join(seg.text for seg in segments).strip()

    def health(self) -> bool:
        try:
            import faster_whisper
            return True
        except Exception:
            return False
```

### 7.4 模型注册表（registry.py）

PG 表 `model_registry`：

| 列 | 类型 | 说明 |
|----|------|------|
| `model_id` | VARCHAR(128) PK | 模型唯一标识 |
| `type` | VARCHAR(16) | llm / embedding / asr |
| `provider` | VARCHAR(64) | openai / anthropic / ollama / fastembed / faster-whisper / external |
| `litellm_model` | VARCHAR(256) | litellm 模型名（如 `openai/gpt-4o`） |
| `api_key` | TEXT | API Key（加密存储） |
| `base_url` | VARCHAR(512) | 自定义 endpoint（可选） |
| `tags` | VARCHAR(64)[] | 标签：chat / embed / asr |
| `context_window` | INT | 上下文长度 |
| `dim` | INT | 嵌入维度（embedding 类型） |
| `priority` | INT | 路由优先级 |
| `is_active` | BOOLEAN | 是否启用 |
| `created_at` | TIMESTAMP | 创建时间 |

注册流程：
1. POST `/v1/models/register` → 写 PG → 调 `gateway.register_model()` 热加载到 litellm Router
2. DELETE `/v1/models/{id}` → 标记 PG `is_active=false` → 从 Router 移除
3. 启动时从 PG 加载全部 `is_active=true` 的模型

---

## 8. Docker 部署

### 8.1 Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ffmpeg && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip && pip install .
ENV LAKE_CONFIG=/etc/lakemind/models.yaml
EXPOSE 10824
CMD ["python", "-m", "lakemind_model_serving"]
```

> `ffmpeg` 用于 faster-whisper 音频处理。

### 8.2 docker-compose.yml

方案 A：**独立 compose**（推荐）

```yaml
name: lakemind
networks:
  lakemind:
    external: true    # 由 LakeMindServer 创建

services:
  model-serving:
    build: .
    image: lakemind/model-serving:latest
    container_name: lakemind-model-serving
    environment:
      LAKE_CONFIG: /etc/lakemind/models.yaml
      MODELSERVING_API_KEY: "${MODELSERVING_API_KEY:-lakemind-modelserving-key}"
      MAAS_API_KEY: "${MAAS_API_KEY}"
    ports:
      - "10824:10824"
    volumes:
      - ./config/models.yaml:/etc/lakemind/models.yaml:ro
      - ./data/fastembed_cache:/data/fastembed_cache
      - ./data/faster-whisper_cache:/data/faster-whisper_cache
    networks: [lakemind]
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:10824/health')"]
      interval: 15s
      timeout: 10s
      retries: 10
      start_period: 30s
```

方案 B：**并入 LakeMindServer/docker-compose.yml**（作为 server-api 的同级 service）

两种方案均可，方案 A 更清晰（独立模块独立 compose），方案 B 更简单（一次 `docker compose up`）。

### 8.3 pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "lakemind-model-serving"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "pydantic>=2.7",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "psycopg2-binary>=2.9",
    "litellm>=1.40",
    "fastembed>=0.4",
    "faster-whisper>=1.0",
    "cryptography>=42.0",
]

[project.scripts]
lakemind-model-serving = "lakemind_model_serving.__main__:main"

[tool.hatch.build.targets.wheel]
packages = ["src/lakemind_model_serving"]
```

---

## 9. 对 LakeMindServer 的影响

### 9.1 引擎变更（11 → 9）

| 引擎 | 变更 |
|------|------|
| `cognitive.llm` (gateway) | **移除** — 改为调用 ModelServing `/v1/chat/completions` |
| `cognitive.embedding` (fastembed) | **移除** — 改为调用 ModelServing `/v1/embeddings` |
| `cognitive.memory` (basic) | **改造** — LLM 和 embedding 调用改为远程 ModelServing |
| 其余 9 引擎 | 不变 |

### 9.2 代码变更

| 文件 | 变更 |
|------|------|
| `plugins/cognitive/llm/` | **删除整个目录**（gateway.py, openai_compat.py, anthropic.py, ollama.py） |
| `plugins/cognitive/embedding/` | **改为远程客户端**（调 ModelServing /v1/embeddings） |
| `plugins/cognitive/memory/basic.py` | `_ensure_embed()` 改为调 ModelServing；`_extract_facts()` 中 `self._llm.chat()` 改为 HTTP 调用 |
| `plugins/protocols.py` | 移除 `LLMPlugin`；`EmbeddingPlugin` 改为远程接口 |
| `plugins/registry.py` | 移除 `cognitive.llm` 和 `cognitive.embedding` 的本地注册 |
| `engines.py` | 移除 `self.llm`；`self.embedding` 改为远程客户端 |
| `config/engines.yaml` | 移除 `cognitive.llm` 和 `cognitive.embedding` 段；`cognitive.memory` 增加 `model_serving_url` 配置 |
| `api/llm.py` | **改为代理**（转发到 ModelServing）或**删除** |
| `api/embedding.py` | **改为代理**（转发到 ModelServing）或**删除** |
| `docker-compose.yml` | 移除 `MAAS_API_KEY` env；`server-api` 增加 `MODEL_SERVING_URL` env |
| `pyproject.toml` | 移除 `fastembed` 依赖（由 ModelServing 承载） |

### 9.3 LakeMindServer engines.yaml 变更

```yaml
# 移除 cognitive.embedding 和 cognitive.llm 段
cognitive:
  memory:
    plugin: basic
    config:
      # ... 原有 PG / Valkey / Lance 配置不变 ...
      model_serving_url: "http://lakemind-model-serving:10824"
      embedding_model: "jina-embeddings-v2-base-zh"
      embedding_dim: 768
      llm_model: "deepseek-v4-flash"
```

### 9.4 Ray Worker 影响

Ray worker 目前通过 Docker 网络调用 `lakemind-server-api:10823` 的 LLM 端点。
变更后改为调用 `lakemind-model-serving:10824/v1/chat/completions`。
Ray worker 的环境变量增加 `MODEL_SERVING_URL=http://lakemind-model-serving:10824`。

### 9.5 启动顺序变更

```powershell
# 1. 数据平面（含 Ray）
cd LakeMindServer; docker compose --env-file .env --profile ray up -d

# 2. 模型服务
cd ../LakeMindModelServing; docker compose up -d --build

# 3. 3 MCP
cd ../LakeMindMCP; docker compose --profile all up -d --build

# 4. 监控
cd ../LakeMindMonitor; docker compose up -d --build
```

> ModelServing 在 MCP 之前启动（MCP 的 server_client 可能需要 LLM 健康检查）。
> Server 和 ModelServing 之间无强依赖（Server 的 memory 引擎 lazy init），但建议 ModelServing 先启动。

---

## 10. 对上层文档的影响

| 文档 | 变更 |
|------|------|
| `AGENTS.md` | 包结构表增加 LakeMindModelServing 行；访问拓扑图增加 :10824；技术栈表增加 litellm/faster-whisper；引擎清单 11→9 |
| `.agent/DESIGN.md` | 架构图增加 ModelServing；引擎清单更新；容器清单增加；设计决策记录增加 |
| `.agent/SPEC.md` | 仓库结构增加 LakeMindModelServing；技术栈表增加 litellm/FunASr；启动顺序更新 |
| `.agent/STATE.md` | 增加 LakeMindModelServing 进度段；容器状态增加 model-serving |
| `docs/api-reference.md` | 增加 ModelServing API 文档 |
| `docs/architecture.md` | 架构图更新 |

---

## 11. 验证计划

| 验证项 | 方法 | 预期 |
|--------|------|------|
| 服务启动 | `docker compose up` + `/health` | 200 OK，各子服务 healthy |
| LLM chat | POST `/v1/chat/completions` | 正常返回 |
| LLM fallback | 主模型不可用 → fallback 模型 | 自动切换 |
| Embedding | POST `/v1/embeddings` | 返回正确维度向量 |
| ASR | POST `/v1/audio/transcriptions` + wav 文件 | 返回转写文本 |
| 模型注册 | POST `/v1/models/register` → GET `/v1/models` | 新模型出现在列表 |
| 模型注销 | DELETE `/v1/models/{id}` → GET `/v1/models` | 模型消失 |
| LakeMindServer 集成 | memory add + search（走 ModelServing embedding） | 正常工作 |
| Ray worker 集成 | Ray job 调 ModelServing LLM | 正常工作 |
| OpenAI SDK 兼容 | 用 openai Python SDK 直连 :10824 | 正常工作 |

---

## 12. 实施步骤（待批准后执行）

| 步骤 | 内容 | 预估 |
|------|------|------|
| 1 | 创建 LakeMindModelServing 骨架（pyproject.toml, Dockerfile, docker-compose.yml） | 15min |
| 2 | 实现 config.py + models.yaml 配置加载 | 20min |
| 3 | 实现 gateway.py（litellm Router 封装） | 30min |
| 4 | 实现 services/embedding.py（fastembed 服务） | 15min |
| 5 | 实现 services/asr.py（faster-whisper 服务） | 30min |
| 6 | 实现 registry.py（PG 模型注册表） | 30min |
| 7 | 实现 api/ 全部端点（chat, embeddings, audio, models, health） | 45min |
| 8 | 实现 auth.py + app.py | 20min |
| 9 | Docker build + 启动验证 | 30min |
| 10 | 改造 LakeMindServer（移除 LLM/embedding 引擎，memory 改远程调用） | 60min |
| 11 | 更新 LakeMindServer docker-compose（增加 MODEL_SERVING_URL） | 10min |
| 12 | 端到端验证（Server + ModelServing + MCP） | 30min |
| 13 | 更新上层文档（README.md, AGENTS.md, .agent/*, docs/） | 30min |

**总预估：~5.5 小时**

---

## 13. 待确认问题

| # | 问题 | 建议 | 待确认 |
|---|------|------|--------|
| 1 | docker-compose 独立还是并入 Server？ | 独立（方案 A），模块边界清晰 | ? |
| 2 | LakeMindServer 的 `/api/v1/cognitive/llm/*` 和 `/api/v1/cognitive/embedding/*` 端点保留为代理还是删除？ | 删除，消费者直接调 ModelServing | ? |
| 3 | 模型注册表是否复用 LakeMindServer 的 PG 实例？ | 复用（同一 PG，新表 `model_registry`） | ? |
| 4 | faster-whisper 是否需要 GPU 支持？ | MVP 用 CPU INT8，生产可加 GPU profile | ? |
| 5 | litellm 是否启用缓存？ | MVP 不启用（`cache: false`），生产可加 Redis 缓存 | ? |
