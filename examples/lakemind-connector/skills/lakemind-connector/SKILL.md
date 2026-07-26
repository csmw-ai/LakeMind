---
name: lakemind-connector
version: 0.1.0
type: agent-skill
description: "LakeMind 统一连接器 — 让 AI Agent 存取认知资产 + 提交 Ray jobs + ASR"
tags: [mcp, connector, cognition, lakemind, ray-jobs, asr]
---

# lakemind-connector

## 用途

让 AI Agent（如 opencode）通过 LakeMind 存取认知资产并提交分布式计算任务：
- **知识** → 向量化 → LanceDB 向量入库 → 语义检索
- **记忆** → AssetMCP add_memory / search_memory / list_memory
- **Ray Jobs** → 提交 Skill-based 分布式计算 → 轮询状态 → 获取结果
- **ASR** → FunASR 语音识别 → 文本
- **S3** → 对象存储（URI-based API，支持 `s3://bucket/key`）

## 架构

```
Agent (opencode)
  │
  │  1. search_skill("lakemind connector")  ← 从 LakeMind 检索本 Skill
  │  2. get_skill("lakemind-connector")     ← 下载 Skill 代码
  │  3. 在自身运行时执行 Skill 代码          ← LakeMind 不执行，Agent 自己执行
  │
  ▼
Skill 代码运行:
  ├─ AssetMCP (:8401) → 记忆存取 (MCP tools)
  ├─ AdminMCP (:8403) → 租户/Token 管理 (MCP tools)
  ├─ ModelServing (:10824) → Embedding / LLM / ASR (REST API)
  └─ Server (:10823) → 向量存储 / S3 / Ray jobs (REST API)
```

## 文件

| 文件 | 职责 |
|------|------|
| `connector.py` | LakeMindConnector — MCP + REST + Ray Jobs 统一封装 |
| `cognition.py` | 知识概念 + 记忆消息定义 |
| `cli.py` | CLI 入口 (ingest/search/memories/jobs/asr/verify/...) |

## API

### 知识 (向量存储)
```python
await conn.store_knowledge("my-kb", concepts)     # 入库（自动 /add 追加）
hits = await conn.search_knowledge("query", "my-kb")  # 语义检索
rows = await conn.scan_knowledge("my-kb")          # 浏览全部
```

### 记忆 (AssetMCP)
```python
await conn.add_memory([{"role": "user", "content": "记忆内容"}])
results = await conn.search_memory("查询")
memories = await conn.list_memory()
```

### Ray Jobs (Server REST)
```python
# 提交 job
job = await conn.submit_job(
    skill_uri="lake://skills/my-skill",
    job_name="asr",
    params={"input_uri": "s3://bucket/data/input.wav", "result_uri": "s3://bucket/data/result.json"},
)

# 轮询直到完成
status = await conn.poll_job(job["job_id"], interval=1.5, timeout=120)

# 一步提交+等待
status = await conn.submit_and_wait("lake://skills/my-skill", "asr", params)

# 查询/管理
status = await conn.get_job_status(job_id)
result = await conn.get_job_result(job_id)
await conn.cancel_job(job_id)
jobs = await conn.list_jobs(status="running")
```

### ASR (ModelServing)
```python
result = await conn.asr(audio_bytes)
clean_text = LakeMindConnector.clean_asr_text(result["text"])
```

### S3 (URI-based)
```python
await conn.s3_put_uri("s3://bucket/path/file.json", data_bytes)
content = await conn.s3_get_uri("s3://bucket/path/file.json")
exists = await conn.s3_exists_uri("s3://bucket/path/file.json")
```

### Skill 打包上传
```python
uri = await conn.upload_skill("skills/my-skill", "my-skill")
# → s3://lakemind-filesets/{tenant}/skills/my-skill.zip
```

### 健康检查
```python
health = await conn.check_health()
# → {model_serving: {ok, models}, server: {ok, distributed}, asset_mcp: {ok}, all_ok}
```

## 依赖

- `httpx` — REST API 调用
- `mcp` — MCP 协议客户端

## 环境变量

| 变量 | 说明 |
|------|------|
| `ASSET_MCP_URL` | AssetMCP 端点 (default: http://localhost:8401/mcp) |
| `ADMIN_MCP_URL` | AdminMCP 端点 (default: http://localhost:8403/mcp) |
| `SERVER_API_URL` | Server REST API (default: http://localhost:10823) |
| `MODEL_SERVING_URL` | ModelServing (default: http://localhost:10824) |
| `OPENCODE_TOKEN` | opencode 租户 Token |
| `TENANT_ID` | 租户 ID (default: opencode) |
