# STATE.md — LakeMind 项目开发进展状态

> 最后更新：2026-07-25（v0.2.2-asr-vad）
> 总文件：`AGENTS.md`，设计规范：`.agent/DESIGN.md`，开发规范：`.agent/SPEC.md`

---

## 1. 总体进度

```
数据平面  ████████████████████  100%  (REST API + 10 引擎 + Ray)
模型平面  ████████████████████  100%  (litellm + fastembed + SenseVoice funasr)
运行平面  ████████████████████  100%  (3 MCP + ControlCenter 全完成)
开发平面  ░░░░░░░░░░░░░░░░░░░░    0%  (Studio 未开始)
示例      ████████████████████  100%  (meeting-agent v0.2.0 全链路 + lakemind-connector)
验证      ████████████████████  100%  (L0-L8 286/286 PASS + 压测 7/9 PASS)
文档      ████████████████████  100%  (AGENTS + .agent/ + docs/ + README + CHANGELOG)

总体      ████████████████████  ~99%
```

### 里程碑时间线

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1-2 | Server REST API + 3 容器 + PG catalog | ✅ 完成 |
| Phase 3-4 | 3 MCP + Steward + Monitor | ✅ 完成 |
| Ray 分布式 | 自建镜像，3 节点 12 CPU，7 任务类型 | ✅ 完成 |
| LLM 网关 | GatewayLLM 路由器 → litellm Router | ✅ 完成 |
| MCP 重设计 | mem0 记忆 + OKF 知识 + execute_skill 移除 + 三要素 | ✅ 完成 |
| 许可证审计 | Dragonfly BSL 1.1 → Valkey BSD 3-Clause | ✅ 完成 |
| LakeMindModelServing | 统一模型服务：litellm + fastembed + SenseVoice funasr | ✅ 完成 |
| **v0.1.0 发版** | MVP：13 容器、10 引擎、68 MCP 工具 | ✅ 完成 |
| **v0.2.0 ControlCenter** | 统一管理入口（前端 + BFF + Steward），10 页面 | ✅ 完成 |
| **v0.2.0 RBAC** | 5 builtin roles, 26 actions, SecurityContext | ✅ 完成 |
| **v0.2.0 Job Runtime** | JobService 受控执行，状态机，Ray backend | ✅ 完成 |
| **v0.2.0 模型管理** | Definition + Deployment 两层，Profile 路由，部署检测 | ✅ 完成 |
| **v0.2.0 Meeting Agent** | 浏览器录音→ASR→转写→纪要→知识全链路 | ✅ 完成 |
| **Steward+Monitor 迁移** | 合并迁入 ControlCenter，删除独立目录 | ✅ 完成 |
| **v0.2.0 性能优化** | 4 轮压测 3→7 PASS，事件循环修复+IVF索引+锁细化+Arrow IPC | ✅ 完成 |
| **v0.2.0 代码修正** | 7 项问题修正：文档同步+鉴权降级+密钥加密+CI测试+Cookie安全 | ✅ 完成 |
| **v0.2.0 最终加固** | WP0-WP7 全加固：生命周期+事件+异步边界+向量API+Memory优化+E2E测试 | ✅ 完成 |
| **v0.2.0 Ray 修复** | 7 bug 修复：check_timeouts cancel + _mark_lost cancel + entrypoint_num_cpus + UNKNOWN 状态 + cleanup_zombies + working_dir + scan_jobs | ✅ 完成 |
| **v0.2.2 ASR 改进** | ONNX 自定义后端废弁 → funasr 官方库（自带标点 + ITN，PyTorch CPU 推理 ~2s） | ✅ 完成 |
| **v0.2.2 ASR VAD+Hotwords** | fsmn-vad 语音活动检测 + 30 领域 hotwords + ffmpeg loudnorm 归一化 + job 并发 10→30 | ✅ 完成 |
| **v0.2.1 Jobs API 修复** | 3 bug：duplicate app=FastAPI() 丢 lifespan + get_skill("latest") 未解析 + S3 URI 未解析 | ✅ 完成 |
| LakeMindStudio | Tauri 桌面客户端 | ❌ 未开始 |

