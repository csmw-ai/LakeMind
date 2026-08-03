# 快速入门

本文帮助你从零启动 LakeMind，完成全部验证。

> **预计耗时**：首次约 20-30 分钟（含镜像构建 + 模型下载），后续启动约 2 分钟。

## 前置要求

| 要求 | 最低版本 | 用途 |
|------|----------|------|
| Docker + Docker Compose | Docker 24+ | 运行 12 个容器 |
| Python | 3.12+ | 模型预下载 + 验证脚本 |
| 可用内存 | ≥ 8GB | 含 Ray 集群 |
| 磁盘空间 | ≥ 20GB | 镜像 + 模型 + 数据 |

## 1. 克隆仓库 + 配置

```bash
git clone https://github.com/csmw-ai/LakeMind.git
cd LakeMind
cp .env.example .env
```

编辑 `.env`，填入你的 API Key 和密钥（详见文件内注释）。

## 2. 预下载模型（必须）

LakeMind 禁止运行时下载模型。启动前需预下载 ASR 和 Embedding 模型：

```bash
pip install modelscope fastembed

# ASR 模型（~900MB）
python -c "from modelscope import snapshot_download; snapshot_download('iic/SenseVoiceSmall', local_dir='LakeMindModelServing/data/asr-models/asr/sensevoice-small')"

# VAD 模型（~5MB）
python -c "from modelscope import snapshot_download; snapshot_download('iic/speech_fsmn_vad_zh-cn-16k-common-pytorch', local_dir='LakeMindModelServing/data/asr-models/asr/fsmn-vad')"

# Embedding 模型（~160MB）
python -c "from fastembed import TextEmbedding; m=TextEmbedding(model_name='jinaai/jina-embeddings-v2-base-zh', cache_dir='LakeMindModelServing/data/fastembed_cache'); list(m.embed(['init'])); print('OK')"
```

> 详见 [模型离线下载指南](model-offline-download.md)

## 3. 启动 LakeMind

```bash
# 本地开发（首次需构建镜像）
docker buildx bake core --load
docker compose -f docker-compose.yml -f docker-compose.build.yml --env-file .env --profile ray --profile all up -d --no-build

# 或使用预构建镜像
docker compose --env-file .env --profile ray --profile all up -d
```

## 4. 验证

```bash
curl http://localhost:10823/api/v1/system/health
# 期望：10 个引擎全部 true
```

打开 ControlCenter 管理界面：`http://localhost:3000`（admin 登录）

## 5. 运行 meeting-agent 示例

```bash
cd examples/meeting-agent
cd frontend && npm install && npm run build && cd ..
docker compose up -d --build
# 浏览器打开 http://localhost:9100
```

详见 [示例指南](../examples/README.md)。

## 下一步

- [架构设计](architecture.md) — 理解两层模型、三 MCP、三大引擎
- [MCP 工具](mcp-tools.md) — 68 个 MCP 工具详细说明
- [模型离线下载](model-offline-download.md) — 模型预下载详细步骤
- [部署运维](deployment.md) — 容器管理、引擎切换、故障排查
