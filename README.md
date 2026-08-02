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

## 技术架构

### 总览

![LakeMind 架构设计](docs/LakeMind-Architectural.png)



### 2 层数据类型

LakeMind 将 Agent 需要的一切数据分为两层，用不同的 MCP 面提供访问：

| 层 | 定位 | 访问面 | 说明 |
|----|------|--------|------|
| **认知资产层 (ASSET)** | 面向 Agent 认知模型的语义封装 | AssetMCP | 知识、技能、记忆、本体——声明式 YAML 定义，预置 4 类，可删可扩。Agent 不关心底层存储，只声明"我需要一个知识库" |
| **数据层 (DATA)** | 多模态数据底座，通过 REST API 透传不做语义解释 | DataMCP | 数据是什么、存哪、怎么读写。Iceberg 表、Lance 向量、S3 文件、Valkey KV、PG 图——通过 REST API 全量透传给 Steward 和高级 Agent |

### 3 个 MCP 服务

Agent 通过 MCP 协议连接 LakeMind。三个 MCP 独立部署、各自水平扩展、scope 隔离：

| MCP | 端口 | Scope | 面向 | 工具数 | 职责 |
|-----|------|-------|------|--------|------|
| **LakeMindAssetMCP** | 8401 | `asset` | 业务 Agent | 23 tools, 11 resources, 6 prompts | 认知资产面：知识检索/摄入、技能管理、记忆读写、本体查询 |
| **LakeMindDataMCP** | 8402 | `data` | Steward / 高级 Agent | 24 tools, 6 resources, 2 prompts | 数据面：Iceberg/DuckDB/LanceDB/S3/Valkey/Graph 通过LakeMind的统一API进行访问 + Ray 作业提交 |
| **LakeMindAdminMCP** | 8403 | `admin` | Steward | 21 tools, 6 resources, 2 prompts | 管理面：用户/租户/Token/资产类型/租户密钥/平台健康 |

### 核心服务 LakeMindServer 与 LakeMindModelServing

LakeMindServer 是数据平面的核心，提供 REST API 网关（40+ OpenAPI 路径）和 2 大引擎类别：

**数据存储引擎**：

| 引擎 | 选型 | 用途 |
|------|------|------|
| 对象存储 | **SeaweedFS** | S3 兼容，存 Iceberg 数据文件 / Lance 向量 / Skill 代码 |
| 表格式 | **Apache Iceberg** | 结构化表，PyIceberg 嵌入式，PG SQL catalog |
| 向量 / 多模态 | **PyLance + LanceDB** | 向量检索，共享 Lance 目录 |
| KV 缓存 | **Valkey** | Redis 兼容 TTL KV，短期/工作记忆（BSD 3-Clause） |
| 统一元数据 | **PostgreSQL 16** | Iceberg catalog + 图存储 + 用户/租户/Token + 资产定义 |
| 图 / 本体 | **PG 原生表** | graph_nodes / graph_edges + JSONB |

**数据计算引擎**：

| 引擎 | 选型 | 用途 |
|------|------|------|
| 即席 SQL | **DuckDB** | 进程内轻量 SQL，即席分析 |
| 分布式计算 | **Ray 2.41** | 3 节点 12 CPU，批量 embedding / 并行检索 / 重计算 |

**认知引擎**（Server 内）：

| 引擎 | 选型 | 用途 |
|------|------|------|
| 记忆引擎 | **BasicMemory** | 短期 Valkey TTL + 长期 Lance 向量 + PG 元信息（mem0 风格），LLM 事实抽取 via ModelServing |

**模型服务引擎**（LakeMindModelServing :10824）：

| 引擎 | 选型 | 用途 |
|------|------|------|
| Embedding | **fastembed** | ONNX + jinaai/jina-embeddings-v2-base-zh，dim=768，中英混合 |
| LLM 网关 | **litellm** | 多 provider 路由 + fallback，支持 OpenAI/DeepSeek/Anthropic/Ollama |
| 语音识别 | **SenseVoice (funasr)** | iic/SenseVoiceSmall 本地 ASR (CPU, funasr + PyTorch，自带标点 + ITN) |

### 配套工具

| 工具 | 定位 | 状态 |
|------|------|------|
| **LakeMindModelServing** | 统一模型服务：litellm 网关 + fastembed 嵌入 + SenseVoice funasr 语音识别 | ✅ 已完成 |
| **LakeMindControlCenter** | 统一管理入口（前端 + BFF + Steward）：10 页面，Mission Control 仪表板，模型配置与路由，Steward 对话 | ✅ v0.2.0 |
| **LakeMindStudio** | 桌面客户端（Tauri）：资产设计器、MCP 调试台、Skill 脚手架、CI/CD | 🔨 待开发 |

