# LakeMind 示例

本目录包含 LakeMind 平台能力验证与 Agent 接入示例。

## 示例总览

| 目录 | 说明 | 验证能力 | 状态 |
|------|------|----------|------|
| `meeting-agent/` | 会议实时知识化 Agent | 录音→ASR→纪要→知识 全链路 | ✅ v0.2.1 验证通过 |
| `lakemind-connector/` | opencode Skill 接入 LakeMind | Skill 注册/检索/执行 + 认知资产存取 | ✅ 已验证 |

---

## 前置条件：启动 LakeMind 平台

运行任何示例前，需先启动 LakeMind 全栈（12 容器）。

### 1. 克隆仓库 + 配置环境

```bash
git clone https://github.com/csmw-ai/LakeMind.git
cd LakeMind
cp .env.example .env
```

编辑 `.env`，填入你的 API Key：

```bash
# 必填项
MAAS_API_KEY=<your-llm-api-key>          # LLM provider API key（如华为云 ModelArts）
LAKEMIND_MASTER_KEY=<base64-32-bytes>     # openssl rand -base64 32
SERVER_API_KEY=<your-server-api-key>      # 自定义，用于 Server API 认证
```

### 2. 预下载模型（离线模式，必须执行）

LakeMind 禁止运行时下载模型。启动前需预下载 ASR 和 Embedding 模型：

```bash
# 创建模型目录
mkdir -p LakeMindModelServing/data/asr-models/asr
mkdir -p LakeMindModelServing/data/fastembed_cache

# 下载 SenseVoice ASR 模型（约 900MB）
pip install modelscope
python -c "
from modelscope import snapshot_download
snapshot_download('iic/SenseVoiceSmall', local_dir='LakeMindModelServing/data/asr-models/asr/sensevoice-small')
"

# 下载 fsmn-vad 语音活动检测模型（约 5MB）
python -c "
from modelscope import snapshot_download
snapshot_download('iic/speech_fsmn_vad_zh-cn-16k-common-pytorch', local_dir='LakeMindModelServing/data/asr-models/asr/fsmn-vad')
"

# 下载 fastembed 嵌入模型（约 160MB，首次启动时自动缓存到此目录）
# 方法：运行一次 fastembed 的 Python 调用
pip install fastembed
python -c "
from fastembed import TextEmbedding
model = TextEmbedding(model_name='jinaai/jina-embeddings-v2-base-zh', cache_dir='LakeMindModelServing/data/fastembed_cache')
list(model.embed(['初始化模型缓存']))
print('Embedding model cached.')
"
```

> 详见 [模型离线下载指南](../docs/model-offline-download.md)

### 3. 启动 LakeMind 全栈

```bash
# 本地开发（首次需构建镜像）
docker buildx bake core --load
docker compose -f docker-compose.yml -f docker-compose.build.yml --env-file .env --profile ray --profile all up -d --no-build

# 或使用预构建镜像（正式部署）
docker compose --env-file .env --profile ray --profile all up -d
```

验证平台健康：

```bash
curl http://localhost:10823/api/v1/system/health
# 期望：10 个引擎全部 true
```

打开 ControlCenter 管理界面：`http://localhost:3000`

---

## meeting-agent：会议实时知识化

浏览器实时录音 → ASR 转写 → LLM 纪要 → 知识萃取 → 向量入库，全链路走 LakeMind MCP + Ray Serve。

### 架构

```
浏览器 (React frontend)
  │  MediaRecorder 每 20s 生成 WebM chunk
  │  PUT /api/tasks/{id}/audio/chunks/{n}
  ▼
Agent Backend (FastAPI :9100)
  │  通过 MCP 编排：S3 上传 → Ray Job 提交/轮询 → SSE 推送
  │  S3/Ray → DataMCP(:8402)  知识/记忆 → AssetMCP(:8401)
  ▼
Ray Serve (asr-app + embedding-app)
  │  ASR: SenseVoice funasr (CPU)
  │  Embedding: fastembed jina-v2-base-zh (CPU)
  ▼
LakeMindServer (:10823)
  │  JobService 受控执行 + 知识/记忆入库
  ▼
LakeMindModelServing (:10824)
  │  litellm LLM 网关（纪要生成 + 知识萃取）
```

