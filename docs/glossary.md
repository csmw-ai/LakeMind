# 核心概念与术语表

> 帮助新人快速理解 LakeMind 的关键概念。

---

## 一句话定位

**LakeMind 是 Agent 时代的数据操作系统**——就像 Kubernetes 是容器时代的操作系统一样。

Agent 通过 MCP 协议声明"我需要什么"，LakeMind 负责路由到正确的引擎、正确的租户空间、正确的权限边界。

---

## 核心概念

### Agent 原生（Agent-Native）

LakeMind 从第一天起就是为 Agent 设计的，不是"给人用的系统加了个 API"。

- Agent 通过 **MCP 协议**连接，不写 SQL、不调 SDK。
- 所有数据访问是**声明式**的：声明"我需要一个知识库"，而非"创建一个 LanceDB table，设置 cosine metric，插入向量…"。
- 平台**只存取不执行**：Agent 检索到技能代码后在自己的运行时执行，LakeMind 不越界。

### 认知资产（Cognitive Asset）

Agent 运行中产生和消费的语义数据，分为 4 类：

| 资产类型 | URI | 存储 | 说明 |
|----------|-----|------|------|
| **知识** | `lake://knowledge` | Lance 向量 + PG 图 | OKF 格式（YAML frontmatter + markdown body），语义检索 |
| **记忆** | `lake://memory` | Valkey (短期) + Lance (长期) | mem0 风格，LLM 事实抽取 + 哈希去重 |
| **技能** | `lake://skills` | S3 + PG + LanceDB | 可检索的代码包，平台不执行 |
| **本体** | `lake://ontology` | PG graph_nodes/edges | 实体关系图，JSONB 属性 |

### 三平面架构

| 平面 | 职责 | 包 |
|------|------|-----|
| **数据平面** | 存储与计算底座 | LakeMindServer + LakeMindModelServing |
| **运行平面** | MCP 编排 + 管理入口 | LakeMindMCP + LakeMindControlCenter |
| **开发平面** | 资产设计、调试、脚手架 | LakeMindStudio（待开发） |

### MCP（Model Context Protocol）

Agent 与 LakeMind 交互的唯一协议。每个 MCP 服务提供三要素：

- **Tools**：可执行操作（如 `ingest_knowledge`、`search_memory`）
- **Resources**：只读浏览（如 `lake://knowledge/my_kb`）
- **Prompts**：使用指南（如"如何摄入知识"）

三个 MCP 服务：

| MCP | 端口 | 面向 | 工具数 |
|-----|------|------|--------|
| AssetMCP | 8401 | 业务 Agent | 23 |
| DataMCP | 8402 | Steward / 高级 Agent | 24 |
| AdminMCP | 8403 | Steward | 21 |

### 统一存储底座

所有数据文件都存在 **SeaweedFS** 一个对象存储中。Agent 不需要关心数据存在哪种引擎里：

- Iceberg 表文件 → S3
- Lance 向量文件 → S3
- Skill 代码包 → S3
- 记忆向量 → S3

### 统一元数据

所有结构化元数据都存在 **PostgreSQL** 一个数据库中：

- Iceberg catalog
- 用户 / 租户 / Token
- 资产定义
- 图节点 / 边
- 模型注册表

### 引擎可插拔

所有引擎通过 `engines.yaml` 配置切换，不改代码：

```yaml
compute:
  distributed:
    plugin: ray          # embedded | ray
cognitive:
  memory:
    plugin: basic        # basic | (future: mem0)
```

### 租户隔离

| 层 | 隔离方式 |
|----|----------|
| S3 | key 前缀 `{tenant_id}/` |
| Iceberg | namespace `{tenant_id}_{domain}` |
| LanceDB | 每租户独立 database |
| Valkey | key 前缀 `{tenant_id}:` |
| PostgreSQL | 行级 `tenant_id` 列 |

### Ray 分布式计算

Ray 2.41 集群（3 节点 12 CPU），Agent 通过 MCP 提交分布式作业：

- 批量 embedding
- 并行检索
- 大规模数据处理
- Skill 代码包作为 Ray job 运行

### ControlCenter

统一管理入口（前端 nginx :3000 + BFF FastAPI :3001 + Steward LangGraph :3002），10 页面：
Overview, Assets, Jobs, ModelServing, Services, Configuration, Security, Operations, Audit, Steward。
Mission Control 页面统一了 v0.1.0 的 Monitor 仪表板。

### Steward

管理运维 Agent（LangGraph 巡检工作流 + 对话式管理），走 AdminMCP + DataMCP。v0.2.0 内嵌于 ControlCenter（:3002）。

---

## 术语速查

| 术语 | 含义 |
|------|------|
| **OKF** | Open Knowledge Format，YAML frontmatter + markdown body |
| **mem0** | 记忆引擎风格，8 方法（add/search/get/list/update/delete/clear/history） |
| **MCP** | Model Context Protocol，Agent 与平台交互协议 |
| **Asset** | 认知资产（知识/记忆/技能/本体） |
| **ControlCenter** | 统一管理入口（前端 + BFF + Steward） |
| **Steward** | 管理运维 Agent（内嵌于 ControlCenter） |
| **Tenant** | 租户，数据隔离单元 |
| **Scope** | Token 权限范围（asset/data/admin） |
| **engines.yaml** | 引擎配置文件，切换插件不改代码 |
| **LanceDB** | 向量数据库，基于 Lance 列存格式 |
| **Iceberg** | Apache Iceberg 表格式，结构化数据 |
| **Valkey** | Redis 兼容的 KV 缓存（BSD 3-Clause） |
| **fastembed** | 本地嵌入库，ONNX 推理 |
| **litellm** | LLM 网关，多 provider 路由 |
| **SenseVoice (funasr)** | 本地语音识别（iic/SenseVoiceSmall, CPU, funasr + PyTorch，自带标点 + ITN） |
