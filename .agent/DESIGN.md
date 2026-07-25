# DESIGN.md — LakeMind 架构设计规范

> 本文件是 LakeMind 的架构设计规范，描述系统分层、组件职责、数据流与关键设计决策。
> 总文件为 `AGENTS.md`，开发规范见 `.agent/SPEC.md`，当前状态见 `.agent/STATE.md`。

---

## 1. 总体架构

### 1.1 三平面 + 三 MCP

```
┌─────────────────────────────────────────────────────────┐
│                    开发平面                               │
│               LakeMindStudio (Tauri)                      │
└──────────────────────┬──────────────────────────────────┘
                       │ MCP Client
┌──────────────────────▼──────────────────────────────────┐
│                   运行平面                                │
│                                                          │
│  200 Agents ──→ AssetMCP (:8401)  ← 资产面              │
│  Steward ─────→ DataMCP  (:8402)  ← 数据面              │
│  Steward ─────→ AdminMCP (:8403)  ← 管理面              │
│  Steward (LangGraph, :8500)         ← 运维 Agent         │
│  Monitor (Express, :3000)           ← 人类仪表板         │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API (:10823)
┌──────────────────────▼──────────────────────────────────┐
│                    数据平面                               │
│               LakeMindServer (:10823)                     │
│  REST API + 9 引擎                                        │
│  SeaweedFS (:8333) · PostgreSQL (:5432) · Valkey (:6379) │
│  Ray (:8265, 3 节点 12 CPU)                              │
│               LakeMindModelServing (:10824)               │
│  litellm · fastembed · SenseVoice funasr                 │
└─────────────────────────────────────────────────────────┘
```

### 1.2 两层模型

| 层 | 职责 | 面向 |
|----|------|------|
| **Data 层** | 多模态数据底座。通过 REST API 透传，不做语义解释。数据是什么、存哪、怎么读写。 | Steward / 高级 Agent |
| **Asset 层** | 面向 Agent 认知模型的语义封装。预置 4 类资产，声明式 YAML 可扩展。 | 业务 Agent |

### 1.3 三 MCP 职责划分

| MCP | 端口 | Scope | 面向 | 职责 | Tools | Prompts | Resources |
|-----|------|-------|------|------|-------|---------|-----------|
| AssetMCP | 8401 | `asset` | 业务 Agent | 知识/记忆/技能/本体 | 23 | 6 | 11 |
| DataMCP | 8402 | `data` | Steward / 高级 Agent | Data 层 REST API 透传 | 24 | 2 | 6 |
| AdminMCP | 8403 | `admin` | Steward | 用户/租户/Token/健康 | 21 | 2 | 6 |

> **MCP 三要素**：每个 MCP 都有 Tools（操作）+ Resources（只读浏览）+ Prompts（使用指南）。
> 合计：68 tools, 10 prompts, 23 resources。

---

## 2. 数据平面设计

### 2.1 LakeMindServer REST API

REST API 端口 `:10823`，40+ 路径，10 引擎。认证方式：

```
Authorization: Bearer lakemind-internal-api-key
X-Tenant-Id: retail
X-Agent-Id: agent-001
X-Scopes: asset,data,admin
```

### 2.2 统一 Metadata Hub：PostgreSQL 16

**一个数据库技术栈，一个 PostgreSQL 实例**，承载全部结构化元数据：

| 用途 | 机制 | 表 |
|------|------|-----|
| Iceberg Catalog | PyIceberg SQL catalog | `iceberg_tables`, `iceberg_namespace_properties`（自动创建） |
| 图存储 | PG 原生表 + JSONB | `graph_nodes`, `graph_edges` |
| 用户/租户 | 普通 PG 表 | `tenants`, `users` |
| Token 管理 | PG 表 | `tokens` |
| 资产定义 | PG 表 | `asset_types` |
| 记忆变更历史 | PG 表 | `memory_history` |

> **设计决策**：移除 Gravitino（JVM，H2），用 PostgreSQL 直接作为 PyIceberg SQL catalog。
> AGE 图扩展因编译超时用 PG 原生表替代，功能等价。

