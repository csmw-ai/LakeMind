# LakeMind — 多模智能数据湖

> Agent 原生的多模态智能数据底座。面向企业内或者组织内的大量Agent提供统一存储、统一元数据、统一的认知计算与AI数据计算能力。

---

## 你为什么必须要用 LakeMind？

你有 10 个 Agent，你的团队有 100 个 Agent，你的公司有 1000 个 Agent。

它们认知混乱——每个 Agent 各自维护一套知识，同一个概念在不同 Agent 眼中含义不同，没有人能统一描述"我们到底知道什么"。

它们知识碎片化——A Agent 昨天学到的经验，B Agent 今天还要重新踩坑；团队积累的技能以散落在各处的 prompt、文件、对话记录的形式存在，无法被检索、复用、传承。

它们记忆丢失——对话结束，上下文清空，Agent 的一切认知归零。你给每个 Agent 接了向量数据库，但十套八套互不相通，租户隔离、权限控制、生命周期管理全靠手写。

它们数据割裂——结构化数据在 Iceberg 里，向量在 LanceDB 里，文件在 S3 里，图在 Neo4j 里，缓存在 Redis 里。每个 Agent 要对接五种存储、六种 SDK，开发一个能用的 Agent 门槛高得离谱。

**LakeMind 解决的就是这个问题。**

它为 Agent 提供一个统一的认知数据底座：所有数据、知识、记忆、技能、本体都在同一个地方，用同一套 API 访问，同一套元数据管理，同一套权限体系治理。Agent 不需要关心数据存在哪种引擎里——它只需要声明自己需要什么资产，LakeMind 负责剩下的一切。

---

## LakeMind 是什么

LakeMind 是 **Agent 原生的多模态智能数据底座**（Agent-Native Multimodal Intelligent Data Foundation）。

它不止是数据库，不止是向量存储，不止是 RAG 框架。它是这些东西之上的**统一认知数据层**——把多模态数据存储、结构化表管理、向量检索、图存储、KV 缓存、分布式计算、LLM 推理网关、记忆引擎、资产编排、租户治理，收敛为一个 Agent 可直接消费的数据平面。

Agent 通过 MCP 协议连接 LakeMind，获得**声明式资产访问**能力：不写 SQL，不调 SDK，不管存储——声明"我需要一个知识库"或"我需要回忆上次的经验"，LakeMind 自动路由到正确的引擎、正确的租户空间、正确的权限边界。

**一句话定位**：LakeMind 是 Agent 时代的数据操作系统——就像 Kubernetes 是容器时代的操作系统一样。

![LakeMind 概念总览](docs/LakeMind-Concept.png)

---

## 快速开始

### 前置要求

| 要求 | 最低版本 | 用途 |
|------|----------|------|
| Docker + Docker Compose | Docker 24+ | 运行 12 个容器 |
| Python | 3.12+ | 模型预下载脚本 |
| Node.js | 18+ | 构建示例前端 |
| 可用内存 | ≥ 8GB | 含 Ray 集群 |
| 磁盘空间 | ≥ 20GB | 镜像 + 模型 + 数据 |

### 1. 克隆 + 配置

```bash
git clone https://github.com/csmw-ai/LakeMind.git
cd LakeMind
cp .env.example .env
```

编辑 `.env`，填入以下配置：

```bash
# LLM Provider（你的 API Key 和接口地址）
MAAS_BASE_URL=https://api.modelarts-maas.com/openai/v1   # 或 OpenAI/DeepSeek/Ollama
MAAS_API_KEY=<your-llm-api-key>

# 安全密钥
LAKEMIND_MASTER_KEY=<openssl rand -base64 32>    # 租户密钥加密主密钥
SERVER_API_KEY=<openssl rand -hex 32>            # Server API 认证令牌
```

### 2. 预下载模型（离线模式，必须执行）

LakeMind **禁止运行时下载模型**。启动前需预下载 ASR 和 Embedding 模型：

```bash
pip install modelscope fastembed

# SenseVoice ASR 模型（~900MB）
python -c "from modelscope import snapshot_download; snapshot_download('iic/SenseVoiceSmall', local_dir='LakeMindModelServing/data/asr-models/asr/sensevoice-small')"

# fsmn-vad VAD 模型（~5MB）
python -c "from modelscope import snapshot_download; snapshot_download('iic/speech_fsmn_vad_zh-cn-16k-common-pytorch', local_dir='LakeMindModelServing/data/asr-models/asr/fsmn-vad')"

# fastembed 嵌入模型（~160MB）
python -c "from fastembed import TextEmbedding; m=TextEmbedding(model_name='jinaai/jina-embeddings-v2-base-zh', cache_dir='LakeMindModelServing/data/fastembed_cache'); list(m.embed(['init'])); print('OK')"
```

