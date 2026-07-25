# AGENTS.md — LakeMind AI Agent 协作约定

> 本文件是**总文件**，定义项目结构、技术栈、设计原则与协作约定。
> 详细设计见 `.agent/DESIGN.md`，开发规范见 `.agent/SPEC.md`，当前状态见 `.agent/STATE.md`。

---

## 1. 项目定位

LakeMind 是**认知资产存取平台 + 受控 Job Runtime**。LakeMind 不是通用 Agent Runtime，不负责运行 Agent 的完整推理循环、业务决策和自主行为；但提供受控 Job Runtime，用于执行 Agent 触发的、以 Skill 为定义的确定性或可复现任务。
Agent 通过 MCP 检索和存取知识、记忆、技能等认知资产，通过 JobService 提交受控 Job。

## 2. 仓库包结构

| 目录 | 平面 | 职责 | 状态 |
|------|------|------|------|
| `LakeMindServer/` | 数据平面 | 存储与计算底座（REST API + 10 引擎 + 13 容器） | ✅ 已完成 |
| `LakeMindModelServing/` | 模型平面 | 统一模型服务（litellm 网关 + fastembed 嵌入 + SenseVoice funasr 语音识别） | ✅ 已完成 |
| `LakeMindMCP/` | 运行平面 | 3 MCP 编排（docker-compose + --profile all） | ✅ 已完成 |
| `LakeMindMCP/LakeMindAssetMCP/` | 运行平面 | 资产面 MCP（知识/记忆/技能/本体），23 tools | ✅ 已完成 |
| `LakeMindMCP/LakeMindDataMCP/` | 运行平面 | 数据面 MCP（通过 REST API 透传，不做语义包装），24 tools | ✅ 已完成 |
| `LakeMindMCP/LakeMindAdminMCP/` | 运行平面 | 管理面 MCP（用户/租户/Token/健康），21 tools | ✅ 已完成 |
| `LakeMindControlCenter/` | 运行平面 | 统一管理入口（前端 + BFF + Steward，10 页面） | ✅ v0.2.0 |
| `LakeMindStudio/` | 开发平面 | 资产设计、MCP 调试、Skill 脚手架（Tauri） | ❌ 未开始（P2） |

## 3. 访问拓扑

```
Agent ──→ AssetMCP (:8401)  ← 资产面（知识/记忆/技能/本体）
Steward ─→ DataMCP  (:8402)  ← 数据面（REST API 透传）
Steward ─→ AdminMCP (:8403)  ← 管理面（用户/租户/健康）
ControlCenter (:3000) ← 前端 + BFF (:3001) + Steward (:3002，内嵌)
Monitor ─→ 3 MCP（只读）+ Steward（chat/inspect）  ← 已迁入 ControlCenter
Studio  ─→ 3 MCP + Git
         │
         ▼
LakeMindServer (:10823)  ← 统一 REST API，10 引擎
  SeaweedFS · PostgreSQL · Valkey · Ray
          │
          ▼
LakeMindModelServing (:10824)  ← 统一模型服务（litellm + fastembed + SenseVoice funasr）
  Server / Ray workers ──→ ModelServing（嵌入 / LLM / ASR）
```

- **MCP 是 Agent 唯一入口**，嵌入式引擎在 Server 进程中运行，MCP 通过 REST API 调用，不直连任何底层引擎。
- **MCP 三要素**：Tools（操作）+ Resources（只读浏览）+ Prompts（使用指南），每个 MCP 都有全部三要素。
- **ControlCenter** 统一了 v0.1.0 的 Steward + Monitor：前端（nginx :3000）→ BFF（FastAPI :3001）→ Steward（LangGraph :3002）。Steward 走 MCP admin 域。
- **Monitor** 已迁入 ControlCenter（Mission Control 页面），不再独立部署。

## 4. 技术栈（锁定，不擅自替换）

全开源组件（Apache 2.0 / MIT / BSD）：

| 组件 | 选型 | 用途 |
|------|------|------|
| 对象存储 | **SeaweedFS** | S3 兼容，承载全部数据文件 |
| 统一元数据 | **PostgreSQL 16** | Iceberg SQL catalog + 图 + 用户/租户/Token（替代 Gravitino） |
| 表格式 | **Apache Iceberg** | 结构化数据 |
| 向量/多模态 | **PyLance + LanceDB** | 知识库向量、语义检索（PyPI 包名 `pylance`） |
| 缓存 | **Valkey** | TTL KV（Redis 兼容协议，BSD 3-Clause） |
| 即席计算 | **DuckDB** | 跨表 SQL、Parquet 直读 |
| 分布式计算 | **Ray 2.41.0** | 3 节点 12 CPU（已实现） |
| Embedding | **fastembed** | jinaai/jina-embeddings-v2-base-zh, dim=768（中英混合），由 ModelServing 提供 |
| LLM 网关 | **litellm** | 内部能力，路由多 provider（不通过 MCP 暴露）（PyPI 包名 `litellm`） |
| ASR | **SenseVoice (funasr)** | 本地语音识别（iic/SenseVoiceSmall, CPU, funasr + PyTorch，自带标点 + ITN，fsmn-vad VAD + hotwords + loudnorm 归一化） |
| MCP SDK | **FastMCP** | tools + resources + prompts 三要素 |
| Agent 框架 | **LangGraph** | Steward 巡检工作流 |