### 2.3 引擎清单（9 个）

| 引擎 | 插件名 | 用途 | 状态 |
|------|--------|------|------|
| 对象存储 | `seaweedfs` | S3 兼容文件存储 | ✅ |
| 表格式 | `iceberg` | 结构化数据（PG catalog） | ✅ |
| 向量 | `lancedb` | 向量索引、语义检索 | ✅ |
| KV 缓存 | `valkey` | TTL KV（Redis 兼容，BSD 3-Clause） | ✅ |
| 图 | `postgres_graph` | PG 原生表 graph_nodes/edges | ✅ |
| 元数据 | `postgres` | 用户/租户/Token/资产类型 | ✅ |
| SQL | `duckdb` | 即席计算、Parquet 直读 | ✅ |
| 分布式计算 | `ray` | 3 节点 12 CPU，7 任务类型 | ✅ |
| 记忆 | `basic` | mem0 风格 8 方法 + LLM 事实抽取 | ✅ |

> Embedding 和 LLM 网关已移至 LakeMindModelServing（:10824）

### 2.4 容器清单（13 个）

| 容器 | 镜像 | 端口 | 用途 |
|------|------|------|------|
| server-api | lakemind/server-api | 10823 | REST API + 9 引擎 |
| model-serving | lakemind/model-serving | 10824 | 统一模型服务（litellm + fastembed + SenseVoice funasr） |
| postgres | lakemind/postgres-age:16 | 5432 | Metadata Hub |
| seaweedfs | chrislusf/seaweedfs:latest | 8333 | S3 对象存储 |
| valkey | valkey/valkey:8.0 | 6379 | TTL KV 缓存（BSD 3-Clause） |
| ray-head | rayproject/ray:2.41.0-py3.12 | 8265 | Ray 主节点 |
| ray-worker-1 | rayproject/ray:2.41.0-py3.12 | — | Ray 工作节点 |
| ray-worker-2 | rayproject/ray:2.41.0-py3.12 | — | Ray 工作节点 |
| asset-mcp | lakemind/asset-mcp | 8401 | 资产面 MCP |
| data-mcp | lakemind/data-mcp | 8402 | 数据面 MCP |
| admin-mcp | lakemind/admin-mcp | 8403 | 管理面 MCP |
| steward | lakemind/steward | 8500 | 运维 Agent |
| monitor | lakemind/monitor | 3000 | 人类仪表板 |

### 2.5 数据域 → 引擎映射

| 数据域 | 引擎 | 资源 URI | MCP |
|--------|------|----------|-----|
| 结构化数据 | Iceberg + PG catalog | DataMCP（REST API 透传） | DataMCP |
| 知识/多模态 RAG | Lance + LanceDB（OKF 格式） | `lake://knowledge` | AssetMCP |
| 短期/工作记忆 | Valkey (TTL KV) | `lake://memory` | AssetMCP |
| 长期/语义记忆 | Lance 向量 + PG 元信息（mem0 风格） | `lake://memory` | AssetMCP |
| Skills | S3 + PG + LanceDB（受控 Job Runtime 执行） | `lake://skills` | AssetMCP |
| 本体/图 | PG graph_nodes/edges | `lake://ontology` | AssetMCP |

> **长期记忆双表设计**：Lance 向量表 + PG 元信息小表，通过 `lance_uri` 字段关联，不合并成单表。

---

## 3. 资产层设计

### 3.1 默认 4 类资产

| 资产 | 能力 | 存储 | 工具 |
|------|------|------|------|
| **Knowledge** | search, ingest, register, get, list, list_concepts, delete | LanceDB 向量 + S3 .md 文件 + PG 图 | 7 tools |
| **Skills** | search, register, get, list, delete | S3 代码 + PG 元信息 + LanceDB 向量 | 5 tools |
| **Memory** | add, search, get, list, update, delete, clear, history | Valkey 短期 + Lance 长期 + PG 历史 | 8 tools |
| **Ontology** | query, update, delete | PG graph_nodes/edges | 3 tools |

