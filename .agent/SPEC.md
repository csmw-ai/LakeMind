# SPEC.md — LakeMind 开发规范

> 本文件是 LakeMind 项目的工程开发规范，所有贡献者必须遵守。
> 总文件为 `AGENTS.md`，架构设计见 `.agent/DESIGN.md`，当前状态见 `.agent/STATE.md`。

---

## 1. 仓库结构规范

### 1.1 Monorepo 布局

```
LakeMind/
├── .agent/                      # 设计规范与状态文档（本目录）
│   ├── DESIGN.md                # 架构设计规范
│   ├── SPEC.md                  # 开发规范（本文件）
│   └── STATE.md                 # 项目开发进展状态
├── LakeMindServer/              # 数据平面（REST API + 10 引擎）
├── LakeMindModelServing/         # 模型平面 - 统一模型服务（litellm + fastembed + SenseVoice funasr）
├── LakeMindMCP/                 # 运行平面 - 3 MCP 编排（docker-compose + --profile all）
│   ├── LakeMindAssetMCP/        #   资产面 MCP（23 tools, 11 resources, 6 prompts）
│   ├── LakeMindDataMCP/         #   数据面 MCP（18 tools, 6 resources, 2 prompts）
│   ├── LakeMindAdminMCP/        #   管理面 MCP（17 tools, 6 resources, 2 prompts）
│   └── docker-compose.yml       #   3 MCP 统一编排
├── LakeMindSteward/             # 运行平面 - 运维 Agent
├── LakeMindMonitor/             # 运行平面 - 只读仪表板
├── LakeMindStudio/              # 开发平面 - 桌面客户端（未开始）
├── scripts/                     # 跨包验证脚本
├── docs/                        # 发布文档
├── reports/                     # 验证报告与设计文档
├── AGENTS.md                    # AI Agent 协作约定（总文件）
└── README.md                    # 项目总览
```

### 1.2 包命名规则

- 目录名：`LakeMind{Plane}`，PascalCase
- Python 包名：`lakemind_{plane}_mcp`（下划线，小写）
- Docker 容器名：`lakemind-{plane}-mcp`（连字符，小写）
- Docker 镜像名：`lakemind/{plane}-mcp:latest`

### 1.3 跨包依赖规则

| 规则 | 说明 |
|------|------|
| 运行平面 → 数据平面 | 通过 REST API（:10823），不直连内部文件 |
| 运行平面 → 运行平面 | 只通过 MCP 协议（JSON-RPC over HTTP） |
| Monitor → MCP | 只读代理，不引入额外业务逻辑 |
| Steward → MCP | 通过 MCP 客户端 SDK，持多面 Token |
| **禁止** | 跨包直连内部存储（绕过 MCP 协议或 REST API） |

---

## 2. Python 开发规范

### 2.1 版本与风格

- Python **3.12**（容器）/ ≥3.11（本地开发兼容）
- 类型标注：全部函数签名必须标注返回类型
- 数据模型：使用 Pydantic v2
- 配置：YAML + Pydantic Settings，支持 `${ENV_VAR}` 插值
- 异步：MCP 工具用 `async def`，引擎适配层用同步

### 2.2 包结构（以 AssetMCP 为例）

```
src/lakemind_asset_mcp/
├── __init__.py
├── __main__.py             # 入口：uvicorn 启动
├── server.py               # FastMCP 组装 + 中间件 + resources + prompts
├── server_client.py        # Server REST API 客户端
├── config.py               # Pydantic 配置模型
├── context.py              # contextvars（Identity / TenantContext）
├── health.py               # 健康探活
├── security/               # 认证 + 审计
└── tools/                  # MCP 工具（写操作）
    ├── _helpers.py         # @audited / require_scope 装饰器
    ├── knowledge.py        # 7 OKF tools
    ├── memory.py           # 8 mem0-style tools
    ├── skill.py            # 5 tools（无 execute_skill）
    └── ontology.py         # 3 tools
```

### 2.3 代码约定

- **不加注释**，除非逻辑非显而易见
- 标识符用英文，设计文档 / 架构注释用中文
- 不引入未在 pyproject.toml 声明的依赖
- 不引入闭源依赖（技术栈锁定全开源 Apache 2.0 / MIT / BSD）
- 日志用 structlog，敏感字段脱敏（token / password / secret / api_key / content）

### 2.4 引擎适配层规范

