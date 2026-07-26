# LakeMind 示例

本目录包含 LakeMind 平台能力验证与 Agent 接入示例。

## 示例总览

| 目录 | 说明 | 验证能力 | 状态 |
|------|------|----------|------|
| `meeting-agent/` | 会议实时知识化 Agent | web→agent→skill→job 全链路 | ✅ 已验证 |
| `lakemind-connector/` | opencode Skill 接入 LakeMind | Skill 注册/检索/执行 + 认知资产存取 | ✅ 已验证 |


---

## meeting-agent

**目标**：验证 LakeMind 的 web→agent→skill→job 层次划分和核心能力链路。

浏览器实时录音 → Agent 编排 → Ray job 执行 ASR/摘要/萃取 → 知识入库 → 语义检索。

### 架构

```
Web (static/)           录音 UI + SSE
  ▼
Agent (agent.py)        编排：S3 上传 → Ray job 提交/轮询 → S3 下载 → SSE 推送
  │                     不直接调用 ModelServing
  ▼
Skill (skills/)         可复用业务包：SKILL.md + lakemind_utils.py
  │
  └─ Job (jobs/{name}/)  Ray job：asr / summarize / extract
                         每个 job 自包含，通过 ray.yaml 声明 entrypoint
```

### 验证的 LakeMind 能力

| 能力 | 体现 |
|------|------|
| 对象存储 (SeaweedFS) | 音频/纪要/job 结果存取 |
| Ray 分布式计算 | ASR/摘要/萃取全部通过 Ray job 执行 |
| Skill 包管理 | 打包上传 + ray.yaml 声明 + RAY_JOB_PARAMS 注入 |
| ASR (FunASR) | Ray job: WAV → 转写文本 |
| LLM (litellm) | Ray job: 转写 → 纪要 + 知识萃取 |
| Embedding (fastembed) | Ray job: 知识向量化 + 入库 |
| 向量存储 (LanceDB) | 知识入库 (/add 追加) + 相似度搜索 |
| 记忆 (AssetMCP) | 会议结束记录 |

### 实测数据

17 分钟实时测试：145 chunks、100+ Ray jobs、100% 成功率、3 节点 12 CPU。

### 快速开始

```bash
cd examples/meeting-agent
python scripts/setup.py    # 打包 Skill + 健康检查 + 上传 S3
python agent.py            # 启动 Agent
# 浏览器打开 http://localhost:9100
```

详见 [meeting-agent/README.md](meeting-agent/README.md)。

---

## lakemind-connector

**目标**：验证 Agent 通过 Skill 接入 LakeMind 的存取模式。

Agent 将"如何连接 LakeMind"封装为 Skill 注册到平台，运行时检索 Skill 代码并在自身进程中执行，存取知识和记忆。

### 流程

```
① register_skill  → 打包上传 S3 + 向量化 SKILL.md
② search_skill    → Agent 语义搜索发现 Skill
③ get_skill       → 下载 Skill 代码
④ Agent 执行      → 在自身进程中 import connector.py
⑤ 存取认知        → 通过 MCP/REST 存取知识、记忆
```

> **LakeMind 是存取平台，不是执行平台。** Agent 自行检索技能代码并执行。

详见 [lakemind-connector/README.md](lakemind-connector/README.md)。

---

## 前置条件

LakeMind 全栈已启动（13 容器）：

```bash
cd LakeMindServer && docker compose --env-file .env --profile ray up -d
cd LakeMindMCP && docker compose --profile all up -d
cd LakeMindMonitor && docker compose up -d
```

验证：`python scripts/verify_full.py`（L0-L8 286/286 PASS）。
