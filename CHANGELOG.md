# Changelog

## v0.2.1-ray-fix (2026-07-24)

### Ray Job Lifecycle — 7 Bug Fixes
Root cause: platform (LakeMindServer) bugs, not application or Ray. Jobs timed out in DB but Ray processes never cancelled → permanent CPU leak.

- **Bug #4 (CRITICAL)**: `check_timeouts()` now calls `self._backend.cancel(ray_job_id)` before marking TIMED_OUT — prevents zombie Ray processes holding CPU forever
- **Bug #5**: `_mark_lost()` now calls `cancel()` before marking LOST
- **Bug #1**: `submit()` uses `entrypoint_num_cpus` / `entrypoint_memory` (correct Ray API) instead of `resources={"CPU":...}` (wrong parameter)
- **Bug #3**: Unknown Ray status maps to `"UNKNOWN"` instead of `"RUNNING"` — stops inflating RUNNING count; added `NOT_SUBMITTED`/`SUBMITTED` → `QUEUED` mappings
- **Bug #7**: New `cleanup_zombies()` method runs every sync cycle, cancels Ray processes for TIMED_OUT/LOST attempts
- **Bug #2**: `submit()` sets `working_dir` in `runtime_env` from `skill_package_uri` (was ignored)
- **Bug #6**: `scan_jobs()` actually queries Ray dashboard via `JobSubmissionClient.list_jobs()` (was dead code — empty set never populated)

### ASR — faster-whisper Deprecated
- Replaced faster-whisper with SenseVoice ONNX (iic/SenseVoiceSmall-onnx, CPU)
- Removed `faster-whisper` from `pyproject.toml` dependencies
- Removed `asr-model-init` container from `docker-compose.yml`
- `ASRRouter` only supports `sensevoice-onnx` provider; `FasterWhisperBackend` import removed
- Added PyAV (`av>=14.0.0`) for WebM/Opus audio decoding
- Fixed `<unk>` token filtering in CTC decode

### Infrastructure
- Docker daemon.json: added stable DNS (`223.5.5.5`, `223.6.6.6`, `8.8.8.8`) to fix intermittent ghcr.io DNS failures

## v0.2.0-hardening (2026-07-22)

### Hardening Summary
- 72 files changed, +1376 / -878
- pytest: 63 passed (unit) + 33 skipped (E2E, server not running)

### WP0: Version Unification + API Consolidation
- All components unified to v0.2.0 (Server, ModelServing, 3 MCP, frontend)
- Deleted old `compute/jobs.py` router, renamed `jobs_v2.py` → `jobs.py`, unified `/api/v1/jobs`
- Migration 011 drops `ray_jobs` table; removed ray_jobs CRUD from postgres.py + protocols.py
- 3 ADRs: ADR-020 (runtime facts), ADR-021 (event boundary), ADR-022 (API deprecation)

### WP1: Job Runtime Lifecycle
- `app.py` lifespan initializes RayExecutionBackend → JobService → JobSyncService
- `list_jobs` queries `job_runs` with SQL-level tenant filtering + LIMIT/OFFSET pagination
- `_write_event` on submit/queue/start/fail/cancel/retry/timeout/lost/artifact
- JobSyncLoop every 3s sync + 30s timeout check
- `_collect_result` creates job_artifacts on SUCCEEDED
- Retry restores package_uri, entry_point, secrets, model_binding from original skill
- Cancel: CANCELLING → Ray Stop → CANCELLED + event

### WP2: Outbox Loop
- OutboxLoop started in lifespan
- Default handlers registered: asset.*/knowledge.*/job.*/model.*/config.*/operation.*
- No handler → FAILED (not DONE), prefix matching

### WP3: Async Boundary
- 17 API files fixed: all sync I/O wrapped in `asyncio.to_thread`
- Files: assets, skills, secrets_v2, tenants, steward, observability, events, notifications, security, configuration, audit, operations, instances, sql, metadata, secrets, system

