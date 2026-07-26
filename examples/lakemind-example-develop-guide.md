# LakeMind Example 开发指南

> 本指南指导开发者在 LakeMind 平台之上构建独立 Agent 示例（example）。
> 示例项目可以独立于 LakeMind 主仓库存在，本指南是唯一的开发规范。

---

## 目录

1. [定位与边界](#1-定位与边界)
2. [架构纪律（必读）](#2-架构纪律必读)
3. [前置条件](#3-前置条件)
4. [项目结构模板](#4-项目结构模板)
5. [MCP 客户端开发](#5-mcp-客户端开发)
6. [Skill 开发](#6-skill-开发)
7. [Job 开发](#7-job-开发)
8. [模型 Profile 配置](#8-模型-profile-配置)
9. [Skill 打包与发布](#9-skill-打包与发布)
10. [S3 路径约定](#10-s3-路径约定)
11. [认证与租户配置](#11-认证与租户配置)
12. [Docker 部署](#12-docker-部署)
13. [发现平台问题 → 提交 Issue](#13-发现平台问题--提交-issue)
14. [开发检查清单](#14-开发检查清单)

---

## 1. 定位与边界

LakeMind 是**认知资产存取平台 + 受控 Job Runtime**。Example 是运行在 LakeMind 之上的独立 Agent 应用，演示如何通过 LakeMind 的能力构建端到端业务场景。

**Example 的职责：**
- 业务 UI + 用户交互
- 业务编排逻辑（何时提交 job、何时萃取知识、何时存记忆）
- Skill 包开发（Job 定义）

**Example 不负责：**
- 运行 Agent 的完整推理循环（那是 Agent 框架的事）
- 管理模型（那是 LakeMind ControlCenter 的事）
- 管理存储引擎（那是 LakeMind Server 的事）

---

## 2. 架构纪律（必读）

### 2.1 核心规则：Agent 通过 MCP 访问平台，不直连 Server REST API

```
                    ┌─────────────────────────────────────┐
                    │          Example Agent              │
                    │  (FastAPI / 任意框架)               │
                    └──────────┬──────────┬──────────────┘
                               │          │
                    ┌──────────▼──┐  ┌────▼──────────┐
                    │  DataMCP    │  │  AssetMCP     │
                    │  (:8402)    │  │  (:8401)      │
                    │  S3/Ray/表  │  │  知识/记忆    │
                    └──────┬──────┘  └──────┬────────┘
                           │                │
                    ┌──────▼────────────────▼───────────┐
                    │      LakeMind Server (:10823)      │
                    └────────────────────────────────────┘
```

**Agent 进程**（含 backend、scripts）访问平台能力时，**必须通过 MCP**：

| 能力 | MCP | Tool | 禁止的直连 |
|------|-----|------|-----------|
| S3 读写 | DataMCP | `s3_put` / `s3_get` / `s3_list` / `s3_delete` | ~~Server `/api/v1/storage/objects`~~ |
| Ray job 提交/轮询 | DataMCP | `ray_submit_job` / `ray_job_status` / `ray_job_result` | ~~Server `/api/v1/compute/jobs/*`~~ |
| Iceberg 表操作 | DataMCP | `create_table` / `write_table` / `query_table` / `list_tables` | ~~Server `/api/v1/storage/tables/*`~~ |
| 向量检索 | DataMCP | `vector_search` | ~~Server `/api/v1/storage/vectors/*`~~ |
| KV 缓存 | DataMCP | `kv_get` / `kv_set` / `kv_delete` / `kv_scan` | ~~Server `/api/v1/storage/kv/*`~~ |
| 知识入库/检索 | AssetMCP | `ingest_knowledge` / `search_knowledge` | ~~Server `/api/v1/cognitive/knowledge/*`~~ |
| 记忆读写 | AssetMCP | `add_memory` / `search_memory` / `list_memory` | ~~Server `/api/v1/cognitive/memory/*`~~ |
| Skill 注册 | AssetMCP | `register_skill` / `list_skills` | ~~Server `/api/v1/skills/*`~~ |

### 2.2 例外：Skill 内的 Job 可以直连 Server REST API 和 ModelServing

```
┌─────────────────────────────────────────────────┐
│  Ray Worker (Job 运行环境)                       │
│  skills/{name}/jobs/{job}/main.py               │
│                                                  │
│  ✅ 直连 Server REST API  (S3 读写)             │
│  ✅ 直连 ModelServing     (ASR/LLM/Embedding)   │
│  ❌ 不走 MCP            (MCP 是 Agent 入口)     │
└─────────────────────────────────────────────────┘
```

**为什么 Job 不走 MCP？**
- Job 部署到 LakeMind Ray 集群内执行，是平台的"内部计算"
- Job 通过 `RAY_JOB_PARAMS` 环境变量接收参数，通过 `env_overrides` 接收密钥
- MCP 是 Agent 的入口抽象，Job 是平台的执行单元，两者职责不同
- Job 内直连 Server/ModelServing 性能更好（无 MCP 序列化开销）

### 2.3 例外：Setup 脚本可以直连做健康检查

`scripts/setup.py` 中的健康检查（`GET /api/v1/system/health`、`GET /v1/models`）可以直接 HTTP 调用，因为这是诊断而非数据操作。

### 2.4 模型管理：通过 ModelServing API 配置，不通过 MCP

模型和 Profile 的 CRUD 通过 ModelServing REST API（`/v1/models`、`/v1/profiles`）完成，不在 MCP 工具中暴露。这是平台管理操作，由 `scripts/seed_models.py` 在启动时执行。

### 2.5 架构纪律速查表

| 组件 | Server REST | ModelServing | DataMCP | AssetMCP |
|------|:-----------:|:------------:|:-------:|:--------:|
| Agent backend | ❌ | ❌ | ✅ | ✅ |
| Agent scripts (setup) | ⚠️ 仅 health | ⚠️ 仅 health | ✅ | ✅ |
| Agent scripts (seed_models) | ❌ | ✅ | ❌ | ❌ |
| Agent scripts (publish_skill) | ✅ S3+注册 | ❌ | 可选 | 可选 |
| Skill Job (Ray worker) | ✅ | ✅ | ❌ | ❌ |

---

## 3. 前置条件

### 3.1 LakeMind 平台运行中

```bash
# 验证 12 容器全部 healthy
docker ps --format "table {{.Names}}\t{{.Status}}" | findstr lakemind

# 预期输出（12 容器）：
# lakemind-seaweedfs        Up (healthy)
# lakemind-postgres         Up (healthy)
# lakemind-valkey           Up (healthy)
# lakemind-server-api       Up (healthy)
# lakemind-ray-head         Up
# lakemind-ray-worker       Up
# lakemind-asset-mcp        Up (healthy)
# lakemind-data-mcp         Up (healthy)
# lakemind-admin-mcp        Up (healthy)
# lakemind-model-serving    Up (healthy)
# lakemind-control-center   Up (healthy)
# lakemind-telemetry-agent  Up
```

### 3.2 平台端口

| 服务 | 端口 | 用途 |
|------|------|------|
| Server REST API | 10823 | Job 提交、S3、表、向量（Job 内用） |
| ModelServing | 10824 | LLM/ASR/Embedding（Job 内用 + seed 脚本用） |
| AssetMCP | 8401 | 知识/记忆/Skill（Agent 用） |
| DataMCP | 8402 | S3/Ray/表/KV（Agent 用） |
| AdminMCP | 8403 | 用户/租户/健康（管理用） |
| ControlCenter | 3000 | 管理 UI |

### 3.3 Docker 网络

Example 容器必须加入 LakeMind 的 Docker 网络：

```yaml
networks:
  lakemind:
    external: true
    name: lakemind_lakemind   # 注意前缀是 {project_name}_lakemind
```

---

## 4. 项目结构模板

```
my-example-agent/
├── .env.example                    # 环境变量模板
├── Dockerfile                      # 容器构建
├── docker-compose.yml              # 编排（单服务 + 外部网络）
├── entrypoint.sh                   # 启动序列
├── pyproject.toml                  # Python 依赖
├── README.md                       # 示例说明
├── DESIGN.md                       # 设计文档
│
├── backend/                        # Agent 后端（FastAPI）
│   ├── pyproject.toml
│   └── app/
│       ├── __init__.py
│       ├── config.py               # 环境变量 → 常量
│       ├── main.py                 # FastAPI 入口
│       ├── security.py             # 认证（可选）
│       ├── db.py                   # 本地 SQLite（可选）
│       ├── api/                    # 路由
│       │   ├── __init__.py
│       │   └── *.py
│       └── services/
│           ├── __init__.py
│           ├── lake_client.py      # ★ MCP 客户端封装
│           └── pipeline_service.py # 业务编排
│
├── frontend/                       # 前端（可选）
│   ├── package.json
│   └── src/
│
├── scripts/                        # 运维脚本
│   ├── setup.py                    # 健康检查 + Skill 上传
│   ├── publish_skill.py            # Skill 打包发布
│   ├── seed_models.py              # 模型 Profile 配置
│   └── test_mcp.py                 # MCP 连通性测试
│
├── skills/                         # Skill 包
│   └── my-skill/
│       ├── SKILL.md                # Skill 文档
│       ├── manifest.yaml           # Skill 清单
│       ├── lakemind_utils.py       # Job 共享工具
│       └── jobs/                   # Ray Job 定义
│           ├── job_a/
│           │   ├── main.py
│           │   └── ray.yaml
│           └── job_b/
│               ├── main.py
│           └── ray.yaml
│
└── issues/                         # 平台问题报告（见 §13）
    └── README.md
```

---

## 5. MCP 客户端开发

### 5.1 连接方式

LakeMind MCP 使用 **Streamable HTTP** 传输，路径为 `/mcp`：

```python
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async with streamablehttp_client(
    "http://localhost:8402/mcp",                          # DataMCP
    headers={"Authorization": "Bearer <MCP_TOKEN>"},     # Bearer 认证
) as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("s3_put", {"uri": uri, "body_b64": b64})
        data = json.loads(result.content[0].text)        # 工具返回 JSON 文本
```

### 5.2 封装模式（推荐）

将 MCP 调用封装为单一客户端类，屏蔽工具名和参数细节。完整模板见 `examples/meeting-agent/backend/app/services/lake_client.py`，核心结构：

```python
# backend/app/services/lake_client.py
import base64, json, logging, os
from ..config import ASSET_MCP_URL, DATA_MCP_URL, MCP_TOKEN

logger = logging.getLogger(__name__)

class MCPError(Exception):
    def __init__(self, stage: str, message: str):
        self.stage = stage
        self.message = message
        super().__init__(f"[{stage}] {message}")

async def _call_mcp(url: str, tool: str, arguments: dict) -> dict:
    """调用 MCP 工具，返回解析后的 JSON。"""
    from mcp.client.streamable_http import streamablehttp_client
    from mcp import ClientSession
    try:
        async with streamablehttp_client(
            url, headers={"Authorization": f"Bearer {MCP_TOKEN}"},
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments=arguments)
                if result.isError:
                    err = result.content[0].text if result.content else "unknown"
                    raise MCPError(tool, f"MCP tool error: {err}")
                text = result.content[0].text if result.content else "{}"
                return json.loads(text)
    except MCPError:
        raise
    except Exception as e:
        raise MCPError(tool, f"MCP call failed: {type(e).__name__}: {e}")

class LakeClient:
    # S3 (DataMCP)
    async def s3_put(self, uri: str, data: bytes) -> dict:
        body_b64 = base64.b64encode(data).decode("ascii")
        return await _call_mcp(DATA_MCP_URL, "s3_put", {"uri": uri, "body_b64": body_b64})

    async def s3_get(self, uri: str) -> bytes:
        resp = await _call_mcp(DATA_MCP_URL, "s3_get", {"uri": uri})
        if "content_b64" in resp:
            return base64.b64decode(resp["content_b64"])
        return resp.get("content", "").encode("utf-8")

    # Ray Jobs (DataMCP)
    async def submit_job(self, skill_uri: str, job_name: str,
                         params: dict, env_overrides: dict = None) -> dict:
        return await _call_mcp(DATA_MCP_URL, "ray_submit_job", {
            "skill_uri": skill_uri, "job_name": job_name,
            "params": params, "env_overrides": env_overrides or {},
            "resources": {},
        })

    async def get_job_status(self, job_id: str) -> dict:
        return await _call_mcp(DATA_MCP_URL, "ray_job_status", {"job_id": job_id})

    # 知识 (AssetMCP)
    async def knowledge_search(self, query: str, kb_name: str = "",
                               top_k: int = 5) -> dict:
        args = {"query": query, "top_k": top_k}
        if kb_name:
            args["kb_name"] = kb_name
        return await _call_mcp(ASSET_MCP_URL, "search_knowledge", args)

    # 记忆 (AssetMCP)
    async def memory_add(self, messages: list[dict],
                         metadata: dict | None = None) -> dict:
        return await _call_mcp(ASSET_MCP_URL, "add_memory", {
            "messages": messages, "infer": False, "metadata": metadata or {},
        })

lake = LakeClient()   # 全局单例
```

### 5.3 DataMCP 工具完整清单（24 tools）

| 分类 | 工具 | 参数 | 说明 |
|------|------|------|------|
| **S3** | `s3_get` | `uri` | 读取对象，返回 `content`/`content_b64` |
| | `s3_put` | `uri`, `body`/`body_b64` | 写入对象 |
| | `s3_list` | `uri`, `limit` | 列举对象 |
| | `s3_delete` | `uri` | 删除对象 |
| **Ray** | `ray_submit_job` | `skill_uri`, `job_name`, `params`, `env_overrides`, `resources` | 提交 Skill Job |
| | `ray_job_status` | `job_id` | 查询状态 |
| | `ray_job_result` | `job_id` | 获取结果 |
| | `ray_job_cancel` | `job_id` | 取消 Job |
| | `ray_job_list` | `status` | 列举 Job |
| | `list_skill_jobs` | `skill_uri` | 列举 Skill 中的 Job 名 |
| **Iceberg** | `create_table` | `name`, `schema`, `partition` | 建表 |
| | `write_table` | `table`, `rows`, `mode` | 写表（append/overwrite） |
| | `query_table` | `table`, `columns`, `filter`, `limit` | 扫描表 |
| | `sql_query` | `sql` | 即席 SQL（DuckDB） |
| | `list_tables` | `namespace` | 列表 |
| | `describe_table` | `table` | 表结构 |
| | `drop_table` | `table` | 删表 |
| **向量** | `vector_search` | `table`, `query`, `top_k`, `filter` | 向量检索（自动 embed） |
| **KV** | `kv_get` | `key` | 读 Valkey |
| | `kv_set` | `key`, `value`, `ttl` | 写 Valkey |
| | `kv_delete` | `key` | 删 Valkey |
| | `kv_scan` | `pattern`, `limit` | 扫描 Valkey |
| **图** | `graph_query` | `concept`, `relation` | 查询图 |
| | `graph_update` | `concept`, `relation`, `target` | 更新图 |

### 5.4 AssetMCP 工具完整清单（23 tools）

| 分类 | 工具 | 参数 | 说明 |
|------|------|------|------|
| **知识** | `register_knowledge` | `name`, `description` | 创建知识库 |
| | `ingest_knowledge` | `kb_name`, `concepts` | 入库（自动 embed + 图链接） |
| | `search_knowledge` | `query`, `kb_name`, `top_k`, `filter` | 语义检索 |
| | `get_knowledge` | `kb_name`, `concept_id` | 获取概念 |
| | `list_knowledge` | — | 列出知识库 |
| | `list_concepts` | `kb_name`, `type`, `tag`, `page`, `page_size` | 列出概念 |
| | `delete_knowledge` | `kb_name` | 删除知识库 |
| **记忆** | `add_memory` | `messages`, `metadata`, `infer`, `expiration_date`, `run_id` | 添加记忆 |
| | `search_memory` | `query`, `filters`, `top_k`, `threshold`, `run_id` | 检索记忆 |
| | `get_memory` | `memory_id` | 获取单条 |
| | `list_memory` | `filters`, `page`, `page_size`, `run_id` | 列出记忆 |
| | `update_memory` | `memory_id`, `content` | 更新 |
| | `delete_memory` | `memory_id` | 删除 |
| | `clear_memory` | `filters`, `run_id` | 清空 |
| | `memory_history` | `memory_id` | 变更历史 |
| **Skill** | `search_skill` | `query`, `top_k` | 语义搜索 Skill |
| | `register_skill` | `name`, `description`, `code`, `version`, `format` | 注册 Skill |
| | `get_skill` | `name`, `format` | 获取 Skill |
| | `list_skills` | — | 列出 Skill |
| | `delete_skill` | `name`, `format` | 删除 Skill |
| **本体** | `query_ontology` | `concept`, `relation` | 查询本体 |
| | `update_ontology` | `concept`, `relation`, `target`, ... | 更新本体 |
| | `delete_ontology` | `concept` | 删除概念 |

### 5.5 提交 Job 时的 env_overrides

Agent 通过 DataMCP `ray_submit_job` 提交 Job 时，必须把 Server 和 ModelServing 的连接信息注入 `env_overrides`，供 Job 在 Ray worker 内直连使用：

```python
await lake.submit_job(
    skill_uri="s3://lakemind-filesets/{tenant}/skills/my-skill-v1.0.0.zip",
    job_name="my_job",
    params={"input_uri": chunk_uri, "result_key": "result/001"},
    env_overrides={
        "SERVER_API_URL": "http://lakemind-server-api:10823",
        "SERVER_API_KEY": SERVER_KEY,
        "MODEL_SERVING_URL": "http://lakemind-model-serving:10824",
        "MODELSERVING_API_KEY": MS_KEY,
    },
)
```

---

## 6. Skill 开发

### 6.1 manifest.yaml — Skill 清单

```yaml
name: my-skill
version: "1.0.0"
description: "我的 Skill 做什么"
entry_point: jobs              # Job 目录名

input_schema:
  input_uri:
    type: string
    required: true
    description: "输入数据 S3 URI"
  result_key:
    type: string
    required: true
    description: "结果键名"

output_schema:
  text:
    type: string
    description: "处理结果文本"

model_profiles:                 # 声明依赖的模型 Profile
  - my-asr
  - my-llm
  - my-embedding

jobs:
  my_job:
    description: "Job 做什么"
    model_profile: my-llm       # 使用的 Profile
    inputs:
      input_uri: string
      result_key: string
    outputs:
      text: string
```

### 6.2 SKILL.md — Skill 文档

```markdown
# My Skill

一句话描述 Skill 做什么。

## Jobs

- **my_job** (`jobs/my_job/`): 输入 → 处理 → 输出

## 模型服务

所有 LLM / ASR / Embedding 调用通过 LakeMindModelServing (:10824)，
使用 **profile 名** 路由（管理员可在 ControlCenter UI 动态切换模型）：

- LLM: `profile="my-llm"` → /v1/chat/completions
- ASR: `profile="my-asr"` → /v1/audio/transcriptions
- Embedding: `profile="my-embedding"` → /v1/embeddings

## 运行方式

Agent 通过 DataMCP `ray_submit_job` 提交，参数通过 `RAY_JOB_PARAMS` 注入，
结果写入 S3。
```

### 6.3 lakemind_utils.py — Job 共享工具

**此文件运行在 Ray worker 内，直连 Server REST API 和 ModelServing：**

```python
"""Job 共享工具 — 运行在 Ray worker 内，直连 Server/ModelServing。"""
import json, os, logging, httpx

logger = logging.getLogger(__name__)

SERVER_URL = os.environ.get("SERVER_API_URL", "http://lakemind-server-api:10823")
SERVER_KEY = os.environ.get("SERVER_API_KEY", "")
MS_URL = os.environ.get("MODEL_SERVING_URL", "http://lakemind-model-serving:10824")
MS_KEY = os.environ.get("MODELSERVING_API_KEY", "")


def download_from_s3(uri: str) -> bytes:
    """通过 Server REST API 下载 S3 对象。"""
    from urllib.parse import urlparse
    p = urlparse(uri)
    url = f"{SERVER_URL}/api/v1/storage/objects/{p.netloc}/{p.path.lstrip('/')}"
    resp = httpx.get(url, headers={"Authorization": f"Bearer {SERVER_KEY}"}, timeout=120)
    resp.raise_for_status()
    return resp.content


def upload_to_s3(uri: str, data: bytes) -> dict:
    """通过 Server REST API 上传 S3 对象。"""
    from urllib.parse import urlparse
    p = urlparse(uri)
    url = f"{SERVER_URL}/api/v1/storage/objects/{p.netloc}/{p.path.lstrip('/')}"
    resp = httpx.put(url, content=data, headers={"Authorization": f"Bearer {SERVER_KEY}"}, timeout=120)
    resp.raise_for_status()
    return resp.json()


def llm_chat(system_prompt: str, user_content: str, profile: str = "my-llm") -> str:
    """调用 ModelServing LLM（通过 profile 名路由）。6 次重试。"""
    for attempt in range(6):
        try:
            resp = httpx.post(
                f"{MS_URL}/v1/chat/completions",
                headers={"Authorization": f"Bearer {MS_KEY}"},
                json={"model": profile, "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ]},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning("llm_chat attempt %d failed: %s", attempt + 1, e)
            if attempt == 5:
                raise
            import time; time.sleep(5 * (attempt + 1))


def asr(audio: bytes, filename: str = "audio.wav", profile: str = "my-asr") -> dict:
    """调用 ModelServing ASR（通过 profile 名路由）。"""
    resp = httpx.post(
        f"{MS_URL}/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {MS_KEY}"},
        files={"file": (filename, audio)},
        data={"model": profile},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()


def embed(texts: list[str], profile: str = "my-embedding") -> list[list[float]]:
    """调用 ModelServing Embedding（通过 profile 名路由）。"""
    resp = httpx.post(
        f"{MS_URL}/v1/embeddings",
        headers={"Authorization": f"Bearer {MS_KEY}"},
        json={"model": profile, "input": texts},
        timeout=30,
    )
    resp.raise_for_status()
    return [item["embedding"] for item in resp.json()["data"]]
```

---

## 7. Job 开发

### 7.1 ray.yaml — Job 声明

```yaml
# skills/my-skill/jobs/my_job/ray.yaml
entrypoint: "python jobs/my_job/main.py"
dependencies:
  - httpx
resources:
  num_cpus: 1
```

### 7.2 main.py — Job 入口

```python
"""Job 入口 — 运行在 Ray worker 内。"""
import json, os, sys

# 导入共享工具（需要把 skill 根目录加入 path）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lakemind_utils import download_from_s3, upload_to_s3, llm_chat


def main():
    # 1. 从环境变量读取参数（Server 注入）
    params = json.loads(os.environ["RAY_JOB_PARAMS"])
    input_uri = params["input_uri"]
    result_key = params["result_key"]

    # 2. 下载输入
    data = download_from_s3(input_uri)
    text = data.decode("utf-8")

    # 3. 调用 LLM（通过 profile 名）
    result = llm_chat(
        system_prompt="你是一个助手。",
        user_content=text,
        profile="my-llm",           # ← profile 名，不是模型名
    )

    # 4. 上传结果到 S3
    result_uri = input_uri.rsplit("/input/", 1)[0] + f"/results/{result_key}.json"
    upload_to_s3(result_uri, json.dumps({"text": result}).encode())

    # 5. print 的内容作为 Ray job result 可被 Agent 获取
    print(json.dumps({"text": result}))


if __name__ == "__main__":
    main()
```

### 7.3 Job 开发规则

| 规则 | 说明 |
|------|------|
| 参数通过 `RAY_JOB_PARAMS` | `json.loads(os.environ["RAY_JOB_PARAMS"])` |
| S3 读写通过 Server REST | `lakemind_utils.download_from_s3` / `upload_to_s3` |
| LLM/ASR/Embedding 通过 ModelServing | 使用 **profile 名** 而非模型名 |
| 结果写 S3 + print | Agent 轮询 job 完成后从 S3 下载结果 |
| 不走 MCP | Job 是平台内部计算，不是 Agent 入口 |
| 声明 dependencies | `ray.yaml` 中列出 pip 依赖 |

### 7.4 Job 内向量化入库

Job 内如需向量化入库（如知识萃取后写入向量表），使用 Server REST API：

```python
def ingest_vectors(concepts: list[dict], tenant_id: str, kb_name: str = "my_kb"):
    """通过 Server REST API 向量入库。"""
    texts = [c["title"] + " " + c.get("body", "") for c in concepts]
    vectors = embed(texts, profile="my-embedding")
    db = f"tenant_{tenant_id}"
    table = f"kb_{kb_name}"
    url = f"{SERVER_URL}/api/v1/storage/vectors/{db}/{table}/add"
    rows = [{"concept_id": c["id"], "title": c["title"],
             "body": c.get("body", ""), "vector": vec}
            for c, vec in zip(concepts, vectors)]
    resp = httpx.post(url, headers={"Authorization": f"Bearer {SERVER_KEY}"},
                      json={"rows": rows}, timeout=30)
    resp.raise_for_status()
```

> **注意**：Agent 侧的知识入库应通过 AssetMCP `ingest_knowledge`（OKF 格式 + 自动 embed + 图链接），而非直连向量 API。上例仅适用于 Job 内需要绕过 OKF 格式的场景。

---

## 8. 模型 Profile 配置

### 8.1 Profile 概念

Profile 是**模型名的逻辑别名**。Agent 和 Job 用 profile 名（如 `my-llm`）而非硬编码模型名（如 `deepseek-v4-flash`），管理员可在 ControlCenter UI 动态切换底层模型，无需改代码。

```
Agent/Job  --调用-->  ModelServing  --解析 profile-->  实际模型
  model="my-llm"       /v1/chat/completions              deepseek-v4-flash
```

### 8.2 seed_models.py — 启动时配置 Profile

```python
"""Seed model profiles for my-agent into ModelServing."""
import asyncio, os, httpx

MS_URL = os.environ.get("MODEL_SERVING_URL", "http://localhost:10824").rstrip("/")
MS_KEY = os.environ.get("MODELSERVING_API_KEY", "lakemind-modelserving-key")

PROFILES = [
    {"name": "my-llm", "model_type": "chat", "model_name": "deepseek-v4-flash",
     "description": "LLM for my agent"},
    {"name": "my-embedding", "model_type": "embedding",
     "model_name": "jinaai/jina-embeddings-v2-base-zh",
     "description": "Embedding for my agent"},
    {"name": "my-asr", "model_type": "asr", "model_name": "whisper-small",
     "description": "ASR for my agent"},
]


async def main():
    headers = {"Authorization": f"Bearer {MS_KEY}"}
    async with httpx.AsyncClient(base_url=MS_URL, headers=headers, timeout=30) as c:
        models = (await c.get("/v1/models")).json()
        model_map = {m["name"]: m for m in models.get("data", [])}

        profiles = (await c.get("/v1/profiles")).json()
        profile_map = {p["name"]: p for p in profiles.get("data", [])}

        for p in PROFILES:
            model = model_map.get(p["model_name"])
            if not model:
                print(f"  [FAIL] model '{p['model_name']}' not found")
                continue

            if p["name"] in profile_map:
                existing = profile_map[p["name"]]
                if existing.get("model_id") == model["model_id"]:
                    print(f"  [SKIP] profile '{p['name']}' already -> {p['model_name']}")
                    continue
                resp = await c.put(f"/v1/profiles/{existing['profile_id']}",
                                   json={"model_id": model["model_id"]})
                print(f"  [OK] updated profile '{p['name']}'" if resp.status_code == 200
                      else f"  [FAIL] update: {resp.status_code}")
                continue

            resp = await c.post("/v1/profiles", json={
                "name": p["name"], "model_type": p["model_type"],
                "model_id": model["model_id"], "description": p["description"],
            })
            print(f"  [OK] created profile '{p['name']}'" if resp.status_code == 200
                  else f"  [FAIL] create: {resp.status_code} {resp.text[:80]}")


if __name__ == "__main__":
    asyncio.run(main())
```

### 8.3 可用模型（通过 `GET /v1/models` 查询）

| 模型名 | 类型 | 说明 |
|--------|------|------|
| `deepseek-v4-flash` | chat | DeepSeek V4 Flash（外部 API） |
| `jinaai/jina-embeddings-v2-base-zh` | embedding | Jina 中文嵌入 dim=768（本地 fastembed） |
| `whisper-small` | asr | Whisper Small（本地 faster-whisper） |

> 完整列表通过 `GET http://localhost:10824/v1/models` 查询。模型可通过 `POST /v1/models` 动态注册，无需重启。

---

## 9. Skill 打包与发布

### 9.1 打包

Skill 是一个 zip 包，包含 `jobs/` 目录、`lakemind_utils.py`、`manifest.yaml`、`SKILL.md`：

```python
import io, zipfile, os

def pack_skill(skill_dir: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(skill_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, skill_dir).replace("\\", "/")
                zf.write(fpath, arcname)
    return buf.getvalue()
```

### 9.2 上传到 S3

```python
# 版本化 S3 路径
skill_s3_uri = f"s3://lakemind-filesets/{TENANT_ID}/skills/my-skill-v1.0.0.zip"

# 通过 DataMCP 上传
await lake.s3_put(skill_s3_uri, zip_bytes)
```

### 9.3 版本约定

- Skill zip 命名：`{skill-name}-v{version}.zip`（如 `meeting-processing-v0.2.5.zip`）
- S3 路径：`s3://lakemind-filesets/{tenant}/skills/{skill-name}-v{version}.zip`
- `lake_client.py` 中 `submit_job` 构造 `skill_uri` 时必须与上传的版本号一致
- **版本号必须同步**：`publish_skill.py` 上传的版本 = `lake_client.py` 引用的版本

### 9.4 publish_skill.py 完整模板

```python
"""Pack and publish skill to S3 + Server skill registry."""
import asyncio, io, os, sys, zipfile, httpx, yaml

SERVER_URL = os.environ.get("SERVER_API_URL", "http://localhost:10823").rstrip("/")
SERVER_KEY = os.environ.get("SERVER_API_KEY", "")
TENANT_ID = os.environ.get("TENANT_ID", "examples-my-agent")
S3_BUCKET = "lakemind-filesets"
SKILL_NAME = "my-skill"
SKILL_VERSION = "1.0.0"
SKILL_DIR = os.path.join(os.path.dirname(__file__), "..", "skills", SKILL_NAME)


def pack_skill() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(SKILL_DIR):
            for fname in files:
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, SKILL_DIR).replace("\\", "/")
                zf.write(fpath, arcname)
    return buf.getvalue()


async def main():
    zip_bytes = pack_skill()
    skill_s3_uri = f"s3://{S3_BUCKET}/{TENANT_ID}/skills/{SKILL_NAME}-v{SKILL_VERSION}.zip"

    headers = {"Authorization": f"Bearer {SERVER_KEY}", "X-Tenant-Id": TENANT_ID}
    async with httpx.AsyncClient(base_url=SERVER_URL, headers=headers, timeout=30) as c:
        # 1. 上传 zip 到 S3
        from urllib.parse import urlparse
        p = urlparse(skill_s3_uri)
        resp = await c.put(f"/api/v1/storage/objects/{p.netloc}/{p.path.lstrip('/')}",
                           content=zip_bytes)
        print(f"upload: {resp.status_code}")

        # 2. 注册 Skill（如果 Server 有 /api/v1/skills/register 端点）
        manifest_path = os.path.join(SKILL_DIR, "manifest.yaml")
        with open(manifest_path, encoding="utf-8") as f:
            manifest = yaml.safe_load(f)

        existing = (await c.get("/api/v1/skills")).json()
        skill_id = None
        for s in existing.get("items", []):
            if s.get("name") == SKILL_NAME:
                skill_id = s.get("asset_id") or s.get("skill_id")
                break

        body = {"manifest": manifest,
                "code_package": {"s3_uri": skill_s3_uri, "size_bytes": len(zip_bytes)},
                "trust_level": "demo"}
        if skill_id:
            resp = await c.put(f"/api/v1/skills/{skill_id}", json=body)
        else:
            resp = await c.post("/api/v1/skills/register", json=body)
            skill_id = resp.json().get("asset_id")
        print(f"register: {resp.status_code}")

        # 3. 发布
        if skill_id:
            resp = await c.post(f"/api/v1/skills/{skill_id}/publish")
            print(f"publish: {resp.status_code}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 10. S3 路径约定

### 10.1 基本格式

```
s3://lakemind-filesets/{tenant_id}/...
```

- **Bucket**：固定 `lakemind-filesets`
- **第一级路径**：`tenant_id`（租户隔离）
- **后续路径**：由 example 自行约定

### 10.2 推荐路径模式

```
s3://lakemind-filesets/{tenant_id}/
├── skills/
│   └── {skill-name}-v{version}.zip       # Skill 包
│
└── users/{principal_id}/                 # 按用户隔离
    └── {business_context}/               # 业务上下文（如 meetings/）
        └── {task_id}/
            ├── input/                    # 输入数据
            │   └── {seq:06d}.{ext}
            ├── results/                  # Job 结果
            │   └── {result_key}.json
            └── artifacts/                # 最终产物
                └── {name}.{ext}
```

### 10.3 路径构造示例

```python
def s3_path(tenant_id: str, principal_id: str, task_id: str, *parts: str) -> str:
    return f"s3://lakemind-filesets/{tenant_id}/users/{principal_id}/{task_id}/" + "/".join(parts)

# 输入
chunk_uri = s3_path(tenant, principal, task_id, "input", "audio", f"{seq:06d}.wav")
# 结果
result_uri = s3_path(tenant, principal, task_id, "results", f"asr-{seq:03d}.json")
```

---

## 11. 认证与租户配置

### 11.1 三层认证体系

```
Example Agent
    │
    ├── MCP 认证: Bearer <MCP_TOKEN>        ← 静态 token，在 MCP config.yaml 中注册
    │
    ├── Server 认证 (Job 内): Bearer <SERVER_API_KEY>  ← 平台内部密钥
    │
    └── ModelServing 认证 (Job 内): Bearer <MODELSERVING_API_KEY>  ← 平台内部密钥
```

### 11.2 为新 Example 注册 MCP Token

**步骤 1**：选择 `tenant_id` 和 `token`

```bash
TENANT_ID=examples-my-agent
MCP_TOKEN=my-agent-mcp-token
```

**步骤 2**：在 `LakeMindAssetMCP/config/config.yaml` 的 `tokens:` 列表追加：

```yaml
- token: "my-agent-mcp-token"
  agent_id: "my-agent"
  tenant_id: "examples-my-agent"
  scopes: ["asset"]
```

**步骤 3**：在 `LakeMindDataMCP/config/config.yaml` 的 `tokens:` 列表追加：

```yaml
- token: "my-agent-mcp-token"
  agent_id: "my-agent"
  tenant_id: "examples-my-agent"
  scopes: ["data"]
```

**步骤 4**：重启 MCP 容器

```bash
docker compose restart asset-mcp data-mcp
```

### 11.3 租户隔离命名约定

`tenant_id` 自动应用于所有资源：

| 资源 | 命名规则 | 示例（tenant=`examples-my-agent`） |
|------|----------|------|
| S3 key 前缀 | `{tenant_id}/...` | `examples-my-agent/skills/...` |
| LanceDB 数据库 | `tenant_{tenant_id}` | `tenant_examples-my-agent` |
| Iceberg namespace | `{tenant_id}_data` | `examples-my-agent_data` |
| Valkey key 前缀 | `{tenant_id}:` | `examples-my-agent:foo` |
| 图名 | `ontology_{tenant_id}` | `ontology_examples-my-agent` |

### 11.4 .env.example 模板

```bash
# LakeMind Server（Job 内直连用）
SERVER_API_URL=http://localhost:10823
SERVER_API_KEY=lakemind-internal-api-key

# LakeMind ModelServing（Job 内直连 + seed 脚本用）
MODEL_SERVING_URL=http://localhost:10824
MODELSERVING_API_KEY=lakemind-modelserving-key

# AssetMCP（Agent 用 — 知识/记忆）
ASSET_MCP_URL=http://localhost:8401/mcp
# DataMCP（Agent 用 — S3/Ray/表）
DATA_MCP_URL=http://localhost:8402/mcp
# MCP token（AssetMCP + DataMCP 共用）
MCP_TOKEN=my-agent-mcp-token

# 租户
TENANT_ID=examples-my-agent

# Skill
SKILL_URI=lake://skills/my-skill

# 业务参数
PORT=9200
```

---

## 12. Docker 部署

### 12.1 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn httpx aiosqlite mcp>=1.0 PyYAML

COPY backend/ /app/backend/
COPY frontend/dist/ /app/frontend/dist/
COPY skills/ /app/skills/
COPY scripts/ /app/scripts/
COPY entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh

ENV DB_PATH=/data/my-agent.db
ENV PORT=9200
EXPOSE 9200

CMD ["/app/entrypoint.sh"]
```

### 12.2 docker-compose.yml

```yaml
services:
  my-agent:
    build: .
    container_name: my-agent
    ports:
      - "9200:9200"
    environment:
      SERVER_API_URL: http://lakemind-server-api:10823
      SERVER_API_KEY: ${SERVER_API_KEY}
      MODEL_SERVING_URL: http://lakemind-model-serving:10824
      MODELSERVING_API_KEY: lakemind-modelserving-key
      TENANT_ID: examples-my-agent
      ASSET_MCP_URL: http://lakemind-asset-mcp:8401/mcp
      DATA_MCP_URL: http://lakemind-data-mcp:8402/mcp
      MCP_TOKEN: my-agent-mcp-token
      PORT: "9200"
    volumes:
      - my-agent-data:/data
    networks:
      - lakemind
    restart: unless-stopped

volumes:
  my-agent-data:

networks:
  lakemind:
    external: true
    name: lakemind_lakemind
```

### 12.3 entrypoint.sh

```bash
#!/bin/sh
set -e

echo "=== My Agent starting ==="

echo "[1/3] Seeding model profiles..."
python scripts/seed_models.py || echo "WARNING: seed_models failed, continuing..."

echo "[2/3] Publishing skill..."
python scripts/publish_skill.py || echo "WARNING: publish_skill failed, continuing..."

echo "[3/3] Starting backend..."
cd backend
exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-9200}
```

### 12.4 config.py

```python
# backend/app/config.py
import os

SERVER_URL = os.environ.get("SERVER_API_URL", "http://lakemind-server-api:10823").rstrip("/")
SERVER_KEY = os.environ.get("SERVER_API_KEY", "")
TENANT_ID = os.environ.get("TENANT_ID", "examples-my-agent")
MS_URL = os.environ.get("MODEL_SERVING_URL", "http://lakemind-model-serving:10824").rstrip("/")
MS_KEY = os.environ.get("MODELSERVING_API_KEY", "")
S3_BUCKET = os.environ.get("S3_BUCKET", "lakemind-filesets")

ASSET_MCP_URL = os.environ.get("ASSET_MCP_URL", "http://lakemind-asset-mcp:8401/mcp")
DATA_MCP_URL = os.environ.get("DATA_MCP_URL", "http://lakemind-data-mcp:8402/mcp")
MCP_TOKEN = os.environ.get("MCP_TOKEN", "my-agent-mcp-token")
```

---

## 13. 发现平台问题 → 提交 Issue

在开发 Example 过程中，可能发现 LakeMind 平台本身的 bug、缺失功能或文档错误。这些问题应记录到 `examples/issues/` 目录，并反馈给 LakeMind 平台团队。

### 13.1 Issue 目录结构

```
examples/issues/
├── README.md                    # Issue 提交说明
├── 001-assetmcp-embedding-hardcode.md   # Issue 编号-组件-简述
├── 002-server-jobs-submit-404.md
└── 003-datamcp-s3-list-pagination.md
```

### 13.2 Issue 模板

每个 issue 是一个 Markdown 文件，命名格式 `{序号}-{组件}-{简述}.md`：

```markdown
# Issue #001: AssetMCP embedding 模型名硬编码导致 502

**日期**: 2026-07-19
**严重程度**: P0 (阻断)
**组件**: LakeMindMCP/LakeMindAssetMCP
**发现者**: meeting-agent 开发

## 问题描述

AssetMCP `server_client.py` 的 `embed()` 方法硬编码模型名 `jina-embeddings-v2-base-zh`，
但 fastembed 实际需要 `jinaai/jina-embeddings-v2-base-zh`（带前缀）。
调用 `search_knowledge` 时 AssetMCP 内部 embed 返回 502。

## 复现步骤

1. 确保 ModelServing 运行，模型 `jina-embeddings-v2-base-zh` 已注册
2. 通过 AssetMCP 调用 `search_knowledge(query="test", kb_name="meetings")`
3. 观察返回错误

## 预期行为

`search_knowledge` 正常返回检索结果。

## 实际行为

```
Error executing tool search_knowledge: Server error '502 Bad Gateway'
for url 'http://lakemind-model-serving:10824/v1/embeddings'
```

## 根因

`LakeMindMCP/LakeMindAssetMCP/src/lakemind_asset_mcp/server_client.py:192`:
```python
json={"model": "jina-embeddings-v2-base-zh", "input": texts},  # 缺少 jinaai/ 前缀
```

## 建议修复

改为使用 profile 名或环境变量：
```python
json={"model": os.environ.get("EMBEDDING_PROFILE", "default-embedding"), "input": texts},
```

## 影响范围

所有通过 AssetMCP 使用 `search_knowledge` / `ingest_knowledge` 的 Agent。
```

### 13.3 Issue 提交流程

```
开发 Example
    │
    ├─ 发现平台行为异常（非 Example 自身 bug）
    │    │
    │    ├─ 1. 确认是平台问题而非 Example 代码问题
    │    │    （检查：MCP 工具返回错误？Server API 404/500？ModelServing 502？）
    │    │
    │    ├─ 2. 在 examples/issues/ 创建 issue 文件
    │    │    （使用 §13.2 模板，编号递增）
    │    │
    │    ├─ 3. 在 issue 中记录：复现步骤、预期/实际行为、根因分析、建议修复
    │    │
    │    └─ 4. 提交到 LakeMind 平台仓库的 examples/issues/ 目录
    │         （平台团队会定期 review 并创建对应的修复任务）
    │
    └─ 发现 Example 自身 bug
         │
         └─ 在 Example 项目内修复，不提交平台 issue
```

### 13.4 判断问题归属

| 现象 | 归属 | 处理方式 |
|------|------|----------|
| MCP 工具返回 `isError` | 可能是平台问题 | 检查 MCP 日志，确认是工具实现 bug 还是参数错误 |
| Server REST API 返回 404/500 | 可能是平台问题 | 检查路由是否存在、参数是否正确 |
| ModelServing 返回 502 | 可能是平台问题 | 检查模型名/profile 是否正确、模型是否已加载 |
| Agent 代码报错 | Example 问题 | 在 Example 项目内修复 |
| Job 代码报错 | Example 问题 | 检查 `lakemind_utils.py` 调用是否正确 |
| Skill zip 找不到 (404) | Example 问题 | 检查 `publish_skill.py` 是否上传了正确版本 |

### 13.5 examples/issues/README.md 模板

```markdown
# LakeMind 平台问题报告

本目录记录在 Example 开发过程中发现的 LakeMind 平台问题。

## 提交规则

1. 每个问题一个 Markdown 文件，命名 `{序号}-{组件}-{简述}.md`
2. 序号三位递增（001, 002, ...）
3. 使用 issue 模板（见 lakemind-example-develop-guide.md §13.2）
4. 只记录平台问题，不记录 Example 自身 bug

## Issue 列表

| 序号 | 组件 | 简述 | 严重程度 | 状态 |
|------|------|------|----------|------|
| 001 | AssetMCP | embedding 模型名硬编码 | P0 | 已修复 |
| 002 | Server | jobs/submit 404 | P1 | 待修复 |
```

---

## 14. 开发检查清单

### 14.1 架构纪律检查

- [ ] Agent backend **不直连** Server REST API（所有数据操作走 MCP）
- [ ] Agent backend **不直连** ModelServing（模型调用在 Job 内）
- [ ] `lake_client.py` 封装了所有 MCP 调用
- [ ] Job 内 `lakemind_utils.py` 直连 Server/ModelServing（允许）
- [ ] Job 内**不走 MCP**（MCP 是 Agent 入口）
- [ ] LLM/ASR/Embedding 调用使用 **profile 名**，不硬编码模型名

### 14.2 配置检查

- [ ] MCP token 已在 AssetMCP + DataMCP 的 `config.yaml` 中注册
- [ ] `MCP_TOKEN` 环境变量值与 config.yaml 中的 token 一致
- [ ] `TENANT_ID` 与 MCP token 的 `tenant_id` 一致
- [ ] `.env.example` 包含所有必需环境变量
- [ ] `docker-compose.yml` 使用外部网络 `lakemind_lakemind`

### 14.3 Skill 检查

- [ ] `manifest.yaml` 声明了所有 Job 和 model_profiles
- [ ] 每个 Job 有 `ray.yaml`（entrypoint + dependencies + resources）
- [ ] 每个 Job 有 `main.py`（从 `RAY_JOB_PARAMS` 读参数）
- [ ] `lakemind_utils.py` 包含 S3 读写 + 模型调用工具函数
- [ ] `SKILL.md` 文档完整
- [ ] `publish_skill.py` 上传的版本号与 `lake_client.py` 引用的一致

### 14.4 部署检查

- [ ] `entrypoint.sh` 依次执行：seed_models → publish_skill → start backend
- [ ] `Dockerfile` 包含所有依赖（fastapi, uvicorn, httpx, mcp, ...）
- [ ] `docker-compose.yml` 注入了所有环境变量
- [ ] 容器能通过 `lakemind_lakemind` 网络访问平台服务

### 14.5 验证检查

- [ ] `python scripts/test_mcp.py` — MCP 连通性测试通过
- [ ] `python scripts/seed_models.py` — Profile 全部创建/更新成功
- [ ] `python scripts/publish_skill.py` — Skill 上传+注册成功
- [ ] 端到端流程验证通过（提交 Job → 轮询 → 下载结果 → 知识入库）