### 3.2 OKF 知识格式（Open Knowledge Format）

```markdown
---
title: 概念标题
type: Table
kb: knowledge-base-name
concepts: [concept1, concept2]
links: [../other/concept.md]
---

# 正文内容

markdown body...
```

- YAML frontmatter 存元信息，markdown body 存正文。
- 交叉链接通过正则解析，存入 PG graph_edges。
- S3 存 .md 文件，LanceDB 对 body 做向量索引。

### 3.3 mem0 风格记忆

8 方法，LLM 事实抽取 + 哈希去重：

| 方法 | 说明 |
|------|------|
| `add(messages)` | LLM 抽取事实 → 哈希去重 → Lance 向量写入 + PG 元信息 |
| `search(query)` | 混合检索：Lance 语义 + Valkey 关键词 |
| `get(memory_id)` | 取单条记忆 |
| `list_all(filters)` | 列表（支持过滤） |
| `update(memory_id, content)` | 更新内容 + 记录变更历史 |
| `delete(memory_id)` | 删除 |
| `clear()` | 清空当前 Agent/Tenant 的全部记忆 |
| `history(memory_id)` | 查看变更历史（PG memory_history 表） |

> LLM 事实抽取是"智能存储"而非"执行"——LLM 网关是内部平台能力，不通过 MCP 暴露。

### 3.4 声明式资产扩展

```
assets/
├── native/              # 4 个默认资产（内置）
│   ├── knowledge.yaml
│   ├── skill.yaml
│   ├── memory.yaml
│   └── ontology.yaml
├── extension/           # 用户自定义（自动扫描）
└── engine_patterns/     # 预置引擎模式实现
```

- **添加**：写 YAML → 放 `extension/` 或 AdminMCP `register_asset_type(yaml)` → AssetMCP 热加载
- **删除**：AdminMCP `unregister_asset_type(type)` → 仅删定义，不删底层数据

---

## 4. 运行平面设计

### 4.1 LakeMindAssetMCP（资产面）

```
AssetMCP (:8401)
├── 认证：Bearer Token, scope=asset
├── 23 tools:
│   ├── knowledge: register, ingest, search, get, list, list_concepts, delete (7)
│   ├── memory: add, search, get, list, update, delete, clear, history (8)
│   ├── skill: search, register, get, list, delete (5)
│   └── ontology: query, update, delete (3)
├── 11 resources: capabilities, workspace, knowledge, knowledge/{kb}/{id},
│                 skills, skills/{name}, memory, memory/{id},
│                 ontology, ontology/{concept}
├── 6 prompts: search_knowledge_guide, okf_concept_guide, register_skill_guide,
│              add_memory_guide, search_memory_guide, query_ontology_guide
└── 无 lake://system/health（健康属于 AdminMCP/DataMCP）
```

- `execute_skill` 已移除——改为 JobService 受控执行，Agent 通过 JobService.submit(skill_ref, inputs) 提交。
- 无状态，可多副本。

### 4.2 LakeMindDataMCP（数据面）

```
DataMCP (:8402)
├── 认证：Bearer Token, scope=data
├── 24 tools:
│   ├── 表操作: query_table, write_table, sql_query, list_tables, describe_table,
│   │          create_table, drop_table (7)
│   ├── 向量: vector_search (1)
│   ├── S3: s3_get, s3_put, s3_list, s3_delete (4)
│   ├── KV: kv_get, kv_set, kv_delete, kv_scan (4)
│   └── 图: graph_query, graph_update (2)
├── 6 resources: system/health, tables, tables/{ns}/{table},
│                vectors, vectors/{table}, graph
├── 2 prompts: sql_query_guide, data_exploration_guide
└── 全量透传（通过 REST API），不做语义包装
```

### 4.3 LakeMindAdminMCP（管理面）

