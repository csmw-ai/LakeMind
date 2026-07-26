# opencode-lakemind-connector

> opencode（AI Agent）通过 **Skill** 接入 LakeMind 的 Demo。
>
> Agent 将"如何连接 LakeMind"封装为一个 Skill，注册到 LakeMind 平台。运行时 Agent 检索 Skill 代码并在自身进程中执行，存取自身的知识和记忆。

---

## 1. 设计思路

```
                    LakeMind 平台 (store/retrieve，不执行)
                    ┌─────────────────────────────────────┐
                    │  S3: skill zip                      │
                    │  LanceDB: skill 向量 (可检索发现)    │
                    │  AssetMCP: 记忆存取                  │
                    │  ModelServing: Embedding / LLM      │
                    └─────────────────────────────────────┘
                         ▲                          │
    ① register_skill     │                          │ ② search_skill
                         │                          ▼
    Agent (opencode)     │    ③ get_skill (下载代码)
    ┌─────────────────┐  │         │
    │                 │──┘         │
    │  ④ 执行 Skill   │◄───────────┘
    │     代码        │
    │                 │── ⑤ 通过 MCP 存取认知资产 ──→ LakeMind
    └─────────────────┘
```

1. **register_skill** — 打包 Skill zip → 上传 S3 → 向量化 SKILL.md → 存入 LanceDB
2. **search_skill** — Agent 用语义搜索发现 Skill（"我需要连接 LakeMind"）
3. **get_skill** — 下载 Skill 代码 zip
4. **Agent 执行** — 在自身进程中 import connector.py，LakeMind 不执行
5. **存取认知** — Skill 代码通过 MCP/REST 存取知识、记忆

> **LakeMind 是存取平台，不是执行平台。** `execute_skill` 已移除，Agent 自行检索技能代码并在自身运行时执行。

---

## 2. Skill 包结构

```
skills/lakemind-connector/
├── SKILL.md          ← Skill 文档 (frontmatter + 说明，供检索发现)
├── connector.py      ← LakeMindConnector — MCP + REST 统一封装
├── cognition.py       ← 知识概念 + 记忆消息定义
└── cli.py             ← CLI 入口 (Agent 执行的入口)
```

### connector.py — LakeMindConnector

| 方法 | 来源 | 说明 |
|------|------|------|
| `store_knowledge(kb, concepts)` | ModelServing + Server | 向量化 + 向量入库（`/add` 追加） |
| `search_knowledge(query, kb)` | ModelServing + Server | 语义检索 |
| `scan_knowledge(kb)` | Server REST | 浏览全部概念 |
| `add_memory(messages)` | AssetMCP MCP | 存入记忆 |
| `search_memory(query)` | AssetMCP MCP | 搜索记忆 |
| `list_memory()` | AssetMCP MCP | 列出记忆 |
| `embed(text)` | ModelServing | 文本向量化 |
| `llm_chat(sys, user)` | ModelServing | LLM 对话 |
| `asr(audio)` | ModelServing | FunASR 语音识别 |
| `clean_asr_text(text)` | — | 清理 FunASR 输出标签 (static) |
| `s3_put/get/list()` | Server REST | S3 对象存储 (bucket+key) |
| `s3_put_uri/get_uri/exists_uri()` | Server REST | S3 URI-based (`s3://bucket/key`) |
| `submit_job(skill_uri, job_name, params)` | Server REST | 提交 Ray job |
| `poll_job(job_id, interval, timeout)` | Server REST | 轮询 job 直到终态 |
| `submit_and_wait(skill_uri, job_name, params)` | Server REST | 一步提交+等待 |
| `get_job_status/get_job_result/cancel_job/list_jobs()` | Server REST | Ray job 管理 |
| `pack_skill(skill_dir)` | — | 打包 Skill zip (static) |
| `upload_skill(skill_dir, name)` | Server REST | 打包+上传 Skill 到 S3 |
| `check_health()` | Server + MS + MCP | 统一健康检查（含 Ray distributed） |
| `create_tenant()` | AdminMCP MCP | 创建租户 |
| `issue_token()` | AdminMCP MCP | 签发 Token |

---

## 3. 项目结构

```
examples/lakemind-connector/
├── README.md
├── pyproject.toml
├── .env.example
├── skills/
│   └── lakemind-connector/     ← Skill 包（可打包上传到 LakeMind）
│       ├── SKILL.md
│       ├── connector.py
│       ├── cognition.py
│       └── cli.py
└── scripts/
    ├── setup_tenant.py          ← 创建 opencode 租户 + 签发 Token
    └── register_skill.py        ← 打包 Skill + 上传 S3 + 向量注册
```

---

## 4. 快速开始