> v0.1.0 的 `LakeMindSteward` + `LakeMindMonitor` 已在 v0.2.0 合并迁入 `LakeMindControlCenter`（Steward 作为内嵌组件运行于 :3002，Monitor 仪表板迁为 Mission Control 页面），不再独立部署。

**REST API 网关**：LakeMindServer 提供 40+ OpenAPI 路径的统一 REST API，MCP 通过 httpx 连接池调用，支持 10 引擎健康检查、Bearer 认证、租户/Agent/Scope 三级上下文。外部访问统一通过REST API来访问，不直接访问底层引擎，以保障访问的规范化和便捷化。

**管理/治理面**：AdminMCP 提供用户/租户/Token/资产类型 CRUD，PostgreSQL 行级租户隔离，Token scope 控制 MCP 访问边界。

---

## 数据域 → 引擎映射

| 数据域 | 引擎 | MCP 资产 | 资源 URI |
|--------|------|---------|----------|
| 结构化数据 | Iceberg + PG catalog | `lake://data` | DataMCP（REST API 透传） |
| 知识 / 多模态 RAG | Lance + LanceDB | `lake://knowledge` | AssetMCP |
| 短期/工作记忆 | Valkey (TTL KV) | `lake://memory` | AssetMCP |
| 长期/语义记忆 | Lance 向量 + PG 元信息（mem0 风格） | `lake://memory` | AssetMCP |
| Skills | S3 + PG + LanceDB | `lake://skills` | AssetMCP |
| 本体 / 图 | PG graph_nodes/edges | `lake://ontology` | AssetMCP |
| LLM 推理 | litellm → 外部 API | `/v1/chat/completions` | ModelServing (:10824) |

> 长期记忆采用 Lance 向量 + PG 元信息双表设计（mem0 风格），通过 `lance_uri` 字段关联。

---

## 验证状态

| 验证套件 | 脚本 | 结果 |
|----------|------|------|
| 全面测试 L0-L9 | `scripts/verify_full.py` | ✅ 297/297 PASS |
| Meeting Agent E2E | `examples/meeting-agent/` | ✅ 全链路：录音→ASR→纪要→知识 |

### 引擎健康（10 引擎全部 true）

```
object_storage:  true   tabular:         true   vector:     true
kv:              true   graph:           true   metadata:   true
sql:             true   distributed:     true   model_serving: true
memory:          true
```

---

## 部署模式

### 单机 docker-compose（v0.2.0）

```bash
# 一键启动全部服务（数据平面 + 3 MCP + ModelServing + ControlCenter + Ray）
docker compose --env-file .env --profile ray --profile all up -d

# 或本地开发（先 build 再 up）
docker buildx bake core --load
docker compose -f docker-compose.yml -f docker-compose.build.yml --env-file .env --profile ray --profile all up -d --no-build
```

### 运行容器（12 平台容器 + meeting-agent）

| 容器 | 端口 | 用途 |
|------|------|------|
| lakemind-server-api | 10823 | REST API 网关 (40+ 路径) |
| lakemind-model-serving | 10824 | 统一模型服务 (litellm + fastembed + SenseVoice funasr) |
| lakemind-postgres | 5432 | 统一元数据 + 图存储 |
| lakemind-seaweedfs | 8333 | S3 对象存储 |
| lakemind-valkey | 6379 | TTL KV 缓存 |
| lakemind-ray-head | 8265 | Ray dashboard (4 CPU) |
| lakemind-ray-worker-1/2 | — | Ray worker (各 4 CPU) |
| lakemind-asset-mcp | 8401 | 认知资产面 (23 tools) |
| lakemind-data-mcp | 8402 | 数据面 (24 tools) |
| lakemind-admin-mcp | 8403 | 管理面 (21 tools) |
| lakemind-control-center | 3000 | 统一管理入口 (前端 + BFF + Steward) |
| meeting-agent | 9100 | 会议 Agent 示例（可选） |

### 引擎切换

所有引擎通过 `engines.yaml` 配置切换，不改代码：

```yaml
cognitive:
  memory:
    plugin: basic        # basic | (future: mem0)
    model_serving_url: "http://lakemind-model-serving:10824"
compute:
  distributed:
    plugin: ray          # embedded | ray
```

---

## 示例