```
AdminMCP (:8403)
├── 认证：Bearer Token, scope=admin
├── 21 tools:
│   ├── 用户: create_user, get_user, list_users, update_user, delete_user (5)
│   ├── 租户: create_tenant, get_tenant, list_tenants (3)
│   ├── Token: issue_token, revoke_token, list_tokens (3)
│   ├── 资产类型: register_asset_type, unregister_asset_type, list_asset_types (3)
│   └── 平台: get_platform_health, get_node_status, get_metrics (3)
├── 6 resources: admin/health, admin/tenants, admin/users,
│                admin/tokens, admin/asset-types, admin/nodes
├── 2 prompts: inspect_platform_guide, manage_user_guide
└── 通过 REST API 访问 Server（不直连任何引擎）
```

### 4.4 LakeMindSteward（运维 Agent）

```
Steward (:8500)
├── LangGraph 状态图
│   ├── 巡检工作流：check_health → analyze → report
│   └── 对话管理：意图识别 → MCP 工具调用 → LLM 格式化输出
├── LLM 对话：通过 ModelServing (:10824) 驱动，model=deepseek-v4-flash
├── MCP Client（asset + data + admin 三面）
├── 端点：POST /chat, POST /inspect, GET /health
└── MCP 不可用时降级返回原始数据
```

### 4.5 LakeMindMonitor（人类仪表板）

```
Monitor (:3000)
├── Express + 静态 HTML（极轻）
├── API 代理层 → 3 MCP（只读）+ Steward（chat/inspect）
├── 5 页面：Dashboard / Asset / Data / Admin / Chat
├── 无自有 DB · 无自有用户系统
└── 认证：用平台 Token（配置文件静态）
```

### 4.6 LakeMindStudio（开发平面 · 待开发）

```
Studio (Tauri 2.0)
├── Vue 3 + Vite + TypeScript（前端）
├── Tauri Rust Core（本地文件系统 / Git / 进程管理）
├── MCP Client（直连 3 MCP）
├── 资产设计器：YAML 编辑 + 实时预览 + 一键注册
├── MCP 调试台：在线调用工具/资源
└── Skill 脚手架：模板生成 + 本地沙箱
```

---

## 5. Token 体系

| Token | Agent | Tenant | Scopes | 接入 |
|-------|-------|--------|--------|------|
| `test-business-token` | agent-business-01 | retail | `asset` | AssetMCP |
| `test-steward-token` | steward | platform | `asset, data, admin` | 3 MCP |
| `test-monitor-token` | monitor | platform | `asset` | AssetMCP (只读) |

- 签发：AdminMCP `issue_token` → 存 PG
- 校验：各 MCP AuthMiddleware 校验 Bearer Token + scope
- MVP 兼容配置文件静态 Token

---

## 6. 并发与性能设计

### 6.1 200 Agent 场景

| 瓶颈 | 解决方案 | 状态 |
|------|---------|------|
| Iceberg 元数据并发写 | PostgreSQL（已实现） | ✅ |
| Embedding CPU 密集 | Ray actor 批处理（已实现） | ✅ |
| 大向量检索 | IVF_PQ 索引 + Ray 分布式查询 | ✅ |
| MCP 单进程 | 每类 MCP 多副本 + 负载均衡（生产阶段） | P2 |
| Lance 并发写 | 每表 `threading.Lock` 串行化同表操作 | ✅ |
| async 端点同步 I/O 阻塞 | `asyncio.to_thread()` 包全部同步引擎调用 | ✅ |
| REST JSON 高维向量传输 | Arrow IPC 二进制端点 (`add_arrow`) | ✅ |
| 全局锁串行化 LLM/Embedding | 精确锁只保护 LanceDB 临界区 | ✅ |

### 6.2 当前策略

- 嵌入式引擎在 Server 进程内运行，MCP 通过 REST API 调用。
- Ray 3 节点 5 CPU（head=1, worker=2×2），重计算提交 Ray。
- fastembed ONNX CPU ~2ms/text。
- PostgreSQL 连接池。
- uvicorn workers=1（Docker Desktop IPv6 限制，P0 to_thread 已解并发）。

