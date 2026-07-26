# Meeting Agent 实用化升级方案

> **状态**: 待批准
> **原则**: 不改变 example 性质，不破坏 web→agent→skill→job→LakeMind 开发架构

---

## 1. 租户问题

### 结论：不支持 2 级租户 `examples/meeting-agent`

LakeMind 0.1.0 的 `tenant_id` 是 PostgreSQL `TEXT PRIMARY KEY`，API 层**无校验**——任何字符串都能存进去。但 `/` 在以下存储面**会断裂**：

| 存储面 | `examples/meeting-agent` 的后果 |
|--------|------|
| Iceberg namespace `{tenant}_data` | `examples/meeting-agent_data` — pyiceberg 标识符不允许 `/`，**建表直接报错** |
| LanceDB 路径 `/data/lance/tenant_examples/meeting-agent` | 产生意外嵌套目录，db 名歧义 |
| S3 路径 | 可用但解析歧义 |

### 方案：使用扁平租户 `examples-meeting-agent`

- 仅含 `[a-z0-9-]`，全部存储面安全
- Agent 启动时自动创建租户（`POST /api/v1/metadata/tenants`，幂等）
- `.env.example` 中 `TENANT_ID=examples-meeting-agent`

---

## 2. 任务管理表设计

### 存储选型：Iceberg 结构化表

用户要求"建一个表来管理"，LakeMind 的结构化数据路径就是 Iceberg。

- **Namespace**: `examples-meeting-agent_data`（遵循 DataMCP `{tenant}_data` 约定）
- **Table**: `meeting_tasks`
- **创建方式**: Agent 启动时通过 `POST /api/v1/storage/tables/` 创建（幂等，已存在则跳过）

### Schema

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | string | 任务 ID（`meeting-{YYYYMMDD-HHMMSS}-{hex6}`） |
| `title` | string | 会议标题 |
| `participants` | string | 参会人 |
| `status` | string | `recording` / `stopped` / `completed` |
| `chunk_count` | int64 | 音频片段数 |
| `summary_count` | int64 | 纪要生成次数 |
| `extract_count` | int64 | 知识抽取次数 |
| `started_at` | string | 开始时间 ISO8601 |
| `stopped_at` | string | 结束时间 ISO8601（可空） |
| `transcript_uri` | string | transcript.json 的 S3 URI |
| `minutes_uri` | string | minutes.md 的 S3 URI |
| `kb_name` | string | 知识库名（固定 `meetings`） |
| `duration` | int64 | 会议时长秒 |
| `created_at` | string | 记录创建时间 ISO8601 |
| `updated_at` | string | 记录更新时间 ISO8601 |

> 时间戳用 `string`（ISO8601）而非 `timestamp` 类型——避免 Iceberg 类型转换边界问题，example 够用。

### 写入策略：append-only + 读时去重

Iceberg API 只有 `append` / `overwrite`，没有行级 `UPDATE`。采用 **append-only**：

- 每次状态变更 → append 一行新记录（同 `id`，不同 `updated_at`）
- 查询时 scan 全表 → 按 `id` 分组 → 取 `updated_at` 最大的一行
- 天然审计日志，无需 read-modify-write

对于 example 规模（几十到几百条任务），全表 scan + Python 去重完全够用。

---

## 3. Web UI 改造

### 视图结构（3 个视图，vanilla JS 切换）

```
首页（任务展廊）
  ├── [新建会议转录] 按钮 → 录音视图
  ├── 任务卡片网格
  │     └── 每张卡片: 标题 / 状态徽章 / 片段数 / 时间 / [查看] 按钮
  └── [知识检索] 按钮 → 搜索视图

录音视图（新建任务）
  ├── 会议标题 / 参会人 输入
  ├── 录音按钮 / 状态 / 计时器
  └── 实时转写 / 实时纪要 / 已发现知识（SSE，同现有）
  └── [停止] → 回到首页

任务详情视图（查看历史任务）
  ├── 标题 / 参会人 / 状态 / 时长 / 片段数
  ├── 转写全文（从 S3 加载 transcript.json）
  ├── 会议纪要（从 S3 加载 minutes.md）
  └── 知识条目（从 LanceDB 搜索 meeting_id 匹配的 concepts）
  └── [返回] → 首页

搜索视图（知识检索，保持不变）
```