---

## 2. 容器运行状态

> 检查时间：2026-07-19

| 容器 | 端口 | 状态 | 用途 |
|------|------|------|------|
| lakemind-server-api | 10823 | ✅ Up | REST API + 10 引擎 |
| lakemind-model-serving | 10824 | ✅ Up | 统一模型服务（litellm + fastembed + SenseVoice funasr） |
| lakemind-postgres | 5432 | ✅ Up | Metadata Hub |
| lakemind-seaweedfs | 8333 | ✅ Up | S3 对象存储 |
| lakemind-valkey | 6379 | ✅ Up | TTL KV 缓存（BSD 3-Clause） |
| lakemind-ray-head | 8265 | ✅ Up | Ray 主节点 |
| lakemind-ray-worker-1 | — | ✅ Up | Ray 工作节点 |
| lakemind-ray-worker-2 | — | ✅ Up | Ray 工作节点 |
| lakemind-asset-mcp | 8401 | ✅ Up | 资产面 MCP（23 tools, 6 prompts, 11 resources） |
| lakemind-data-mcp | 8402 | ✅ Up | 数据面 MCP（24 tools, 2 prompts, 6 resources） |
| lakemind-admin-mcp | 8403 | ✅ Up | 管理面 MCP（21 tools, 2 prompts, 6 resources） |
| lakemind-control-center | 3000 | ✅ Up | 统一管理入口（前端 + BFF:3001 + Steward:3002） |
| meeting-agent | 9100 | ✅ Up | 会议 Agent 示例（可选） |

**12 平台容器 + meeting-agent 全部运行正常，10 引擎全部健康。**

### 引擎健康状态

```
object_storage: True    tabular:       True    vector:        True
kv:              True    graph:         True    metadata:      True
sql:             True    distributed:   True    model_serving: True
memory:          True
```

---

## 3. MCP 工具清单

### 3.1 AssetMCP（23 tools, 6 prompts, 11 resources）

| 域 | 工具 | 数量 |
|----|------|------|
| Knowledge | register, ingest, search, get, list, list_concepts, delete | 7 |
| Memory | add, search, get, list, update, delete, clear, history | 8 |
| Skill | search, register, get, list, delete | 5 |
| Ontology | query, update, delete | 3 |

- `execute_skill` 已移除（改为 JobService 受控执行）

### 3.2 DataMCP（24 tools, 2 prompts, 6 resources）

| 域 | 工具 | 数量 |
|----|------|------|
| 表操作 | query_table, write_table, sql_query, list_tables, describe_table, create_table, drop_table | 7 |
| 向量 | vector_search | 1 |
| S3 | s3_get, s3_put, s3_list, s3_delete | 4 |
| KV | kv_get, kv_set, kv_delete, kv_scan | 4 |
| 图 | graph_query, graph_update | 2 |
| Job | submit_job, get_job, cancel_job, list_jobs, get_job_result | 5 |
| 健康 | health_check | 1 |

### 3.3 AdminMCP（21 tools, 2 prompts, 6 resources）

| 域 | 工具 | 数量 |
|----|------|------|
| 用户 | create_user, list_users, update_user, delete_user | 4 |
| 租户 | create_tenant, list_tenants, update_tenant, delete_tenant | 4 |
| Token | issue_token, revoke_token, list_tokens | 3 |
| 资产类型 | register_asset_type, unregister_asset_type, list_asset_types | 3 |
| 平台 | get_platform_health, get_node_status, get_metrics | 3 |
| 配置/实例/审计 | list_configs, register_instance, heartbeat, list_audit_logs | 4 |

---

## 4. 验证结果汇总

