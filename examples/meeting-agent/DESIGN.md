# 会议实时知识化 Agent — 设计方案

> 位置：`examples/meeting-agent/`
> 状态：已实现并验证（17 分钟实时测试，145 chunks，100+ Ray jobs，100% 成功）
> 日期：2026-07-12

---

## 1. 项目定位

**LakeMind 平台能力验证 Demo**。浏览器实时录音，Agent 编排流水线，通过 Ray job 执行 ASR/摘要/萃取，验证 LakeMind 的存储、Ray 分布式计算、Skill 管理、ASR、LLM、Embedding、向量检索、记忆等核心能力。

> **不是生产级应用**。省略了认证、持久化、并发控制、错误重试等生产必需能力。

---

## 2. 架构

```
┌─────────────────────────────────────────────────────────┐
│                    浏览器 (Web UI)                        │
│  MediaRecorder per-chunk restart (10s/chunk)             │
│  POST /api/chunk (WebM binary) + SSE 消费                │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              Agent (FastAPI :9100)                        │
│                                                           │
│  职责：输入归一化 + job 编排 + 结果分发                    │
│    chunk → ffmpeg WAV → MCP s3_put → MCP ray_submit_job   │
│         → poll → MCP s3_get → SSE 推送                     │
│    每6chunk → MCP submit Ray job(summarize) → poll        │
│    每2纪要 → MCP submit Ray job(extract) → poll           │
│           → retrieval self-check → SSE 推送               │
│                                                           │
│  通过 MCP 访问平台，不直连 Server REST API                │
│  不直接调用 ModelServing（ASR/LLM/embed 全在 Ray job 内）  │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  DataMCP (:8402)              AssetMCP (:8401)           │
│  s3_put / s3_get / s3_list    search_knowledge           │
│  ray_submit_job / ray_status  add_memory                 │
│  create_table / write_table  search_memory               │
│  query_table / list_tables                                │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              LakeMind Server (:10823)                     │
│  /api/v1/compute/jobs/submit → Ray 集群                   │
│  /api/v1/storage/objects → S3 (SeaweedFS)                │
│  /api/v1/storage/vectors → LanceDB                        │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              Ray Cluster (3 nodes, 12 CPU)               │
│                                                           │
│  jobs/asr/main.py:     WAV → ModelServing ASR → S3       │
│  jobs/summarize/main.py: transcript → LLM → S3           │
│  jobs/extract/main.py: minutes → LLM → embed → 入库 → S3 │
│                                                           │
│  共享: lakemind_utils.py (S3/LLM/ASR/embed/ingest)       │
│  依赖: httpx (在 ray.yaml dependencies 中声明)            │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 层次划分

| 层 | 位置 | 职责 | 复用性 |
|----|------|------|--------|
| **Web** | `static/` | 录音 UI + SSE 消费 | 仅本 demo |
| **Agent** | `agent.py` + `lakemind_client.py` | 通过 MCP 编排 Ray job + S3 + 知识/记忆 + SSE 分发 | demo 专属 |
| **Skill** | `skills/meeting-processing/` | 可复用业务逻辑包 | 可被其他 Agent 复用 |
| **Job** | `skills/.../jobs/{name}/main.py` | 最小执行单元 | 可独立提交到任何 Ray 集群 |

### 关键原则

- **Agent 通过 MCP 访问平台** — S3/Ray/表走 DataMCP(:8402)，知识/记忆走 AssetMCP(:8401)，不直连 Server REST API
- **Agent 不直接调用 ModelServing** — ASR/LLM/embed 全部在 Ray job 内执行
- **Agent 只做编排** — 通过 MCP 提交 job、轮询状态、读写 S3、SSE 推送
- **Job 是自包含的** — 每个 `main.py` 通过 `lakemind_utils.py` 直连 ModelServing/Server，不依赖 Agent
- **Skill 可复用** — 其他 Agent 可通过 `ray_submit_job("lake://skills/meeting-processing", "asr", ...)` 提交相同的 job
- **向量入库用 `/add`** — 追加到已有表，不覆盖；仅首次创建时用 `mode:overwrite`

---

## 4. 数据流

### 4.1 ASR

```
Agent                          Server                    Ray Worker
  │                               │                          │
  ├─ ffmpeg WebM → WAV            │                          │
  ├─ S3 PUT chunk.wav ──────────→ │                          │
  ├─ POST /jobs/submit ─────────→ │                          │
  │   {skill_uri, job=asr,        │                          │
  │    params={chunk_uri,         │                          │
  │            result_uri}}       │                          │
  │                               ├─ fetch skill zip from S3 │
  │                               ├─ parse ray.yaml          │
  │                               ├─ inject RAY_JOB_PARAMS   │
  │                               ├─ submit to Ray ────────→ │
  │                               │                          ├─ download WAV from S3
  │                               │                          ├─ POST ModelServing ASR
  │                               │                          ├─ S3 PUT result.json
  │                               │                          ├─ (job SUCCEEDED)
  │ ← poll status ────────────── │ ← get_job_status ────── │
  ├─ S3 GET result.json ────────→│                          │
  ├─ clean_asr_text()             │                          │
  └─ SSE broadcast transcript     │                          │
```

### 4.2 Summarize

```
Agent → S3 PUT transcript.json → submit job(summarize)
  → Ray Worker: download transcript → LLM chat → S3 PUT minutes.md + result.json
  → Agent: poll → S3 GET result → SSE broadcast minutes