### 交互流程

```
用户打开应用
  → GET /api/tasks → 返回任务列表（从 Iceberg scan + 去重）
  → 渲染任务卡片网格

用户点"新建会议转录"
  → 显示录音视图
  → POST /api/start {title, participants} → 返回 meeting_id
  → 录音、发送 chunk、SSE 实时更新（同现有逻辑）
  → POST /api/stop → 更新任务状态 → 回到首页

用户点任务卡片"查看"
  → GET /api/tasks/{id} → 返回任务详情 + transcript + minutes
  → 显示任务详情视图（只读）
```

---

## 4. Agent 层改造

### 新增 `TaskManager` 类（在 `agent.py` 内或单独 `task_manager.py`）

```python
class TaskManager:
    """通过 Iceberg 表管理会议任务的生命周期"""

    async def init(self):
        """创建租户 + 创建 meeting_tasks 表（幂等）"""

    async def create_task(self, id, title, participants) -> dict:
        """插入初始行，status=recording"""

    async def update_task(self, id, **fields) -> dict:
        """append 一行新记录，只更新传入的字段"""

    async def list_tasks(self) -> list[dict]:
        """scan 全表 → 按 id 去重 → 按 started_at 倒序"""

    async def get_task(self, id) -> dict | None:
        """scan → 按 id 去重 → 取指定 id"""

    async def get_task_detail(self, id) -> dict | None:
        """get_task + 从 S3 加载 transcript.json + minutes.md"""
```

### `MeetingAgent` 改造

| 方法 | 现有行为 | 改造后 |
|------|---------|--------|
| `__init__` | `self.meetings = {}` | `self.tasks = TaskManager(...)` |
| `start_meeting` | 写内存 dict | `tasks.create_task(id, title, participants)` |
| `on_chunk` | 更新内存计数 | `tasks.update_task(id, chunk_count=N)` |
| `_summarize` | 更新内存计数 | `tasks.update_task(id, summary_count=N, minutes_uri=uri)` |
| `_extract` | 更新内存计数 | `tasks.update_task(id, extract_count=N)` |
| `stop_meeting` | 写内存 + add_memory | `tasks.update_task(id, status="stopped", ...)` + add_memory |
| `list_meetings` | 读内存 dict | `tasks.list_tasks()` |
| —（新增）— | — | `get_task_detail(id)` 供详情页加载 |

### `lakemind_client.py` 新增方法

```python
# 租户管理
async def ensure_tenant(self, tenant_id, name)

# Iceberg 表管理
async def create_table(self, namespace, table, schema)
async def table_exists(self, namespace, table) -> bool
async def append_rows(self, namespace, table, rows)
async def scan_table(self, namespace, table, limit=1000) -> list[dict]
```

### 新增 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tasks` | 任务列表（替换 `/api/history`） |
| GET | `/api/tasks/{task_id}` | 任务详情（transcript + minutes + knowledge） |

`/api/history` 保留但标记 deprecated，内部转发到 `/api/tasks`。

---

## 5. 不变的部分

| 层 | 文件 | 变化 |
|----|------|------|
| Skill | `skills/meeting-processing/SKILL.md` | **不变** |
| Skill | `skills/meeting-processing/lakemind_utils.py` | **不变** |
| Job | `jobs/asr/main.py` | **不变** |
| Job | `jobs/summarize/main.py` | **不变** |
| Job | `jobs/extract/main.py` | **不变** |
| Setup | `scripts/setup.py` | **不变**（仍打包上传 skill） |
| Client | `lakemind_client.py` 的 S3/Ray/Memory 方法 | **不变**（只新增 Iceberg 方法） |