> **不引入**：Apache Gravitino（已用 PG 替代）、Apache Ranger（生产阶段）、Trino、Daft。

## 5. 数据域 → 引擎映射

| 数据域 | 引擎 | MCP 资产 |
|--------|------|---------|
| 结构化数据 | Iceberg + PG catalog | DataMCP（REST API 透传） |
| 知识 / 多模态 RAG | Lance + LanceDB（OKF 格式） | `lake://knowledge` |
| 短期/工作记忆 | Valkey（TTL KV） | `lake://memory` |
| 长期/语义记忆 | Lance 向量 + PG 元信息（mem0 风格） | `lake://memory` |
| Skills | S3 + PG + LanceDB（不执行） | `lake://skills` |
| 本体/图 | PG graph_nodes/edges | `lake://ontology` |

## 6. 设计原则（不可偏离）

1. **统一认知资产管理与多模态数据管理** — 提供一套标准化的认知管理接口和多模态数据管理接口
2. **统一存储底座** — SeaweedFS 一个对象存储
3. **统一元数据** — PostgreSQL 一个数据库
4. **计算与引擎分离** — 引擎可替换，计算可走嵌入式或 Ray
5. **禁止运行时动态下载模型** — 所有模型（ASR、Embedding、本地 LLM 等）必须在部署前预下载到持久化存储，运行时只从本地路径加载。模型缺失时返回错误，不触发下载。预下载通过独立的一次性容器（如 `asr-model-init`）或模型 Bundle 镜像完成。

## 7. 关键设计决策

- **`execute_skill` 已移除** — 改为 JobService 受控执行，Agent 通过 JobService.submit(skill_ref, inputs) 提交以 Skill 为定义的确定性或可复现任务。
- **Memory 采用 mem0 风格** — 8 方法（add/search/get/list/update/delete/clear/history），LLM 事实抽取 + 哈希去重。
- **Knowledge 采用 OKF 格式** — YAML frontmatter + markdown body，交叉链接存 PG 图。
- **长期记忆双表设计** — Lance 向量表 + PG 元信息小表，通过 `lance_uri` 关联，不合并成单表。
- **LLM 网关是内部能力** — litellm 网关独立为 LakeMindModelServing，不通过 MCP 暴露，Agent 使用自己的 LLM。
- **LLM 网关独立为 LakeMindModelServing** — litellm 替代手写 GatewayLLM，新增 ASR，统一模型服务。Steward 通过 ModelServing LLM 驱动对话。

## 8. 约定

- 根目录 `docker-compose.yml` 是唯一统一编排文件（纯运行，不含 build）。
- 开发覆盖：`docker-compose.build.yml`（将 GHCR 镜像替换为本地 dev 标签）。
- 构建定义：`docker-bake.hcl`（本地和 CI 的唯一构建入口）。
- 依赖锁定：`uv.lock`（Python）+ `package-lock.json`（前端）。
- 5 个自研镜像：`postgres-age`、`server-api`、`mcp-suite`、`model-serving`、`control-center`。
- 3 个 MCP 复用同一 `mcp-suite` 镜像，通过不同 `command` 启动。
- Ray 使用官方镜像 `rayproject/ray:2.41.0-py312`。
- 启动顺序：数据平面 → 运行平面 → 模型平面 → 管理平面。
- 本地开发：`docker buildx bake core --load` → `docker compose -f docker-compose.yml -f docker-compose.build.yml --env-file .env --profile ray --profile all up -d --no-build`。
- 正式部署：`docker compose --env-file .env pull` → `docker compose --env-file .env --profile ray --profile all up -d --no-build`。
- 跨包依赖只通过 MCP 协议（运行平面）或 REST API（数据平面，:10823），不直连任何底层引擎。
- 验证脚本放 `scripts/`，主验证脚本 `scripts/verify_full.py`（L0-L9 全分层）。
- 代码不加注释，除非逻辑非显而易见。
- 设计文档用中文，代码标识符用英文。
- PowerShell 下读写中文文件名需设置 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`。

## 9. 详细文档索引

| 文件 | 内容 |
|------|------|
| `.agent/DESIGN.md` | 架构设计规范（三平面、MCP 职责、数据流、设计决策） |
| `.agent/SPEC.md` | 开发规范（包结构、代码约定、Docker、验证） |
| `.agent/STATE.md` | 当前状态（进度、容器、验证结果、已知问题） |
| `docs/` | 发布文档（architecture, api-reference, mcp-tools, etc.） |
| `LakeMindModelServing/` | 统一模型服务（litellm + fastembed + SenseVoice funasr 部署文档） |
| `reports/` | 验证报告与设计文档 |