```bash
cd examples/lakemind-connector

# 设置环境变量（见 .env.example）
export ASSET_MCP_URL=http://localhost:8401/mcp
export ADMIN_MCP_URL=http://localhost:8403/mcp
export SERVER_API_URL=http://localhost:10823
export SERVER_API_KEY=lakemind-internal-api-key
export MODEL_SERVING_URL=http://localhost:10824
export MODELSERVING_API_KEY=lakemind-modelserving-key
export OPENCODE_TOKEN=tk_9d377e74c0c14969
export ADMIN_TOKEN=test-steward-token
export TENANT_ID=opencode

# Step 1: 创建租户（一次性）
python scripts/setup_tenant.py

# Step 2: 注册 Skill 到 LakeMind（一次性）
python scripts/register_skill.py
# → Skill zip 上传到 S3
# → SKILL.md 向量化存入 LanceDB
# → 其他 Agent 可通过 search_skill("lakemind connector") 发现本 Skill

# Step 3: Agent 运行 Skill（每次使用）
cd skills/lakemind-connector
python cli.py ingest                  # 入库知识 + 记忆
python cli.py search "MCP protocol"   # 语义检索
python cli.py scan                    # 浏览全部概念
python cli.py memories                # 列出记忆
python cli.py remember "今天修复了bug" # 存入新记忆
python cli.py search-memory "验证"    # 语义搜索记忆
python cli.py verify                  # 验证入库结果
python cli.py tools                   # 列出 MCP 工具
python cli.py health                  # 平台健康检查 (含 Ray distributed)
python cli.py jobs                    # 列出 Ray jobs
python cli.py jobs running            # 筛选 running 状态
python cli.py job-status <job_id>     # 查询 job 状态
python cli.py asr <audio.wav>         # ASR 语音识别
```

---

## 5. Agent 使用 Skill 的代码示例

```python
# Agent 检索并使用 Skill（伪代码）

# ① 搜索发现 Skill
hits = await lake.search_skill("lakemind connector")

# ② 下载 Skill 代码
zip_bytes = await lake.get_skill("lakemind-connector")

# ③ 解压并 import
extract(zip_bytes, "/tmp/lakemind-connector")
sys.path.insert(0, "/tmp/lakemind-connector")
from connector import LakeMindConnector
from cognition import KNOWLEDGE_BASE, KNOWLEDGE_CONCEPTS

# ④ 使用 Skill 存取认知
conn = LakeMindConnector()
await conn.store_knowledge(KNOWLEDGE_BASE, concepts)   # 存知识
hits = await conn.search_knowledge("query", KNOWLEDGE_BASE)  # 检索知识
await conn.add_memory([{"role": "user", "content": "新记忆"}])  # 存记忆

# ⑤ 提交 Ray job（分布式计算）
job = await conn.submit_job(
    skill_uri="lake://skills/my-skill",
    job_name="process",
    params={"input_uri": "s3://bucket/data/input.json", "result_uri": "s3://bucket/data/result.json"},
)
status = await conn.poll_job(job["job_id"])  # 等待完成
result = await conn.s3_get_uri("s3://bucket/data/result.json")  # 下载结果
```

---

## 6. 已存入的认知资产

### 知识（9 个概念，kb_opencode-self）

| 类型 | 内容 |
|------|------|
| agent_identity | opencode 身份与能力 |
| platform_architecture | LakeMind 三平面架构 |
| technical_knowledge | MCP 协议、FunASR、LanceDB、MediaRecorder、Monitor |
| project_knowledge | meeting-agent 架构与设计决策 |
| infrastructure_fix | Server 修复记录 |

### 记忆（5 条，AssetMCP）

1. 构建 meeting-agent 示例
2. 调试 ASR 502 问题
3. 修复 Monitor 显示空白
4. 创建 opencode 租户
5. 端到端验证状态

---

## 7. E2E 验证结果

`python cli.py verify` 全部通过：

- **知识检索**：5 queries × top-1 命中正确概念（distance 0.53~1.06）
- **记忆检索**：4 queries × 均返回相关记忆（score 0.35~0.67，cosine metric）
- **知识库状态**：`kb_opencode-self`，9 concepts
- **记忆总数**：5 条

### 修复记录

| 问题 | 根因 | 修复 |
|------|------|------|
| `search_memory` 返回空 | LanceDB 默认 L2 距离 >1.0，score=1.0-dist=0，低于 threshold | `basic.py` search() 改用 `.metric("cosine")` |
| `list_memory` 显示空内容 | MCP 返回字段名为 `memory` 而非 `content` | CLI 读取 `memory` 字段 |

---

## 8. 设计说明

### 为什么是 Skill 而不是库

LakeMind 的设计原则：**平台只存取不执行**。Skill 是可检索、可复用的能力包：
- Agent A 注册 Skill → LakeMind 存储
- Agent B 搜索发现 Skill → 下载 → 在自身运行时执行
- 多 Agent 共享同一 Skill，无需重复开发

### 为什么知识入库绕过 AssetMCP

AssetMCP `ingest_knowledge` 依赖 Server embedding 端点（未 mount，404）。直接用 ModelServing embeddings + Server vector API。

### 租户隔离

opencode 使用独立租户 `opencode`，与 `retail`（meeting-agent）和 `platform`（Monitor）隔离。
