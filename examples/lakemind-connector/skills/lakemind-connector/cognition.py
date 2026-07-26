"""
opencode 自认知数据 — 知识概念和记忆消息定义。

将 opencode 对自身的认知、对 LakeMind 平台的认知、以及对工作过程的认知
结构化为可入库的知识概念和记忆消息。
"""

from __future__ import annotations

KNOWLEDGE_BASE = "opencode-self"

KNOWLEDGE_CONCEPTS = [
    {
        "title": "opencode AI Agent 身份与能力",
        "body": (
            "opencode 是一个交互式 CLI AI 编码助手，由 GLM-5.2 模型驱动。"
            "核心能力：代码生成、调试、重构、架构设计、Docker 运维、Git 操作、"
            "多语言开发（Python/TypeScript/Go/Rust等）。"
            "运行环境：Windows PowerShell + opencode CLI。"
            "设计原则：简洁直接、最小输出、遵循项目约定。"
        ),
        "type": "agent_identity",
        "tags": ["opencode", "ai-agent", "glm-5.2", "cli"],
    },
    {
        "title": "LakeMind 平台架构认知",
        "body": (
            "LakeMind 是认知资产存取平台（store/retrieve），不是 Agent 执行平台。"
            "三平面架构：数据平面(LakeMindServer:10823) + 模型平面(LakeMindModelServing:10824) + 运行平面(3 MCP)。"
            "10 引擎：SeaweedFS(S3) + PostgreSQL(元数据) + Iceberg(表) + LanceDB(向量) + "
            "Valkey(KV) + DuckDB(即席SQL) + Ray(分布式计算) + fastembed(嵌入) + litellm(LLM网关) + FunASR(语音识别)。"
            "3 MCP：AssetMCP(:8401,23tools) + DataMCP(:8402,18tools) + AdminMCP(:8403,17tools)。"
            "MCP 是 Agent 唯一入口，嵌入式引擎在 Server 进程中运行。"
        ),
        "type": "platform_architecture",
        "tags": ["lakemind", "architecture", "mcp", "three-plane"],
    },
    {
        "title": "LakeMind MCP 协议接入方法",
        "body": (
            "MCP 使用 Streamable HTTP 传输，端点格式: http://host:port/mcp。"
            "认证: Authorization: Bearer <token>。"
            "必需 Header: Accept: application/json, text/event-stream。"
            "Python SDK: from mcp.client.streamable_http import streamablehttp_client; from mcp import ClientSession。"
            "流程: streamablehttp_client(url, headers) -> ClientSession(read, write) -> session.initialize() -> session.call_tool(name, arguments)。"
            "Token 配置在 AssetMCP config/config.yaml 的 tokens 列表，映射 token->tenant_id。"
        ),
        "type": "technical_knowledge",
        "tags": ["mcp", "protocol", "python-sdk", "authentication"],
    },
    {
        "title": "FunASR SenseVoice 语音识别输出格式",
        "body": (
            "FunASR SenseVoice-Small 模型输出包含特殊标签：<|zh|> <|en|> <|EMO_UNKNOWN|> <|NEUTRAL|> <|Speech|> <|Cough|> <|woitn|>。"
            "标签格式: < | tag | >（含空格）。"
            "清理方法: 正则 <\\s*\\|[^|]*\\|\\s*> 替换为空，然后 \\s+ 压缩为单空格。"
            "ModelServing 端点: POST /v1/audio/transcriptions，参数 file(audio.wav) + model(sensevoice-small)。"
            "容器内 ffmpeg 对部分 WebM 不稳定，需 host ffmpeg 预转换 WebM->WAV(16kHz mono)。"
        ),
        "type": "technical_knowledge",
        "tags": ["funasr", "asr", "sensevoice", "ffmpeg", "webm"],
    },
    {
        "title": "LanceDB 向量存储操作模式",
        "body": (
            "LanceDB 向量表命名: kb_{knowledge_base_name}，数据库命名: tenant_{tenant_id}。"
            "describe() 返回 {name, row_count, concept_count, schema}。"
            "scan() 方法返回全部行（to_arrow().to_pylist()），用于浏览无需向量的数据。"
            "search() 需要 query_vec + top_k，返回带 _distance 的结果。"
            "create_table mode: overwrite(重建) | append(追加)。"
            "首次入库可能 500（表不存在），retry with overwrite 即可。"
            "Embedding 模型: jina-embeddings-v2-base-zh, dim=768, 由 ModelServing /v1/embeddings 提供。"
        ),
        "type": "technical_knowledge",
        "tags": ["lancedb", "vector", "embedding", "jina", "search"],
    },
    {
        "title": "浏览器 MediaRecorder 多分片录音最佳实践",
        "body": (
            "问题: MediaRecorder timeslice 产生无 EBML 头的 WebM 分段，ffmpeg 无法解析。"
            "解决: per-chunk restart — 每 10s stop() 当前 recorder，onstop 收集完整 WebM blob，立即 new MediaRecorder 开始下一段。"
            "每个 chunk 是完整 WebM 文件（有合法 EBML 头）。"
            "替代方案 ScriptProcessorNode 生成 WAV 不可靠：后续 chunk 数据损坏。"
            "发送: fetch POST /api/chunk, body=webmBlob (binary, 非 multipart)。"
            "Agent 侧用 host ffmpeg 转 WAV 再发 ModelServing ASR。"
        ),
        "type": "technical_knowledge",
        "tags": ["mediarecorder", "webm", "browser", "audio", "chunking"],
    },
    {
        "title": "LakeMind Monitor 资产页面数据流",
        "body": (
            "Monitor 前端 Asset.vue -> GET /api/asset/knowledge -> Monitor server.js -> "
            "MCP resources/read(lake://knowledge) -> AssetMCP server.py -> ServerClient.vector_list/describe -> "
            "Server REST /api/v1/storage/vectors/{db}。"
            "KB 详情: lake://knowledge/{id} -> vector_describe + vector_scan -> 返回 {name, concept_count, concepts[]}。"
            "前端表格列: name, concept_count, type_distribution, created_at。"
            "Token 决定租户: test-business-token->retail, test-monitor-token->platform。"
        ),
        "type": "technical_knowledge",
        "tags": ["monitor", "asset-page", "data-flow", "frontend"],
    },
    {
        "title": "meeting-agent 示例架构与设计决策",
        "body": (
            "examples/meeting-agent/ 是 LakeMind 平台能力验证 Demo（非生产级）。"
            "流水线: 浏览器录音(WebM) -> Agent(ffmpeg转WAV) -> ModelServing(ASR) -> 清理FunASR标签 -> "
            "每6chunk LLM摘要 -> 每2摘要 LLM萃取知识 -> Embedding向量化 -> 向量入库 -> 检索自检。"
            "关键决策: (1)直接调ModelServing而非Ray jobs(Server Ray提交有连接问题); "
            "(2)host ffmpeg转WAV(容器ffmpeg不稳定); (3)MediaRecorder per-chunk restart; "
            "(4)知识入库绕过AssetMCP(Server embedding endpoint未mount); (5)FunASR标签正则清理。"
            "验收日志: [OK]/[FAIL] 标记每个环节。"
        ),
        "type": "project_knowledge",
        "tags": ["meeting-agent", "example", "demo", "architecture", "decisions"],
    },
    {
        "title": "LakeMind Server 基础设施修复记录",
        "body": (
            "修复1: PostgreSQL 缺少 tenant_secrets 表和 ray_jobs 表，手动创建。"
            "修复2: ray_compute.py 缺少 from ray.job_submission import JobSubmissionClient 导入。"
            "修复3: ModelServing 容器缺少 ffmpeg，安装后 ASR 才能处理音频。"
            "修复4: Ray worker 容器缺少 httpx，pip install 后才能调 ModelServing。"
            "修复5: lancedb.py describe() 缺少 concept_count 字段，Monitor 前端显示空白。"
            "修复6: AssetMCP describe_knowledge 资源只返回元信息不返回概念行，新增 vector_scan 端点。"
        ),
        "type": "infrastructure_fix",
        "tags": ["server", "fix", "postgresql", "ray", "ffmpeg", "lancedb"],
    },
]