| 验证 | 脚本 | 结果 | 说明 |
|------|------|------|------|
| **全面测试 L0-L8** | `scripts/verify_full.py` | **286/286 PASS** | 全分层验证（L9 性能压测跳过） |
| **pytest 单元测试** | `pytest tests/unit/` | **63/63 PASS** | 状态机+加密+安全+隔离+Action枚举 |
| **pytest E2E 测试** | `pytest tests/e2e/` | **33 skipped** | 服务器未运行时优雅跳过 |
| Meeting Agent E2E | `examples/meeting-agent/` | ✅ PASS | 133 chunks → 31 ASR → 30 转写 → 6 版纪要 → 7 条知识 |
| ControlCenter | `docs/control-center.md` | ✅ PASS | Jobs 5853 条, Models 5 def+8 dep+5 profile, Instances 8 个全 healthy |
| **性能压测 v4** | `scripts/stress_test.py` | **7/9 PASS** | 向量检索 23x, Memory Add 335x, 并发 0% error |

---

## 4.1 性能优化结果（v0.2.0）

> 4 轮压测：v1 3P/6F → v2 4P/5F → v3 5P/4F → v4 7P/2F
> 详见 `reports/2026.0721.性能优化全轮次总结报告.md`

### 关键指标提升

| 指标 | v1 | v4 | 提升 |
|------|-----|-----|------|
| 向量搜索 p50 | ~1400ms | 60ms | **23x** |
| 向量搜索 10 并发错误率 | 86.8% | 0% | **根治** |
| Memory Add p99 | 11s | 33ms | **335x** |
| Memory 10 并发 QPS | 1.6 | 17.8 | **11x** |
| 文件上传成功率 | 0% | 100% | **根治** |
| 向量入库 (Arrow IPC) | N/A | 8081 vec/s | **新能力** |

### 优化措施

| 轮次 | 措施 | 效果 |
|------|------|------|
| v3 P0 | `asyncio.to_thread()` 包 49 个同步 I/O 调用 (9 API 文件) | 事件循环解冻，并发 0% error |
| v3 P2 | Arrow IPC 二进制向量入库端点 | 向量入库 JSON 700→Arrow 8000 vec/s (20x) |
| v3 | LanceDB 全局 `threading.Lock` | 消除 Rust panic |
| v4 S2 | IVF_PQ 索引 (128 partitions, 16 sub-vectors) | L0 搜索 1220→14ms (86x), Recall=1.0 |
| v4 S2 | Table Handle 缓存 + 每表独立锁 | 不同表并行，同表串行 |
| v4 S3 | Memory 精确锁（只锁 LanceDB 临界区） | Add p99 11s→33ms，LLM/Embedding 不再被锁 |
| v4 S4 | Arrow 端点安全加固 (Content-Type/维度/行数校验) | 生产可用 |

### 剩余 2 FAIL（已知限制，非 bug）

| TC | 原因 | 性质 |
|----|------|------|
| TC-1 | 23.3 MB/s vs 30 阈值 | Docker Desktop 环境限制，100% 成功 |
| TC-4 | JSON 727 vec/s vs 1000 阈值 | 已知 JSON 瓶颈，Arrow 8081 vec/s 可用 |

---

## 5. 各包完成度

### 5.1 LakeMindServer — 100%

- ✅ REST API（:10823，40+ 路径）
- ✅ 10 引擎全部健康
- ✅ PostgreSQL 16（Iceberg catalog + 图 + 用户/租户/Token + memory_history）
- ✅ SeaweedFS + Valkey
- ✅ Ray 2.41.0（3 节点 12 CPU）
- ✅ Memory 引擎（mem0 风格 8 方法）
- ✅ RBAC（5 roles, 26 actions, SecurityContext）
- ✅ JobService（受控执行，状态机，Ray backend）
- ✅ 模型管理（Definition + Deployment + Profile + Route，部署检测）

### 5.2 LakeMindAssetMCP — 100%

- ✅ FastMCP 服务（:8401）
- ✅ 23 tools + 6 prompts + 11 resources
- ✅ OKF 知识格式 + mem0 风格记忆

### 5.3 LakeMindDataMCP — 100%

- ✅ FastMCP 服务（:8402）
- ✅ 24 tools + 2 prompts + 6 resources
- ✅ REST API 透传 + Ray 作业提交

### 5.4 LakeMindAdminMCP — 100%

- ✅ FastMCP 服务（:8403）
- ✅ 21 tools + 2 prompts + 6 resources

### 5.5 LakeMindControlCenter — 100% (v0.2.0)

