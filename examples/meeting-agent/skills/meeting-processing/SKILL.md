# 会议录音实时知识化

实时录音 → ASR 转写 → 会议纪要 → 知识萃取 → 知识库入库。

## Jobs

每个 job 是独立的 Ray 任务，代码在 `jobs/{name}/main.py`，通过 `ray.yaml` 声明 entrypoint。

- **asr** (`jobs/asr/`): 音频 chunk → 转写文本（调用 Ray Serve ASR）
- **summarize** (`jobs/summarize/`): 转写文本 → 结构化纪要（调用 ModelServing LLM）
- **extract** (`jobs/extract/`): 纪要 → 知识点 + 入库（调用 ModelServing LLM + Server REST API）

## 共享工具

- `lakemind_utils.py`: S3 存取、LLM 对话、ASR

## 模型服务

- ASR: Ray Serve deployment `asr-app`（`serve.get_deployment_handle("asr", "asr-app")`）
- LLM: `profile="meeting-minutes"` / `profile="meeting-knowledge-extract"` → ModelServing /v1/chat/completions
- Embedding: 由 Server 内部 AssetMCP 直接调用 Ray Serve `embedding-app`，示例不直接调用

## 运行方式

Agent 通过 Server REST API `/api/v1/compute/jobs/submit` 提交 Ray job，
参数通过 `RAY_JOB_PARAMS` 环境变量注入，结果写入 S3。
