# LakeMind v0.2.0 四平面架构

> 日期：2026-07-13  
> 状态：accepted  
> 依据：[设计方案](../../../reports/v0.2.0-design/LakeMind_v0.2.0_设计方案.md) §4.1-§4.2

---

## 1. 四平面总表

| 平面 | 核心职责 | 调用方向 | 信任级别 |
|------|----------|----------|----------|
| Access Plane | 协议适配、请求校验、入口 | → Control Plane | 最不可信（外部输入） |
| Control Plane | 身份、安全、资产、Job、配置、治理 | → Data & Index Plane（通过 Provider） | 可信（已认证） |
| Data & Index Plane | 保存数据、索引、缓存、投影 | 不主动调用其他平面 | 可信（仅被 Control Plane 调用） |
| Execution Plane | 执行 Job、模型推理、解析 | → Data & Index Plane（受控契约）；← Control Plane（调度） | 半可信（受控代码，非控制面密钥） |

### 1.1 Access Plane

**职责**：接收外部请求（REST / MCP / Control Center BFF），解析协议，校验请求格式，将请求转换为 Control Plane 调用。

**包含组件**：
- LakeMindServer REST API 路由层（FastAPI router + 请求模型校验）
- LakeMindAssetMCP (8401) — 协议适配层
- LakeMindDataMCP (8402) — 协议适配层
- LakeMindAdminMCP (8403) — 协议适配层
- LakeMindControlCenter BFF — 前端聚合入口

**禁止事项**：
- 禁止直连 Data & Index Plane（绕过 Control Plane）
- 禁止包含业务逻辑（仅协议适配 + 请求转发）
- 禁止直连底层引擎 SDK（S3 / Lance / Ray / PG）

### 1.2 Control Plane

**职责**：身份认证、授权、资产管理、Job 管理、配置管理、治理动作。是平台的核心逻辑层。

**包含组件**：
- 12 个 Application Service（AssetService / KnowledgeService / SkillService / MemoryService / JobService / ModelManagementService / ConfigurationService / AuthorizationService / SecretService / OperationService / AuditService / ReconciliationService）
- LakeMindSteward — 受控治理 Agent
- Outbox Worker — 事件投递

**禁止事项**：
- 禁止直接暴露底层引擎细节到外部接口
- 禁止跳过 AuthorizationService 处理请求
- 禁止跳过 AuditService 记录管理操作

### 1.3 Data & Index Plane

**职责**：数据持久化、索引构建、缓存管理、投影维护。通过 Provider 抽象被 Control Plane 调用。

**包含组件**：
- PostgreSQL 16 — 统一元数据 + Iceberg SQL catalog + 图投影
- SeaweedFS — S3 兼容对象存储
- Lance / LanceDB — 向量索引
- Apache Iceberg — 表格式
- Valkey — KV 缓存
- PG Graph（graph_nodes / graph_edges）— 图投影（Experimental）

**禁止事项**：
- 禁止主动调用其他平面
- 禁止包含业务逻辑（仅数据操作）
- 禁止直接对外暴露

### 1.4 Execution Plane

**职责**：执行 Job（以 Skill 为定义的确定性任务）、模型推理、数据解析。受 Control Plane 调度，通过受控契约访问 Data & Index Plane。

**包含组件**：
- LakeMindModelServing (10824) — litellm + fastembed + SenseVoice funasr
- Ray Head + Workers — 分布式计算

**禁止事项**：
- 禁止反向调用 Control Plane
- 禁止持有控制面密钥（仅获声明 Secret 引用）
- 禁止直接对外暴露（仅被 Control Plane 调度）

---

## 2. 组件归属表

| 组件 | v0.1.0 位置 | v0.2.0 平面 | 备注 |
|------|-------------|-------------|------|
| LakeMindAssetMCP (8401) | LakeMindMCP/ | Access Plane | 23 tools → 降为协议适配层 |
| LakeMindDataMCP (8402) | LakeMindMCP/ | Access Plane | 24 tools → 受控数据访问 |
| LakeMindAdminMCP (8403) | LakeMindMCP/ | Access Plane | 21 tools → 调用 Operation Service |
| LakeMindServer REST API (10823) | LakeMindServer/ | Access Plane + Control Plane | 拆分：路由层 → Access；Service 层 → Control |
| LakeMindControlCenter | LakeMindMonitor/ 演进 | Access Plane | BFF + 前端 |
| LakeMindSteward | LakeMindSteward/ | Control Plane | 受控治理 Agent |
| LakeMindModelServing (10824) | LakeMindModelServing/ | Execution Plane | 运行执行；配置归 Control Plane |
| Ray Head + Workers | docker-compose | Execution Plane | 受控 Execution Backend |
| PostgreSQL | docker-compose | Data & Index Plane | 同时是 Control Plane 事实源 |
| SeaweedFS / S3 | docker-compose | Data & Index Plane | 对象存储 |
| Lance / LanceDB | LakeMindServer plugins | Data & Index Plane | 向量索引 |
| Iceberg | LakeMindServer plugins | Data & Index Plane | 表格式 |
| Valkey | docker-compose | Data & Index Plane | KV 缓存 |
| PG Graph (graph_nodes/edges) | LakeMindServer plugins | Data & Index Plane | 图投影（Experimental） |

---

## 3. 平面间依赖规则

```
Access Plane ──→ Control Plane（必须携带 SecurityContext）
Control Plane ──→ Data & Index Plane（通过 Provider 抽象）
Control Plane ──→ Execution Plane（通过 JobService 调度）
Execution Plane ──→ Data & Index Plane（通过受控契约：Asset Binding + Secret Ref）

禁止：Access Plane ──→ Data & Index Plane（绕过 Control Plane）
禁止：Execution Plane ──→ Control Plane（反向调用控制面）
禁止：Data & Index Plane ──→ 任何平面（不主动调用）
```

### 3.1 依赖规则详述

| 规则 | 说明 |
|------|------|
| Access → Control | 请求必须携带 SecurityContext（Token 解析后生成） |
| Control → Data | 通过 Provider 抽象调用，不直连引擎 SDK |
| Control → Execution | 通过 JobService 提交，不直连 Ray API |
| Execution → Data | 通过受控契约（Asset Binding + Secret Ref），仅能访问声明的资源 |
| 禁止 Access → Data | 外部请求不可绕过 Control Plane 直连数据层 |
| 禁止 Execution → Control | 执行层不可反向调用控制面 Service |

---

## 4. 评审标准

- [x] 四平面职责无重叠
- [x] 每个组件有且仅有一个平面归属
- [x] Trust Boundary 调用规则无矛盾（详见 [trust-boundary.md](./trust-boundary.md)）
- [x] 组件映射表覆盖 v0.1.0 全部模块（详见 [component-mapping.md](./component-mapping.md)）
- [x] 文档经全员评审通过
