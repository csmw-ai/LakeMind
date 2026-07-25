# 变更日志

所有 notable 变更记录在此。日期格式 YYYY-MM-DD。

## [v0.2.0] — 2026-07-19

### Breaking Changes
- **LakeMindSteward/ + LakeMindMonitor/ 目录已删除** — 合并迁入 `LakeMindControlCenter/`
- Auth: `LAKEMIND_V2_AUTH=1` enables new RBAC middleware
- DataMCP: 5 Ray tools replaced by JobService (`/api/v1/jobs/*`)
- `execute_skill` removed — replaced by JobService.submit(skill_ref, inputs)

### ControlCenter（统一管理入口）
- LakeMindControlCenter/（前端 nginx :3000 + BFF FastAPI :3001 + Steward LangGraph :3002）
- 10 页面：Overview, Assets, Jobs, ModelServing, Services, Configuration, Security, Operations, Audit, Steward
- Mission Control：11 指标卡（统一了 v0.1.0 的 Monitor 仪表板）
- 模型配置与路由管理：Definition/Deployment/Profile/Route CRUD + 部署检测
- Steward 对话（LangGraph 巡检 + LLM 对话 via ModelServing）

### 模型管理（两层架构）
- Definition（逻辑层）+ Deployment（物理层），1:N 关系
- Profile 路由：model_profiles + model_routes 表
- 部署检测：POST /models/deployments/{id}/test
- enable/disable 同时设置 status + desired_state

### Meeting Agent v0.2.0（全链路验证通过）
- 浏览器录音 → ASR → 转写 → 纪要 → 知识 全链路走 MCP
- 133 chunks → 31 ASR → 30 转写 → 6 版纪要 → 7 条知识
- 录音分片 20 秒，实时纪要/知识（每 6 chunk 触发）
- 录音回放组件（ChunkPlayer），3 栏工作台
- Skill v0.2.4：ASR timeout=300s, LLM 6 次重试

### Bug 修复（ControlCenter 数据空白 Bug-6~13）
- security.py capabilities、BFF tenant_id、job_service ray_jobs 查询
- platform_admin 跨租户、instances 注册心跳、monitoring 指标采集
- ModelServing /models/definitions

### 基础设施变更
- 容器 13（v0.1.0: 独立 steward + monitor）→ 12 平台容器（v0.2.0: control-center 统一）
- 端口 3000 从 Monitor → ControlCenter
- 端口 8500（Steward）内化为 ControlCenter :3002

### 验证结果
- ControlCenter: Jobs 5853 条, Models 5 def+8 dep+5 profile, Instances 8 个全 healthy
- Meeting Agent E2E: 全链路 PASS

---

## [v0.1.0] — 2026-07-12

### 核心

#### LakeMindServer
- REST API 网关（40+ OpenAPI 路径，11 功能域）
- 11 个 Protocol 接口定义（Plugin 架构）
- 10 个 Server 引擎插件 + ModelServing
- 引擎可插拔配置（engines.yaml）
- Bearer Token 认证 + 租户/Agent/Scope 三级上下文
- httpx 连接池（max 50 连接，10 keepalive）

#### LakeMindModelServing（统一模型服务）
- litellm Router 替代手写 GatewayLLM，多 provider 路由 + fallback
- fastembed 本地嵌入（jinaai/jina-embeddings-v2-base-zh, dim=768）
- faster-whisper 本地 ASR（faster-whisper-small, INT8 CPU）
- OpenAI 兼容 API（/v1/chat/completions, /v1/embeddings, /v1/audio/transcriptions）
- 端口 :10824，容器 lakemind-model-serving

#### Ray 分布式计算
- 自建 Ray 镜像（python:3.12-slim + ray 2.41.0 + numpy）
- RayCompute 插件：7 种分布式任务
- 3 节点集群（head + 2 workers，12 CPU）

#### 三个 MCP 服务
- LakeMindAssetMCP（:8401）：23 tools, 11 resources, 6 prompts
- LakeMindDataMCP（:8402）：24 tools, 6 resources, 2 prompts
- LakeMindAdminMCP（:8403）：21 tools, 6 resources, 2 prompts
- `execute_skill` 已移除（平台只存取不执行）

#### 认知资产
- mem0 风格记忆引擎：8 方法，LLM 事实抽取 + 哈希去重
- OKF 知识格式：YAML frontmatter + markdown body + PG 图交叉链接

#### 运行平面（v0.2.0 已合并迁入 ControlCenter）
- LakeMindSteward（:8500）：LangGraph 巡检工作流 + ModelServing LLM 对话
- LakeMindMonitor（:3000）：Express + 静态 HTML，14 API 路由

### 新增 — Examples

#### examples/meeting-agent/
- 浏览器实时会议知识化 Agent Demo
- 四层架构：Web → Agent → Skill → Job (Ray)

#### examples/lakemind-connector/
- opencode AI Agent 通过 Skill 接入 LakeMind 的统一连接器
- `LakeMindConnector`：MCP + REST + Ray Jobs + ASR 统一封装

### 验证结果

| 套件 | 结果 |
|------|------|
| verify_full.py L0-L8 | 286/286 PASS |
| **合计** | **286/286 PASS** |

### 运行容器

v0.1.0: 13 个容器（含独立 steward + monitor）
v0.2.0: 12 平台容器（control-center 统一）+ meeting-agent

### 已知限制

- 动态 Token 不跨 MCP 共享（MVP 使用静态 config.yaml Token）
- LakeMindStudio 未开发（Tauri 桌面客户端）
- 3 份 server_client.py 重复（待提取共享包）