### 6.3 性能优化实测结果（v0.2.0, 2026-07-21）

> 4 轮压测：v1 3P/6F → v2 4P/5F → v3 5P/4F → **v4 7P/2F**
> 详见 `reports/2026.0721.性能优化全轮次总结报告.md`

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 向量搜索 p50 | ~1400ms | 60ms | **23x** |
| 向量搜索 L0 (引擎层) | 1220ms | 14.2ms | **86x** (IVF_PQ) |
| 向量搜索 10 并发错误率 | 86.8% | 0% | **根治** |
| Memory Add p99 | 11s | 33ms | **335x** |
| Memory 10 并发 QPS | 1.6 | 17.8 | **11x** |
| 文件上传成功率 | 0% | 100% | **根治** |
| 向量入库 (Arrow IPC) | 700 vec/s (JSON) | 8081 vec/s | **12x** |
| 混合 30 并发错误率 | 100% | 0% | **根治** |

### 6.4 关键技术决策

| 决策 | 理由 |
|------|------|
| `asyncio.to_thread` 包同步 I/O | boto3/LanceDB/Valkey 均同步库，直接调阻塞事件循环 |
| Arrow IPC 替代 JSON 传向量 | 768 维浮点 JSON 编解码占主要耗时，Arrow 零拷贝 20x |
| IVF_PQ 索引 (128 partitions) | 121K 向量暴力扫描 1220ms→14ms，Recall@10=1.0 |
| 每表锁替代全局锁 | 不同表可并行，同表串行防 Rust panic |
| 精确锁替代方法锁 | 只锁 LanceDB 临界区，LLM/Embedding/PG 并发执行 |
| Table Handle 缓存 | 避免重复 `open_table()` 开销 |
| Ray CPU 12→5 | 过度声明挤占 ModelServing，5 CPU 足够 |

---

## 7. 设计原则（不可偏离）

1. **统一认知资产管理与多模态数据管理** — 提供一套标准化的认知管理接口和多模态数据管理接口
2. **统一存储底座** — SeaweedFS 一个对象存储承载全部数据文件
3. **统一元数据** — PostgreSQL 一个数据库承载全部结构化元数据
4. **计算与引擎分离** — 引擎适配层可替换，计算可走嵌入式或 Ray

---

## 8. 关键设计决策记录

| 决策 | 理由 |
|------|------|
| PostgreSQL 替代 Gravitino + SQLite | 少一个 JVM 服务，并发安全，技术栈更简 |
| 3 MCP 拆分替代单体 | 独立部署、独立扩缩容、避免单点故障 |
| 声明式 YAML 替代代码继承 | 用户无需写代码即可扩展资产 |
| fastembed 替代 SHA256 | 真实语义检索，ONNX CPU ~2ms |
| Express 替代 Nuxt 3 | npm install 超时，Express 构建秒级 |
| PG 原生表替代 AGE | AGE 编译超时，原生表功能等价 |
| `execute_skill` 移除 | 改为 JobService 受控执行，Agent 通过 JobService.submit 提交 |
| Memory 采用 mem0 风格 | LLM 事实抽取 + 哈希去重，智能存储 |
| Knowledge 采用 OKF 格式 | YAML frontmatter + markdown body，交叉链接存 PG 图 |
| LLM 网关为内部能力 | 不通过 MCP 暴露，Agent 用自己的 LLM |
| LLM 网关独立为 LakeMindModelServing | litellm 替代手写 GatewayLLM，新增 ASR，统一模型服务 |
| Ray 已实现 | 3 节点 12 CPU，7 任务类型，12/12 PASS |
| experience 积淀进 memory.kind | 减少资产类型，kind 区分 general/experience/reflection |
| Monitor 无自有 DB | 纯代理层，状态全靠 AdminMCP |
| Dragonfly 替换为 Valkey | Dragonfly BSL 1.1 禁止 SaaS，Valkey BSD 3-Clause 允许商用 |