- 引擎在 Server 进程内运行（嵌入式），MCP 通过 REST API 调用
- 重计算提交 Ray（已实现），轻计算走嵌入式
- `engines.yaml` 配置 10 引擎插件，`engines.py` 聚合为 `Engines` 对象

---

## 3. MCP 服务规范

### 3.1 MCP 三要素

每个 MCP 必须实现全部三要素：

| 要素 | 装饰器 | 说明 |
|------|--------|------|
| Tools | `@mcp.tool()` | 操作（写/读/计算） |
| Resources | `@mcp.resource("lake://...")` | 只读浏览 |
| Prompts | `@mcp.prompt()` | 使用指南（参数化模板） |

### 3.2 FastMCP 组装模式

```python
mcp = FastMCP("LakeMindAssetMCP", stateless=True)
mcp.custom_middleware = AuthMiddleware(tokens, required_scope="asset")

@mcp.tool()
async def search_knowledge(kb: str, query: str, top_k: int = 5): ...

@mcp.resource("lake://knowledge")
async def knowledge_list(): ...

@mcp.prompt()
async def search_knowledge_guide(query: str, kb_name: str): ...
```

### 3.3 工具命名

- `search_*` — 语义检索
- `ingest_*` — 批量写入
- `register_*` — 创建实例
- `add_*` / `update_*` / `delete_*` / `clear_*` — mem0 风格记忆操作
- `list_*` — 列表查询
- `get_*` — 只读单条查询
- `query_*` / `write_*` / `sql_*` — 数据面透传
- `create_*` / `issue_*` / `revoke_*` — 管理面 CRUD

### 3.4 资源 URI 约定

**AssetMCP（11 resources）**：

| URI | 说明 |
|-----|------|
| `lake://capabilities` | 资产能力图 |
| `lake://workspace` | 工作区信息 |
| `lake://knowledge` | 知识库列表 |
| `lake://knowledge/{kb}/{concept_id}` | 知识库概念详情 |
| `lake://skills` | 技能列表 |
| `lake://skills/{name}` | 技能详情 |
| `lake://memory` | 记忆概况 |
| `lake://memory/{memory_id}` | 记忆详情 |
| `lake://ontology` | 本体列表 |
| `lake://ontology/{concept}` | 本体概念详情 |

> AssetMCP **不含** `lake://system/health`——健康属于管理/数据面。

**DataMCP（6 resources）**：`lake://system/health`, `lake://tables`, `lake://tables/{ns}/{table}`, `lake://vectors`, `lake://vectors/{table}`, `lake://graph`

**AdminMCP（6 resources）**：`lake://admin/health`, `lake://admin/tenants`, `lake://admin/users`, `lake://admin/tokens`, `lake://admin/asset-types`, `lake://admin/nodes`

### 3.5 认证与 Scope

| MCP | Required Scope | Token |
|-----|---------------|-------|
| AssetMCP | `asset` | `test-business-token` |
| DataMCP | `data` | `test-steward-token` |
| AdminMCP | `admin` | `test-steward-token` |

REST API 认证：`Bearer lakemind-internal-api-key` + `X-Tenant-Id` / `X-Agent-Id` / `X-Scopes` 头。

### 3.6 租户隔离

| 层 | 隔离方式 |
|----|----------|
| S3 | key 前缀 `{tenant_id}/` |
| Iceberg | namespace `{tenant_id}_{domain}` |
| LanceDB | 每租户独立 database |
| Valkey | key 前缀 `{tenant_id}:` |
| PostgreSQL | 行级 `tenant_id` 列（应用层过滤） |

---

## 4. Docker 规范

### 4.1 Dockerfile 约定

- Python 包：`python:3.12-slim` 基镜像
- Node 包：`node:20-alpine` 基镜像
- BuildKit 禁用：`$env:DOCKER_BUILDKIT=0`（Windows 环境兼容）
- 多阶段构建仅在有编译步骤时使用

### 4.2 docker-compose 约定

- 3 compose 组：`LakeMindServer/`（`lakemind-server`）、`LakeMindMCP/`（`lakemind-mcp`）、`LakeMindMonitor/`（`lakemind-runtime`）
- `LakeMindServer/` 创建网络，其余两组使用外部网络
- 外部网络：`lakemind-server_lakemind`（由 LakeMindServer 创建）
- LakeMindModelServing 已合并入 `lakemind-runtime` 组（由 LakeMindMonitor/docker-compose.yml 编排）
- 持久化：bind mount 到 `./data/`
- `restart: unless-stopped`
- Ray 服务用 `profiles: [ray]`

### 4.3 启动顺序