MEMORY_MESSAGES = [
    {
        "role": "user",
        "content": (
            "我和用户一起构建了 examples/meeting-agent/ — 一个浏览器实时会议知识化 Agent。"
            "从设计到实现到调试，经历了多轮迭代。"
            "最终架构: 浏览器 MediaRecorder -> Agent(FastAPI) -> ModelServing(ASR/LLM) + Server REST(S3/向量) + AssetMCP(记忆)。"
            "验证通过: 12 chunk ASR 全成功, 3 次摘要, 1 次知识萃取, 检索自检通过。"
        ),
    },
    {
        "role": "user",
        "content": (
            "调试浏览器录音 ASR 502 问题的完整过程: "
            "第1次尝试 ScriptProcessorNode 生成 WAV — 首个 chunk 成功，后续全部 502(ffmpeg Invalid data)。"
            "第2次尝试 MediaRecorder timeslice — 产生无 EBML 头的 WebM 分段。"
            "第3次尝试 MediaRecorder per-chunk restart + host ffmpeg 转换 — 全部成功。"
            "根因: ScriptProcessorNode 后续 chunk 数据损坏; MediaRecorder timeslice 分段不完整。"
            "解决: 每个 chunk 独立 MediaRecorder 生成完整 WebM + host ffmpeg 转 WAV。"
        ),
    },
    {
        "role": "user",
        "content": (
            "修复 LakeMind Monitor 资产页面显示空白问题: "
            "根因1: lancedb.describe() 返回 row_count 但前端期望 concept_count。"
            "根因2: lake://knowledge/{id} 资源只返回表元信息不返回概念行。"
            "根因3: describe_knowledge 无条件拼 kb_ 前缀导致 kb_kb_meetings。"
            "修复: describe() 增加 concept_count; 新增 vector_scan 方法和 REST 端点; "
            "describe_knowledge 返回实际概念行; 判断 id.startswith(kb_) 避免重复前缀。"
            "通过 docker cp 直接修改容器内 site-packages 文件并重启。"
        ),
    },
    {
        "role": "user",
        "content": (
            "通过 LakeMind AdminMCP 创建了 opencode 租户(tenant_id=opencode)，"
            "签发了 Token(tk_9d377e74c0c14969)，"
            "在 AssetMCP config.yaml 中注册了 Token->tenant 映射。"
            "然后通过 AssetMCP 将自己的知识(9个概念)和记忆(4条)存入 LakeMind。"
            "这是 opencode 首次将自身认知资产存入外部平台。"
        ),
    },
]