| 示例 | 目录 | 验证内容 | 状态 |
|------|------|----------|------|
| **meeting-agent** | `examples/meeting-agent/` | web→agent→skill→job 全链路：浏览器录音 → Ray job ASR → Ray job 摘要 → Ray job 知识萃取 → 向量入库 → 语义检索 | ✅ v0.2.0 全链路验证通过（133 chunks → 31 ASR → 30 转写 → 6 版纪要 → 7 条知识） |
| **lakemind-connector** | `examples/lakemind-connector/` | Agent 通过 Skill 接入 LakeMind：register_skill → search_skill → 下载执行 → MCP 存取认知资产 | ✅ 已验证 |

> `retail-agent/` 已弃用，不再维护。

详见 `examples/README.md`。

---

## 租户隔离

| 层 | 隔离方式 |
|----|----------|
| S3 | key 前缀 `{tenant_id}/` |
| Iceberg | namespace `{tenant_id}_{domain}` |
| LanceDB | 每租户独立 database |
| Valkey | key 前缀 `{tenant_id}:` |
| PostgreSQL | 行级 `tenant_id` 列（应用层过滤） |

---

## 设计原则

1. **统一认知资产管理与多模态数据管理**  — 提供一套标准化的认知管理接口和多模态数据管理接口
2. **统一存储底座** — SeaweedFS 一个对象存储承载全部数据文件
3. **统一元数据** — PostgreSQL 一个数据库承载全部结构化元数据
4. **计算与引擎分离** — 引擎适配层可替换，计算可走嵌入式或 Ray

---

## 技术栈

全开源组件（Apache 2.0 / MIT / BSD），不引入闭源依赖：

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
| 语音识别 | SenseVoice (funasr) | Apache-2.0 |
| MCP SDK | FastMCP | MIT |
| Agent 框架 | LangGraph | MIT |

---

## License
本项目遵循：Apache 2.0 协议。

---

## 文档索引

### 快速上手

| 文档 | 内容 | 适合谁 |
|------|------|--------|
| [快速入门](docs/quickstart.md) | 从零启动 LakeMind，15 分钟完成全部验证 | 初次使用者 |
| [核心概念与术语表](docs/glossary.md) | Agent 原生、认知资产、MCP 等概念解释 | 新人 |
| [Control Center 使用指南](docs/control-center.md) | 统一管理入口：Mission Control、模型配置、路由管理 | 运维/管理员 |

### 开发与架构

| 文档 | 内容 | 适合谁 |
|------|------|--------|
| [开发指南](docs/develop-guide.md) | 编写 Skill、管理密钥、提交 Ray 作业、构建数据处理流水线 | 业务开发者 |
| [架构设计](docs/architecture.md) | 三平面分层、MCP 职责、数据流、设计决策 | 架构师 |
| [MCP 工具参考](docs/mcp-tools.md) | 68 个工具 + 23 个资源 + 10 个 prompts 完整清单 | Agent 开发者 |
| [REST API 参考](docs/api-reference.md) | 40+ OpenAPI 路径，11 个功能域 | 后端开发者 |
| [Example 开发指南](docs/lakemind-example-develop-guide.md) | 从零构建 Example Agent：MCP 客户端、Skill、Job、Profile、打包发布、Docker 部署全流程 | Agent 开发者 |

### 运维与配置

| 文档 | 内容 | 适合谁 |
|------|------|--------|
| [配置参考](docs/configuration.md) | engines.yaml 引擎配置、环境变量、引擎切换 | 运维 |
| [部署运维](docs/deployment.md) | docker-compose 部署、容器管理、健康检查、故障排查、扩容、备份 | 运维 |
| [变更日志](docs/changelog.md) | 版本变更记录 | 所有人 |

### 社区

| 文档 | 内容 |
|------|------|
| [贡献指南](CONTRIBUTING.md) | 如何报告 Bug、提出新功能、提交代码 |
| [行为准则](CODE_OF_CONDUCT.md) | 社区行为规范 |

---

## 反馈与社区

- **Bug 报告 / 功能请求**：[GitHub Issues](https://github.com/csmw-ai/LakeMind/issues)
- **代码贡献**：请阅读 [贡献指南](CONTRIBUTING.md)
- **发布说明**：[v0.2.0 Release](https://github.com/csmw-ai/LakeMind/releases/tag/v0.2.0)

---

## 路线图

| 版本 | 计划内容 | 状态 |
|------|----------|------|
| **v0.1.0** | MVP：13 容器、10 引擎、68 MCP 工具、Ray 分布式计算 | ✅ 已发布 |
| **v0.2.0** | ControlCenter 统一管理（10 页面）、RBAC、Job Runtime、模型管理、Meeting Agent 全链路 | ✅ 已发布 |
| **v0.3** | LakeMindStudio（Tauri 桌面客户端） | 规划中 |