### WP4: Vector Index API + Memory Optimization
- LanceDB engine: `create_index`/`list_indexes`/`drop_index`
- vectors.py: 4 new index endpoints (POST/GET/refresh/DELETE)
- Memory basic.py: persistent `httpx.Client` (replaces per-call `httpx.post`)
- Memory dedup: PG `memory_hash_index` table with UNIQUE constraint (replaces full table scan)
- Memory delete: batch `tbl.delete()` for run_id filter (replaces row-by-row)

### WP5: Steward + Monitoring
- Steward.tsx: removed WebSocket, replaced with fetch POST /steward/chat
- Monitoring service: real HTTP health probes (replaces `unknown` placeholder)

### WP6: ModelServing
- chat.py: `stream=true` returns 400 `STREAMING_NOT_SUPPORTED_IN_V0_2_0`
- ASR docs corrected: SenseVoice → faster-whisper-small across 15 doc files

### WP7: E2E Tests
- 33 empty `pass` stubs replaced with real HTTP-based tests
- conftest.py: server availability detection + skip_if_no_server marker
- golden_path (14), security (6), consistency (7), recovery (6)

### P0 Fixes
- P0-08: monitoring ray_jobs → job_runs query + real health probes
- P0-09: memory zero-vector fallback removed; `_embed` now raises on failure

### Pre-existing Fixes
- Docs: 58 → 68 MCP tools
- Auth: graceful degradation to tenant_admin when LAKEMIND_V2_AUTH unset
- registry.py: AES-256-GCM encryption for api_key (`enc:` prefix)
- CI: build.yml test job runs pytest
- BFF: COOKIE_SECURE env controls `secure` flag
- test_actions.py: 32 → 36 actions

---

## v0.2.0 (2026-07-19)

### Breaking Changes
- **LakeMindSteward/ + LakeMindMonitor/ 目录已删除** — 合并迁入 `LakeMindControlCenter/`（Steward 作为内嵌组件运行于 :3002，Monitor 仪表板迁为 Mission Control 页面）
- Auth: `LAKEMIND_V2_AUTH=1` enables new RBAC middleware (v0.1.0 API Key still works when unset)
- DataMCP: 5 Ray tools replaced by JobService (`/api/v1/jobs/*`)
- `execute_skill` removed — replaced by JobService.submit(skill_ref, inputs)

### New Features

#### ControlCenter（统一管理入口）
- LakeMindControlCenter/ 目录（前端 nginx :3000 + BFF FastAPI :3001 + Steward LangGraph :3002）
- 10 页面：Overview, Assets, Jobs, ModelServing, Services, Configuration, Security, Operations, Audit, Steward
- Mission Control：11 指标卡（统一了 v0.1.0 的 Monitor 仪表板）
- 模型配置与路由管理：Definition/Deployment/Profile/Route CRUD + 部署检测（Test 按钮）
- WebSocket for real-time updates

#### 模型管理（两层架构）
- Definition（逻辑层）+ Deployment（物理层），1:N 关系
- Profile 路由：model_profiles + model_routes 表，profile→deployment 映射（含 priority/is_fallback/tenant_id）
- 部署检测：POST /models/deployments/{id}/test — 按 model_type 发探测请求
- enable/disable 同时设置 status + desired_state

#### Meeting Agent v0.2.0（全链路验证通过）
- 浏览器录音 → ASR → 转写 → 纪要 → 知识 全链路走 MCP
- 133 chunks → 31 ASR SUCCEEDED → 30 段转写 → 6 版纪要 → 7 条知识 → REVIEW_REQUIRED
- 录音分片间隔 20 秒，实时纪要/知识（每 6 chunk 触发）
- 录音回放组件（ChunkPlayer），3 栏工作台（转写|纪要|知识）
- Skill v0.2.4：ASR timeout=300s, LLM 6 次重试, litellm Router timeout=120s

#### Bug 修复（ControlCenter 数据空白）
- Bug-6: security.py capabilities 修复
- Bug-7~13: BFF tenant_id, job_service ray_jobs 查询, platform_admin 跨租户, instances 注册心跳, monitoring 指标采集, ModelServing /models/definitions