---

## 6. 数据流（改造后）

```
浏览器
  │
  ├─ GET /api/tasks ──→ Agent ──→ Iceberg scan + 去重 ──→ 任务卡片列表
  │
  ├─ POST /api/start ──→ Agent ──→ Iceberg append (status=recording)
  │
  ├─ POST /api/chunk ──→ Agent
  │     ├─ ffmpeg → S3 PUT wav
  │     ├─ Ray job (asr) → poll → S3 GET → SSE broadcast
  │     └─ Iceberg append (chunk_count++)
  │
  ├─ [每6 chunks] Ray job (summarize) → poll → SSE broadcast
  │     └─ Iceberg append (summary_count++, minutes_uri)
  │
  ├─ [每2 summaries] Ray job (extract) → poll → LanceDB add → SSE broadcast
  │     └─ Iceberg append (extract_count++)
  │
  ├─ POST /api/stop ──→ Agent
  │     ├─ final summarize
  │     ├─ AssetMCP add_memory
  │     └─ Iceberg append (status=stopped, stopped_at, duration)
  │
  └─ GET /api/tasks/{id} ──→ Agent
        ├─ Iceberg scan → 任务元信息
        ├─ S3 GET transcript.json → 转写全文
        ├─ S3 GET minutes.md → 会议纪要
        └─ LanceDB search (meeting_id filter) → 知识条目
```

---

## 7. S3 路径约定（不变）

```
s3://lakemind-filesets/examples-meeting-agent/
  ├── skills/meeting-processing.zip
  └── meetings/{meeting_id}/
        ├── audio/chunk-001.wav, chunk-002.wav, ...
        ├── transcript.json
        ├── minutes.md
        └── results/asr-001.json, summarize-001.json, extract-001.json, ...
```

---

## 8. 改动文件清单

| 文件 | 操作 | 改动量 |
|------|------|--------|
| `agent.py` | 改造 | 大 — 新增 TaskManager，MeetingAgent 改用 TaskManager |
| `lakemind_client.py` | 增量 | 中 — 新增 ensure_tenant / create_table / append_rows / scan_table |
| `static/index.html` | 改造 | 中 — 新增任务展廊视图 + 任务详情视图 |
| `static/app.js` | 改造 | 大 — 新增展廊/详情交互逻辑 |
| `static/style.css` | 增量 | 小 — 新增卡片/徽章样式 |
| `.env.example` | 改 | 小 — TENANT_ID 改为 examples-meeting-agent |
| `README.md` | 改 | 小 — 更新使用说明 |
| `DESIGN.md` | 改 | 小 — 更新架构说明 |

**不新增文件**（TaskManager 放在 `agent.py` 内，保持 example 简洁）。

---

## 9. 启动时初始化流程

```
Agent 启动
  ├─ LakeMindClient() 初始化
  ├─ TaskManager.init()
  │    ├─ ensure_tenant("examples-meeting-agent", "Meeting Agent Example")
  │    └─ create_table("examples-meeting-agent_data", "meeting_tasks", schema)  # 幂等
  ├─ MeetingAgent(client, task_manager)
  └─ FastAPI 启动，监听 :9100
```

---

## 10. 风险与对策

| 风险 | 对策 |
|------|------|
| Iceberg 表创建失败（引擎未就绪） | 启动时 retry 3 次，失败则 warn 但不阻塞（降级为内存模式） |
| Iceberg scan 慢（任务多） | example 规模 <1000 条，scan + Python 去重 <100ms |
| append-only 导致表膨胀 | example 场景可接受；生产可加 compaction |
| 浏览器录音权限 | 不变，现有逻辑已处理 |
| 旧租户 `retail` 的数据 | 不迁移，新租户从零开始 |