> 详见 [模型离线下载指南](docs/model-offline-download.md)

### 3. 启动平台

```bash
# 本地开发（首次构建镜像）
docker buildx bake core --load
docker compose -f docker-compose.yml -f docker-compose.build.yml --env-file .env --profile ray --profile all up -d --no-build

# 或使用预构建镜像（从 GHCR 拉取）
docker compose --env-file .env --profile ray --profile all pull
docker compose --env-file .env --profile ray --profile all up -d
```

### 4. 验证

```bash
curl http://localhost:10823/api/v1/system/health   # 10 引擎全部 true
```

打开 ControlCenter：`http://localhost:3000`（admin 登录）

### 5. 运行示例

```bash
cd examples/meeting-agent
cd frontend && npm install && npm run build && cd ..
docker compose up -d --build
# 浏览器打开 http://localhost:9100
```

详见 [示例指南](examples/README.md)。

---

## 技术架构

### 总览

![LakeMind 架构设计](docs/LakeMind-Architectural.png)

### 2 层数据类型

| 层 | 定位 | 访问面 | 说明 |
|----|------|--------|------|
| **认知资产层 (ASSET)** | 面向 Agent 认知模型的语义封装 | AssetMCP | 知识、技能、记忆、本体——声明式 YAML 定义，预置 4 类，可删可扩 |
| **数据层 (DATA)** | 多模态数据底座，REST API 透传 | DataMCP | Iceberg 表、Lance 向量、S3 文件、Valkey KV、PG 图 |

### 3 个 MCP 服务

| MCP | 端口 | Scope | 工具数 | 职责 |
|-----|------|-------|--------|------|
| **LakeMindAssetMCP** | 8401 | `asset` | 23 tools | 认知资产面：知识检索/摄入、技能管理、记忆读写、本体查询 |
| **LakeMindDataMCP** | 8402 | `data` | 24 tools | 数据面：Iceberg/DuckDB/LanceDB/S3/Valkey/Graph + Ray 作业提交 |
| **LakeMindAdminMCP** | 8403 | `admin` | 21 tools | 管理面：用户/租户/Token/密钥/平台健康 |

### 核心服务

| 服务 | 端口 | 职责 |
|------|------|------|
| **LakeMindServer** | 10823 | REST API 网关（40+ 路径）+ 10 引擎 + Job Runtime |
| **LakeMindModelServing** | 10824 | litellm LLM 网关 + 模型管理 API |
| **Ray Serve** | — | ASR (asr-app) + Embedding (embedding-app) 推理服务 |
| **LakeMindControlCenter** | 3000 | 统一管理入口（前端 + BFF + Steward） |

### 引擎一览

| 引擎 | 选型 | 用途 |
|------|------|------|
| 对象存储 | **SeaweedFS** | S3 兼容，承载全部数据文件 |
| 表格式 | **Apache Iceberg** | 结构化表，PyIceberg 嵌入式 |
| 向量/多模态 | **PyLance + LanceDB** | 向量检索，共享 Lance 目录 |
| KV 缓存 | **Valkey** | Redis 兼容 TTL KV |
| 统一元数据 | **PostgreSQL 16** | Iceberg catalog + 图 + 用户/租户/Token |
| 即席 SQL | **DuckDB** | 进程内轻量 SQL |
| 分布式计算 | **Ray 2.41** | Job Runtime + Serve（ASR/embedding 推理） |
| Embedding | **fastembed** | jina-v2-base-zh, dim=768（Ray Serve） |
| LLM 网关 | **litellm** | 多 provider 路由 + fallback |
| ASR | **SenseVoice (funasr)** | 本地语音识别（Ray Serve，自带标点 + ITN） |

---

## 运行容器

| 容器 | 端口 | 用途 |
|------|------|------|
| lakemind-server-api | 10823 | REST API 网关 |
| lakemind-model-serving | 10824 | LLM 网关 + 模型管理 |
| lakemind-postgres | 5432 | 统一元数据 + 图存储 |
| lakemind-seaweedfs | 8333 | S3 对象存储 |
| lakemind-valkey | 6379 | TTL KV 缓存 |
| lakemind-ray-head | 8265 | Ray dashboard |
| lakemind-ray-worker | — | Ray worker（ASR + embedding 推理） |
| lakemind-asset-mcp | 8401 | 资产面 MCP |
| lakemind-data-mcp | 8402 | 数据面 MCP |
| lakemind-admin-mcp | 8403 | 管理面 MCP |
| lakemind-control-center | 3000 | 统一管理入口 |

