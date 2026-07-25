# 架构设计

## 1. 总体架构

LakeMind 采用三平面分层架构：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            开发平面                                      │
│                     LakeMindStudio (Tauri 桌面)  （后续版本实现）          │
│              资产设计器 · MCP调试台 · 数据任务开发 · CI/CD                 │
└─────────────────────────────────────────────────────────────────────────┘
                                       │ MCP Client
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          运行平面 · Agent 侧                             │
│                                                                         │
│  ┌──────────────┐     ┌──────────────────────────────────────────────┐  │
│  │  N Agents    │     │         LakeMindControlCenter                 │  │
│  │  (业务 Agent) │     │    前端(:3000) + BFF(:3001) + Steward(:3002)  │  │
│  └──────┬───────┘     │    10 页面 · Mission Control · 模型配置        │  │
│         │ asset                    │                   │ admin           │
│         ▼                          ▼                   ▼                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                  │
│  │ AssetMCP    │    │  DataMCP    │    │  AdminMCP   │                  │
│  │  :8401      │    │  :8402      │    │  :8403      │                  │
│  │ 认知资产面   │    │  数据面     │    │  管理面     │                  │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                  │
└─────────┼──────────────────┼──────────────────┼─────────────────────────┘
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        数据平面 · LakeMindServer                          │
│                                                                         │
│  REST API 网关 (:10823) — 统一引擎入口，40+ OpenAPI 路径                  │
│                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐          │
│  │  数据存储引擎    │  │  数据计算引擎    │  │  认知计算引擎    │          │
│  │  SeaweedFS (S3) │  │  Ray (分布式)   │  │  Memory Engine  │          │
│  │  Iceberg (表)   │  │  DuckDB (SQL)  │  │                 │          │
│  │  Lance/LanceDB  │  │                 │  │                 │          │
│  │  Valkey (KV)   │  │                 │  │                 │          │
│  │  PostgreSQL     │  │                 │  │                 │          │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘          │
└─────────────────────────────────────────────────────────────────────────┘
```

> Embedding (fastembed) / LLM 网关 (litellm) / ASR (SenseVoice funasr) 已独立为 **LakeMindModelServing (:10824)**，不在 Server 进程内。

## 2. 2 层数据类型

LakeMind 将 Agent 需要的一切数据分为两层：

### 认知资产层 (ASSET)

面向 Agent 认知模型的语义封装。声明式 YAML 定义，预置 4 类，可删可扩。Agent 不关心底层存储，只声明"我需要一个知识库"。

| 资产 | 能力 | 存储 | 工具 |
|------|------|------|------|
| **Knowledge** | search, ingest, get, list, list_concepts, delete | LanceDB 向量 + S3 .md 文件 + PG 图 | 7 OKF tools |
| **Skills** | search, register, get, list, delete | S3 代码 + PG 元信息 + LanceDB 向量 | 5 tools（无 execute_skill） |
| **Memory** | add, search, get, list, update, delete, clear, history | Valkey 短期 + Lance 长期 + PG 历史 | 8 mem0-style tools |
| **Ontology** | query, update, delete | PG graph_nodes/edges | 3 tools |

### 数据层 (DATA)

多模态数据底座，通过 REST API 透传不做语义解释。数据是什么、存哪、怎么读写。Iceberg 表、Lance 向量、S3 文件、Valkey KV、PG 图——通过 REST API 全量透传给 Steward 和高级 Agent。

## 3. 3 个 MCP 服务

Agent 通过 MCP 协议直连 LakeMind。三个 MCP 独立部署、各自水平扩展、scope 隔离：

| MCP | 端口 | Scope | 面向 | 工具数 | 职责 |
|-----|------|-------|------|--------|------|
| LakeMindAssetMCP | 8401 | `asset` | 业务 Agent | 23 tools, 11 resources, 6 prompts | 认知资产面 |
| LakeMindDataMCP | 8402 | `data` | Steward / 高级 Agent | 24 tools, 6 resources, 2 prompts | 数据面 REST API 透传 |
| LakeMindAdminMCP | 8403 | `admin` | Steward | 21 tools, 6 resources, 2 prompts | 管理面 |

MCP 是瘦客户端，不直连引擎，通过 httpx 连接池调用 LakeMindServer REST API。

## 4. 核心服务 LakeMindServer

LakeMindServer 是数据平面的核心，提供 REST API 网关和 3 大引擎类别。

### 4.1 REST API 网关

- 40+ OpenAPI 路径，覆盖 11 个功能域
- Bearer Token 认证 + X-Tenant-Id / X-Agent-Id / X-Scopes 三级上下文
- 10 引擎健康检查
- httpx 连接池（max 50 连接，10 keepalive）

### 4.2 数据存储引擎

| 引擎 | 选型 | 用途 | 可插拔替换 |
|------|------|------|-----------|
| 对象存储 | SeaweedFS | S3 兼容 | AWS S3 / 阿里云 OSS / 华为云 OBS |
| 表格式 | Apache Iceberg | 结构化表 | — |
| 向量 / 多模态 | PyLance + LanceDB | 向量检索 | Milvus / Qdrant |
| KV 缓存 | Valkey | TTL KV | Redis |
| 统一元数据 | PostgreSQL 16 | Iceberg catalog + 图 + 用户/租户/Token | MySQL |
| 图 / 本体 | PG 原生表 | graph_nodes / graph_edges + JSONB | AGE / Neo4j |

### 4.3 数据计算引擎

| 引擎 | 选型 | 用途 | 可插拔替换 |
|------|------|------|-----------|
| 即席 SQL | DuckDB | 进程内轻量 SQL | — |
| 分布式计算 | Ray 2.41 | 3 节点 12 CPU | Embedded（降级） |

### 4.4 认知计算引擎

| 引擎 | 选型 | 用途 | 可插拔替换 |
|------|------|------|-----------|
| 记忆引擎 | BasicMemory | 短期 Valkey TTL + 长期 Lance 向量 | mem0 |

> Embedding (fastembed) / LLM 网关 (litellm) / ASR (SenseVoice funasr) 已独立为 **LakeMindModelServing (:10824)** 统一模型服务。

### 4.5 引擎插件架构

所有引擎遵循统一的插件接口：

```
Protocol (接口定义)
  └── Plugin (具体实现)
       └── engines.yaml (配置选择)