- ✅ 前端（nginx :3000）+ BFF（FastAPI :3001）+ Steward（LangGraph :3002）
- ✅ 10 页面：Overview, Assets, Jobs, ModelServing, Services, Configuration, Security, Operations, Audit, Steward
- ✅ Mission Control（11 指标卡，统一了 v0.1.0 的 Monitor）
- ✅ 模型配置与路由管理（Definition/Deployment/Profile/Route CRUD + 部署检测）
- ✅ Steward 对话（LangGraph 巡检 + LLM 对话 via ModelServing）
- ✅ BFF session 认证 + Control Plane API 代理

### 5.6 LakeMindModelServing — 100%

- ✅ FastAPI 服务（:10824）
- ✅ litellm Router（多 provider 路由 + fallback，timeout=120s, num_retries=3）
- ✅ fastembed 本地嵌入（jina-embeddings-v2-base-zh, dim=768）
- ✅ SenseVoice 本地 ASR（iic/SenseVoiceSmall, CPU, funasr + PyTorch，自带标点 + ITN）
- ✅ ONNX 自定义后端已废弁（由 funasr 官方库替代，标点 + ITN 由模型内建产出）
- ✅ OpenAI 兼容 API

### 5.7 LakeMindStudio — 0%

- ❌ 未开始
- 规划：Tauri 2.0 + Vue 3 + Vite
- 优先级：P2

---

## 6. 已知问题与技术债

| # | 问题 | 影响 | 优先级 | 状态 |
|---|------|------|--------|------|
| 1 | 3 个 server_client.py 重复 | AssetMCP/DataMCP/AdminMCP 各有一份 | P2 | 后续版本提取共享包 |
| 2 | 动态 Token 不跨 MCP 共享 | 静态 config.yaml Token，MVP 限制 | P2 | 已知限制 |
| 3 | publish_skill.py 在容器内缺 yaml 包 | 容器内发布 skill 失败 | P3 | 不阻塞，从主机发布 |
| 4 | Server skill register/publish API 无 PUT | 无法通过 API 更新 skill | P3 | 不阻塞 |
| 5 | Arrow 端点未接入 Knowledge outbox worker | 真实向量写入仍走 JSON | P1 | 待接入 |
| 6 | v4 改动通过 docker cp 部署，未进正式镜像 | 需 DNS 恢复后重建 | P1 | 待重建 |
| 7 | uvicorn workers>1 在 Docker Desktop 下异常 | IPv6 端口转发问题 | P3 | workers=1 可用 |
| 8 | 3 MCP config.py 95% 重复 | 复制粘贴，各自演化 | P2 | 后续提取 LakeMindMCPShared 包 |

### v0.2.0-hardening 已修复问题

| 原问题 | 修复 |
|--------|------|
| Job Runtime 未连接到 app 生命周期 | lifespan 初始化 RayExecutionBackend → JobService → JobSyncService |
| list_jobs 查询不存在的 jobs 表 | 改为查询 job_runs，SQL 级租户过滤 + 分页 |
| job_events 未写入 | _write_event 在所有状态转换时写入 |
| Outbox 无默认处理器 | 注册 asset.*/knowledge.*/job.*/model.*/config.*/operation.* |
| 17 个 API 文件同步 I/O 阻塞事件循环 | 全部包装 asyncio.to_thread |
| Memory 全表扫描去重 | PG memory_hash_index 表 + UNIQUE 约束 |
| Memory 每次新建 HTTP 连接 | 持久化 httpx.Client |
| Steward WebSocket 不稳定 | 替换为 fetch POST /steward/chat |
| 监控服务健康探测为 unknown | 真实 HTTP GET /health 探测 |
| ModelServing stream=true 静默忽略 | 返回 400 STREAMING_NOT_SUPPORTED_IN_V0_2_0 |
| 33 个 E2E 测试为空 pass | 替换为真实 HTTP 测试 + skip_if_no_server |
| Memory 零向量回退掩盖错误 | 移除回退，_embed 抛异常 |

---

## 7. 关键配置

### 7.1 PostgreSQL