### 快速开始（Docker 部署，推荐）

```bash
cd examples/meeting-agent

# 1. 构建前端（必须先执行）
cd frontend && npm install && npm run build && cd ..

# 2. 启动 meeting-agent 容器
docker compose up -d --build

# 3. 等待初始化完成（约 30s：seed models + publish skill）
docker logs -f meeting-agent
# 看到 "Application startup complete." 即可

# 4. 浏览器打开 http://localhost:9100
#    注册/登录 → 新建会议 → 点击录音 → 开始说话
```

### 快速开始（本地运行，开发调试用）

```bash
cd examples/meeting-agent

# 安装依赖
pip install -e .

# 设置环境变量
export SERVER_API_URL=http://localhost:10823
export SERVER_API_KEY=<your-server-api-key>
export MODEL_SERVING_URL=http://localhost:10824
export MODELSERVING_API_KEY=lakemind-modelserving-key
export ASSET_MCP_URL=http://localhost:8401/mcp
export DATA_MCP_URL=http://localhost:8402/mcp
export MCP_TOKEN=meeting-agent-mcp-token
export TENANT_ID=examples-meeting-agent

# 注册 LLM profile + 发布 Skill
python scripts/seed_models.py
python scripts/publish_skill.py

# 启动后端
cd backend && uvicorn app.main:app --port 9100
```

### 验证的 LakeMind 能力

| 能力 | 体现 |
|------|------|
| 对象存储 (SeaweedFS) | 音频分片、纪要、Job 结果存取 |
| Ray 分布式计算 | ASR/纪要/知识萃取通过 Ray Job 执行 |
| Ray Serve | ASR + Embedding 推理服务（asr-app + embedding-app） |
| Skill 包管理 | 打包上传 + manifest.yaml 声明 + Job Runtime 执行 |
| ASR (SenseVoice) | Ray Serve: 音频 → 转写文本（自带标点 + ITN） |
| LLM (litellm) | Ray Job: 转写 → 结构化纪要 + 知识萃取 |
| Embedding (fastembed) | Ray Serve: 知识向量化 |
| 向量存储 (LanceDB) | 知识入库 + 相似度搜索 |
| 记忆 (AssetMCP) | 会议结束记录 |

### 实测数据（v0.2.1 持续监控）

15 分钟持续录音：48 分片、47 ASR 成功、7 版纪要、33 条知识、零失败。

详见 [pipeline 监控报告](../reports/2026.0802.v0.2.1-pipeline监控报告.md)。

---

## lakemind-connector：Skill 接入示例

Agent 将"如何连接 LakeMind"封装为 Skill 注册到平台，运行时检索 Skill 代码并在自身进程中执行，存取知识和记忆。

```
① register_skill  → 打包上传 S3 + 向量化 SKILL.md
② search_skill    → Agent 语义搜索发现 Skill
③ get_skill       → 下载 Skill 代码
④ Agent 执行      → 在自身进程中 import connector.py
⑤ 存取认知        → 通过 MCP 存取知识、记忆
```

> **LakeMind 是存取平台，不是执行平台。** Agent 自行检索技能代码并执行。

详见 [lakemind-connector/README.md](lakemind-connector/README.md)。

---

## 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| 分片上传 502 | MCP 连接失败 | 检查 DataMCP 容器健康：`docker ps` 含 `lakemind-data-mcp` |
| ASR Job FAILED | 模型未预下载 | 执行模型预下载步骤（见上方第 2 步） |
| ASR 结果为空 | 音频静音或格式错误 | 确认浏览器麦克风权限，检查 ffmpeg 可用 |
| 纪要不生成 | LLM API Key 无效 | 检查 `.env` 中 `MAAS_API_KEY`，在 ControlCenter 测试模型连通性 |
| meeting-agent 启动卡住 | 依赖服务未就绪 | 确认 LakeMind 全栈健康后再启动 meeting-agent |
| `mcp` import 错误 | mcp 包版本不匹配 | 确认 `mcp>=2.0,<3`（`pip show mcp`） |