```

通过 `engines.yaml` 切换插件，不改代码：

```yaml
cognitive:
  memory:
    plugin: basic
    model_serving_url: "http://lakemind-model-serving:10824"
```

## 5. 配套工具

| 工具 | 定位 | 状态 |
|------|------|------|
| LakeMindControlCenter | 统一管理入口（前端 + BFF + Steward）：10 页面，Mission Control 仪表板，模型配置与路由 | ✅ v0.2.0 |
| LakeMindModelServing | 统一模型服务（litellm + fastembed + SenseVoice funasr） | ✅ |
| LakeMindStudio | 桌面客户端（Tauri）：资产设计器、MCP 调试台 | 🔨 待开发 |

> v0.1.0 的 `LakeMindSteward` + `LakeMindMonitor` 已在 v0.2.0 合并迁入 `LakeMindControlCenter`，不再独立部署。

## 6. 数据域 → 引擎映射

| 数据域 | 引擎 | MCP 资产 | 资源 URI |
|--------|------|---------|----------|
| 结构化数据 | Iceberg + PG catalog | lake://data | DataMCP |
| 知识 / 多模态 RAG | Lance + LanceDB | lake://knowledge | AssetMCP |
| 短期/工作记忆 | Valkey (TTL KV) | lake://memory | AssetMCP |
| 长期/语义记忆 | Lance 向量 + PG 元信息（mem0 风格） | lake://memory | AssetMCP |
| Skills | S3 + PG + LanceDB | lake://skills | AssetMCP |
| 本体 / 图 | PG graph_nodes/edges | lake://ontology | AssetMCP |
| LLM 推理 | litellm → 外部 API | /v1/chat/completions | ModelServing (:10824) |

> 长期记忆采用 Lance 向量 + PG 元信息双表设计（mem0 风格），通过 lance_uri 字段关联。

## 7. 租户隔离

| 层 | 隔离方式 |
|----|----------|
| S3 | key 前缀 {tenant_id}/ |
| Iceberg | namespace {tenant_id}_{domain} |
| LanceDB | 每租户独立 database |
| Valkey | key 前缀 {tenant_id}: |
| PostgreSQL | 行级 tenant_id 列（应用层过滤） |

## 8. Token 体系

| Token | Agent | Tenant | Scopes | 接入 |
|-------|-------|--------|--------|------|
| test-business-token | agent-business-01 | retail | asset | AssetMCP |
| test-steward-token | steward | platform | asset, data, admin | 3 MCP |
| test-monitor-token | monitor | platform | asset | AssetMCP (只读) |

## 9. 设计原则

1. **统一认知资产管理与多模态数据管理** — 提供一套标准化的认知管理接口和多模态数据管理接口
2. **统一存储底座** — SeaweedFS 一个对象存储承载全部数据文件
3. **统一元数据** — PostgreSQL 一个数据库承载全部结构化元数据
4. **计算与引擎分离** — 引擎适配层可替换，计算可走嵌入式或 Ray

## 10. 关键设计决策

| 决策 | 理由 |
|------|------|
| PostgreSQL 替代 Gravitino + SQLite | 少一个 JVM 服务，并发安全，技术栈更简 |
| 3 MCP 拆分替代单体 | 独立部署、独立扩缩容、避免单点故障 |
| 声明式 YAML 替代代码继承 | 用户无需写代码即可扩展资产 |
| fastembed 替代 SHA256 | 真实语义检索，ONNX CPU ~2ms |
| PG 原生表替代 AGE | AGE 编译超时，原生表功能等价 |
| Ray 自建镜像 | Docker Hub 不可达，从 python:3.12-slim 自建 |
| LLM 网关 → litellm | 初期自建后替换为 litellm Router，功能更全，支持多 provider 路由 + fallback |