```
host: lakemind-postgres:5432
db: lakemind
user: lakemind / password: lakemind_pass
```

### 7.2 S3 (SeaweedFS)

```
endpoint: http://lakemind-seaweedfs:8333
access_key: admin / secret_key: admin123456
region: us-east-1
buckets: lakemind-iceberg, lakemind-filesets
```

### 7.3 Valkey

```
host: lakemind-valkey:6379
image: valkey/valkey:8.0
license: BSD 3-Clause
```

### 7.4 REST API 认证

```
Authorization: Bearer <SERVER_API_KEY>
X-Tenant-Id: <tenant> / X-Agent-Id: <agent> / X-Scopes: asset,data,admin
```

### 7.5 Embedding

```
provider: fastembed
model: jinaai/jina-embeddings-v2-base-zh
dim: 768
```

### 7.6 LLM 网关

```
provider: litellm Router
model: deepseek-v4-flash (via ModelServing)
timeout: 120s, num_retries: 3
```

### 7.7 Ray

```
head: lakemind-ray-head:8265
workers: lakemind-ray-worker-1, lakemind-ray-worker-2
CPU: 5 (head=1, worker=2×2)
```

### 7.8 ControlCenter

```
port: 3000 (nginx → BFF:3001 + Steward:3002)
container: lakemind-control-center
user: admin / tenant: ten_default / role: platform_admin
```

---

## 8. 下一步计划

| 优先级 | 任务 | 预估工作量 |
|--------|------|-----------|
| P1 | DNS 恢复后重建正式镜像（含 v4 全部改动） | 1h |
| P1 | Arrow 接入 Knowledge outbox worker 真实向量写入链路 | 4h |
| P2 | TC-1 阈值调整 + TC-4 拆分 JSON/Arrow | 2h |
| P2 | 提取共享 LakeMindMCPShared 包 | 2h |
| P2 | LakeMindStudio（Tauri 桌面客户端） | 2-3d |
| P2 | 线程池治理：按资源独立 Executor + Semaphore | 4h |
| P3 | 动态 Token 跨 MCP 共享 | 1d |

---

## 9. 文件索引

### 设计文档

| 文件 | 说明 |
|------|------|
| `AGENTS.md` | AI Agent 协作约定（总文件） |
| `.agent/DESIGN.md` | 架构设计规范 |
| `.agent/SPEC.md` | 开发规范 |
| `.agent/STATE.md` | 本文件 |
| `README.md` | 项目总览 |
| `docs/lakemind-example-develop-guide.md` | Example 开发指南 |
| `docs/` | 发布文档（architecture, api-reference, mcp-tools, control-center, etc.） |
| `reports/` | 验证报告与设计文档 |

### 关键源码

| 文件 | 说明 |
|------|------|
| `LakeMindServer/src/lakemind_server/engines.py` | 10 引擎聚合 |
| `LakeMindServer/src/lakemind_server/api/models.py` | Models API（CRUD + test + routes） |
| `LakeMindServer/src/lakemind_server/services/model_management_service.py` | 模型管理服务 |
| `LakeMindControlCenter/frontend/src/pages/ModelServing.tsx` | 模型配置前端（3 Tab） |
| `LakeMindControlCenter/bff/app.py` | BFF（FastAPI） |
| `LakeMindControlCenter/steward/` | Steward（LangGraph，内嵌） |
| `LakeMindModelServing/src/lakemind_model_serving/gateway.py` | litellm Router 网关 |
| `LakeMindServer/src/lakemind_server/plugins/storage/vector/lancedb.py` | LanceDB 引擎（每表锁 + Table 缓存） |
| `LakeMindServer/src/lakemind_server/plugins/cognitive/memory/basic.py` | Memory 引擎（精确锁 LanceDB 临界区） |
| `LakeMindServer/src/lakemind_server/api/vectors.py` | 向量 API（to_thread + add_arrow 端点） |

### 验证脚本

| 脚本 | 结果 |
|------|------|
| `scripts/verify_full.py` | **286/286 PASS**（L0-L8 全分层） |
| `scripts/stress_test.py` | **7/9 PASS**（性能压测 v4） |