```

### 4.3 Extract

```
Agent → S3 PUT minutes.md → submit job(extract)
  → Ray Worker: download minutes → LLM extract concepts (JSON)
    → for each concept: embed(title+body) → vector
    → POST /vectors/{db}/{table}/add (追加，不覆盖)
    → S3 PUT result.json
  → Agent: poll → S3 GET result → retrieval self-check → SSE broadcast knowledge
```

---

## 5. Skill 包结构

```
meeting-processing/
├── SKILL.md                    ← Skill 声明（jobs 列表 + 模型服务说明）
├── lakemind_utils.py           ← 共享工具
│   ├── download_from_s3()
│   ├── upload_to_s3()
│   ├── llm_chat()
│   ├── asr()
│   ├── embed()
│   └── ingest_knowledge()      ← 使用 /add 端点追加，不覆盖
└── jobs/
    ├── asr/
    │   ├── ray.yaml            ← entrypoint + dependencies
    │   ├── requirements.txt
    │   └── main.py             ← ASR job entrypoint
    ├── summarize/
    │   ├── ray.yaml
    │   ├── requirements.txt
    │   └── main.py             ← 摘要 job entrypoint
    └── extract/
        ├── ray.yaml
        ├── requirements.txt
        └── main.py             ← 萃取 job entrypoint
```

### ray.yaml 格式

```yaml
entrypoint: "python jobs/asr/main.py"   # 相对于 skill root
dependencies:                             # pip 依赖，Ray worker 安装
  - httpx
resources:
  num_cpus: 1                            # Ray 资源声明
```

### RAY_JOB_PARAMS

Server 将 `submit` 请求中的 `params` 字段序列化为 `RAY_JOB_PARAMS` 环境变量注入到 Ray job。Job 代码通过 `json.loads(os.environ["RAY_JOB_PARAMS"])` 读取参数。

### 环境变量注入

Ray job 运行时获得的环境变量来源（优先级递增）：

1. Server 容器的 `os.environ`（含 `SERVER_API_KEY`、`MODEL_SERVING_URL` 等）
2. 租户密钥（PG `tenant_secrets` 表，AES-256-GCM 解密）
3. `env_overrides`（请求中显式指定）
4. `RAY_JOB_PARAMS`（`params` 字段序列化）

### 向量入库策略

`ingest_knowledge` 函数使用两步策略：

1. **先尝试 `POST /{db}/{table}/add`** — 追加数据到已有表
2. **若 404（表不存在）** → `POST /{db}` with `mode:overwrite` — 创建表并写入初始数据

这确保每次萃取的知识**追加**到向量表，而非覆盖之前的数据。

---

## 6. S3 路径约定

```
s3://lakemind-filesets/{tenant}/meetings/{meeting_id}/
  ├── audio/
  │   ├── chunk-001.wav          ← Agent 上传的 WAV 音频
  │   ├── chunk-002.wav
  │   └── ...
  ├── transcript.json              ← Agent 上传的转写文本
  ├── minutes.md                   ← Summarize job 输出的纪要
  └── results/
      ├── asr-001.json             ← ASR job 结果 {text, segments}
      ├── asr-002.json
      ├── summarize-001.json       ← Summarize job 结果 {minutes, minutes_uri}
      └── extract-001.json         ← Extract job 结果 {concepts}
```

---

## 7. 向量 schema

- DB: `tenant_{tenant_id}`（如 `tenant_retail`）
- Table: `kb_meetings`
- Fields: `concept_id`, `type`, `title`, `description`, `tags`, `s3_uri`, `vector(dim=768)`, `created_at`
- 入库端点: `POST /api/v1/storage/vectors/{db}/{table}/add`
- 检索端点: `POST /api/v1/storage/vectors/{db}/{table}/search`

---

## 8. 验证结果

### 17 分钟实时测试

| 指标 | 值 |
|------|-----|
| 运行时长 | ~17 分钟 |
| 音频 chunks | 145 |
| Ray jobs（最近 100） | ASR=81, Summarize=13, Extract=6 |
| Job 成功率 | **100% completed**，零失败 |
| 知识入库 | 3 concepts（kb_meetings） |
| 语义检索 | 5 个查询全部返回 hits |
| Ray 集群 | 3 节点 12 CPU，job 完成后 idle |

### 架构验证

| 检查项 | 结果 |
|--------|------|
| Agent 通过 MCP 访问平台 | ✅ DataMCP + AssetMCP，不直连 Server REST API |
| Agent 不直接调用 ModelServing | ✅ ASR/LLM/embed 全在 Ray job 内 |
| Job 代码在 `jobs/{name}/main.py` | ✅ 不在 skill 根 |
| RAY_JOB_PARAMS 注入 | ✅ job 通过环境变量接收参数 |
| Skill 可复用 | ✅ 其他 Agent 可通过 `ray_submit_job` 提交 |
| 向量入库不覆盖 | ✅ 使用 `/add` 端点追加 |
| 12 容器全绿 | ✅ |
| Ray 3 节点 12 CPU | ✅ |

---

## 9. 已知限制

| 限制 | 说明 |
|------|------|
| 内存存储 | 会议状态在 Agent 内存中，重启丢失 |
| 无认证 | Web UI 和 API 无认证 |
| 无并发控制 | 单会议串行处理 |
| 无错误重试 | Ray job 失败后不重试 |
| 单租户 | 硬编码 `retail` 租户 |
| 轮询模式 | Agent 轮询 job 状态（非回调），增加 ~1-3s 延迟 |