---

## 数据域 → 引擎映射

| 数据域 | 引擎 | MCP 资产 |
|--------|------|---------|
| 结构化数据 | Iceberg + PG catalog | DataMCP |
| 知识 / 多模态 RAG | Lance + LanceDB | `lake://knowledge` |
| 短期/工作记忆 | Valkey (TTL KV) | `lake://memory` |
| 长期/语义记忆 | Lance 向量 + PG 元信息 | `lake://memory` |
| Skills | S3 + PG + LanceDB | `lake://skills` |
| 本体 / 图 | PG graph_nodes/edges | `lake://ontology` |

---

## 示例

| 示例 | 目录 | 验证内容 | 状态 |
|------|------|----------|------|
| **meeting-agent** | `examples/meeting-agent/` | 录音→ASR→纪要→知识 全链路 | ✅ v0.2.1 验证通过 |
| **lakemind-connector** | `examples/lakemind-connector/` | Skill 注册/检索/执行 + 认知资产存取 | ✅ 已验证 |

详见 `examples/README.md`。

---

## 技术栈

全开源组件（Apache 2.0 / MIT / BSD）：

| 组件 | 选型 | 许可证 |
|------|------|--------|
| 对象存储 | SeaweedFS | Apache 2.0 |
| 表格式 | Apache Iceberg | Apache 2.0 |
| 向量 / 多模态 | PyLance + LanceDB | Apache 2.0 / MIT |
| 元数据 / 图 | PostgreSQL 16 | PostgreSQL License |
| 缓存 / 短期记忆 | Valkey | BSD 3-Clause |
| 即席计算 | DuckDB | MIT |
| 分布式计算 | Ray | Apache 2.0 |
| Embedding | fastembed | Apache 2.0 |
| LLM 网关 | litellm | MIT |
| 语音识别 | SenseVoice (funasr) | Apache 2.0 |
| MCP SDK | FastMCP | MIT |
| Agent 框架 | LangGraph | MIT |

---

## 文档索引

### 快速上手

| 文档 | 内容 |
|------|------|
| [快速入门](docs/quickstart.md) | 从零启动 LakeMind |
| [模型离线下载指南](docs/model-offline-download.md) | 预下载 ASR + Embedding 模型 |
| [核心概念与术语表](docs/glossary.md) | Agent 原生、认知资产、MCP 等概念 |
| [ControlCenter 使用指南](docs/control-center.md) | 统一管理入口 |

### 开发与架构

| 文档 | 内容 |
|------|------|
| [开发指南](docs/develop-guide.md) | 编写 Skill、提交 Ray 作业 |
| [架构设计](docs/architecture.md) | 三平面分层、MCP 职责、数据流 |
| [MCP 工具参考](docs/mcp-tools.md) | 68 工具 + 23 资源 + 10 prompts |
| [REST API 参考](docs/api-reference.md) | 40+ OpenAPI 路径 |
| [Example 开发指南](docs/lakemind-example-develop-guide.md) | 从零构建 Example Agent |

### 运维

| 文档 | 内容 |
|------|------|
| [配置参考](docs/configuration.md) | 引擎配置、环境变量 |
| [部署运维](docs/deployment.md) | 容器管理、故障排查 |

---

## 反馈与社区

- **Bug 报告 / 功能请求**：[GitHub Issues](https://github.com/csmw-ai/LakeMind/issues)
- **代码贡献**：请阅读 [贡献指南](CONTRIBUTING.md)

---

## 路线图

| 版本 | 计划内容 | 状态 |
|------|----------|------|
| **v0.1.0** | MVP：13 容器、10 引擎、68 MCP 工具 | ✅ 已发布 |
| **v0.2.0** | ControlCenter、RBAC、Job Runtime、模型管理、Meeting Agent | ✅ 已发布 |
| **v0.2.1** | Ray Serve 迁移（ASR+embedding）、mcp 2.0 适配、bug 修复 | ✅ 已发布 |
| **v0.2.2** | 文档刷新、模型离线下载指南、examples 安装优化 | ✅ 已发布 |
| **v0.3** | LakeMindStudio（Tauri 桌面客户端） | 规划中 |

---

## License

Apache 2.0