```powershell
# 1. 数据平面（含 Ray）
cd LakeMindServer; docker compose --env-file .env --profile ray up -d

# 2. 3 MCP
cd ../LakeMindMCP; docker compose --profile all up -d

# 3. 运行时服务（Steward + Monitor + ModelServing）
cd ../LakeMindMonitor; docker compose up -d
```

### 4.4 Server 更新方式

server-api Docker build 耗时较长（Ray 依赖安装），使用 `docker cp` 热更新：

```powershell
docker cp LakeMindServer/src/lakemind_server/. lakemind-server-api:/usr/local/lib/python3.12/site-packages/lakemind_server/
docker restart lakemind-server-api
```

---

## 5. 验证规范

### 5.1 验证脚本

- 脚本放 `scripts/` 目录
- 主验证脚本：`scripts/verify_full.py`（L0-L9 全分层，297/297 PASS）
- 输出格式：`PASS/FAIL` 逐项 + 最终 `Result: N passed, M failed`
- 退出码：0 = 全通过，1 = 有失败

### 5.2 验证矩阵

| 验证 | 脚本 | 范围 | 当前结果 |
|------|------|------|---------|
| **全面测试 L0-L9** | `scripts/verify_full.py` | 68 tools + 10 prompts + 23 resources + REST API + 安全 + 端到端 + 性能 | **297/297 PASS** |

### 5.3 验证流程

每次完成一个步骤后：
1. 运行该步骤的验证脚本
2. 全部 PASS 才能进入下一步
3. 验证结果记录到 `.agent/STATE.md`

---

## 6. 技术栈锁定

**除非用户明确要求，不引入替代品或闭源依赖。**

| 组件 | 选型 | PyPI 包名 |
|------|------|-----------|
| 对象存储 | SeaweedFS | — |
| 统一数据库 | PostgreSQL 16 | `psycopg2-binary` |
| 表格式 | Apache Iceberg | `pyiceberg[pyarrow,sql-postgres]` |
| 向量/多模态 | PyLance + LanceDB | `pylance`, `lancedb` |
| 缓存 | Valkey | `redis`（Redis 兼容协议） |
| 即席计算 | DuckDB | `duckdb` |
| 分布式计算 | Ray 2.41.0 | `ray[default]` |
| Embedding | fastembed | `fastembed` |
| LLM 网关 | litellm | `litellm` |
| ASR | SenseVoice (funasr) | `funasr` + `torch` CPU + `librosa` |
| MCP SDK | FastMCP | `mcp` |
| Agent 框架 | LangGraph | `langgraph` |
| Web 框架 | FastAPI（Steward）/ Express（Monitor） | — |

### 不引入

| 项 | 原因 |
|----|------|
| Apache Gravitino | 已用 PostgreSQL 替代 |
| Apache Ranger | 生产阶段引入 |
| Trino | DuckDB + Ray 替代 |
| Daft | DuckDB + Ray 替代 |
| Dragonfly | BSL 1.1 禁止 SaaS，已用 Valkey（BSD 3-Clause）替代 |
| AGE 图扩展 | 编译超时，PG 原生表替代 |

### 模型管理规范

| 规则 | 说明 |
|------|------|
| **禁止运行时动态下载** | 所有模型（ASR、Embedding、本地 LLM 等）必须在部署前预下载到持久化存储。运行时只从本地绝对路径加载。 |
| **模型缺失返回错误** | 模型文件不存在时返回 `503 Service Unavailable`，不触发任何下载。 |
| **预下载容器** | 通过独立的一次性容器（`asr-model-init`，`restart: no`）或模型 Bundle 镜像完成预下载。 |
| **持久化 volume** | 模型存储在 Docker named volume 中，容器重建后不丢失。 |
| **启动时预加载** | ModelServing 启动时预加载模型（`preload: true`），不在首个请求时触发加载。 |
| **readiness 检查** | `/health/ready` 反映模型是否实际加载完成，`/health` 仅检查进程存活。 |
| **local_only 模式** | SenseVoice funasr 从本地路径加载模型文件，运行时不访问外部模型仓库。 |

---

## 7. 文档规范

- 设计文档用中文，代码标识符用英文
- PowerShell 下读写中文文件名需设置 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`
- 不主动创建 README.md / 文档文件，除非明确要求
- 文档层次：`AGENTS.md`（总）→ `.agent/DESIGN.md` + `.agent/SPEC.md` + `.agent/STATE.md`（子）→ `docs/`（发布）
