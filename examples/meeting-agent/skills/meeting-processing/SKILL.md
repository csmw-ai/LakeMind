# 会议录音实时知识化

实时录音 → ASR 转写 → 会议纪要 → 知识萃取 → 知识库入库。

## Jobs

每个 job 是独立的 Ray 任务，代码在 `jobs/{name}/main.py`，通过 `ray.yaml` 声明 entrypoint。

- **asr** (`jobs/asr/`): 音频 chunk → 转写文本（调用 ModelServing FunASR）
- **summarize** (`jobs/summarize/`): 转写文本 → 结构化纪要（调用 ModelServing LLM）
- **extract** (`jobs/extract/`): 纪要 → 知识点 + 入库（调用 ModelServing LLM + embed + Server REST API）

## 共享工具

- `lakemind_utils.py`: S3 存取、LLM 对话、ASR、嵌入、知识入库

## 模型服务

所有 LLM / ASR / Embedding 调用通过 LakeMindModelServing (:10824)，使用 **profile 名** 路由（管理员可在 ControlCenter UI 动态切换模型，无需改代码）：

- ASR: `profile="meeting-asr"` → /v1/audio/transcriptions
- LLM: `profile="meeting-minutes"` / `profile="meeting-knowledge-extract"` → /v1/chat/completions
- Embedding: `profile="meeting-embedding"` → /v1/embeddings

## 运行方式

Agent 通过 Server REST API `/api/v1/compute/jobs/submit` 提交 Ray job，
参数通过 `RAY_JOB_PARAMS` 环境变量注入，结果写入 S3。