#### WP2: Control Plane & Security
- RBAC: 5 builtin roles, 26 actions, SecurityContext + middleware
- Token management: SHA-256 hashed tokens, issue/revoke/list
- Tenant isolation: S3/Lance/Iceberg/Valkey key resolution
- Protected namespace: `lake://` scheme guard
- Configuration service: schema-validated, revision-based, rollback
- Instance registry: heartbeat + Desired/Active revision tracking
- Secret management: AES-256-GCM encryption, rotation, minimal injection
- Audit service: queryable audit log with export
- Operation service: state machine (DRAFT→APPROVAL_REQUIRED→APPROVED→RUNNING→SUCCEEDED/FAILED)
- Outbox: SKIP LOCKED + exponential backoff event processing
- Docker network isolation: `internal` network

#### WP3: Asset Runtime
- Asset state machine: CREATED→INITIALIZING→READY→DEGRADED→DELETING→DELETED
- AssetService: CRUD + bindings + lineage + reindex
- KnowledgeService: ingest/search/reindex (OKF format)
- SkillService: register/validate/publish/revoke (PUBLISHED-only execution)
- MemoryService: mem0-style 8 methods (add/search/get/list/update/delete/clear/history)
- ReconciliationService: scan assets/jobs/config for drift

#### WP4: Job Runtime
- Job schema: job_runs + job_attempts + job_artifacts
- Job state machine: SUBMITTED→QUEUED→RUNNING→SUCCEEDED/FAILED/TIMED_OUT/CANCELLED/LOST
- JobService: submit/cancel/retry/get_result/get_attempts
- ExecutionBackend Protocol + RayExecutionBackend
- JobSyncService: status sync + startup recovery + timeout detection
- JobArtifactService: create/list/assetize (Artifact → Knowledge/Memory)
- Resource quota: Skill default + tenant limit + job override
- Idempotency key support

#### WP5: ModelServing Management
- 5 model tables: definitions, deployments, profiles, routes, embedding_spaces
- ModelManagementService: CRUD + resolve_profile + enable/disable + YAML import
- Secret Ref replacement (no plaintext API keys)
- Config revision tracking for model changes

#### WP7: Steward Governance
- Independent Service Identity (non-superadmin)
- 3-level action model: observe / low_risk auto / high_risk approval
- 6 inspection categories: service health, degraded assets, lost jobs, outbox, binding drift, config drift
- Policy-driven auto-action level

### Infrastructure Changes
- 容器从 13 个（v0.1.0: 含独立 steward + monitor）→ 12 平台容器（v0.2.0: control-center 统一）
- 端口 3000 从 Monitor 变为 ControlCenter
- 端口 8500（Steward）内化为 ControlCenter :3002
- 5 个自研镜像：postgres-age, server-api, mcp-suite, model-serving, control-center

### Database Migrations
- 001_initial_schema: v0.1.0 baseline (10 tables)
- 002_control_plane: 12 CP tables + seed roles/tenant
- 003_asset_core: assets/bindings/lineage/reconciler
- 004_asset_types: knowledge_meta/skill_meta/memory_meta
- 005_job_runtime: job_runs/job_attempts/job_artifacts
- 006_model_management: model_definitions/deployments/profiles/routes/embedding_spaces

### Dependencies Added
- alembic>=1.13
- sqlalchemy>=2.0
- ulid-py>=2.0

---

## v0.1.0 (2025-07-12)

### Initial Release
- MVP：13 容器、10 引擎、68 MCP 工具、Ray 分布式计算
- 3 MCP 服务：AssetMCP (23 tools) + DataMCP (24 tools) + AdminMCP (21 tools)
- LakeMindServer：REST API 网关 (40+ 路径) + 10 引擎
- LakeMindModelServing：litellm + fastembed + FunASR
- LakeMindSteward + LakeMindMonitor（v0.2.0 已合并迁入 ControlCenter）
- examples/meeting-agent + examples/lakemind-connector
- L0-L9 验证：297/297 PASS
