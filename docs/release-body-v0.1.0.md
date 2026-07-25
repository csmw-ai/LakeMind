# LakeMind v0.1.0: Agent-Native Cognitive Asset Platform MVP

**Agent 原生的多模态智能数据底座** — 首个可用版本。

## 核心能力

- **统一数据底座**：SeaweedFS + PostgreSQL + Iceberg + LanceDB + Valkey + Ray，一套 API 访问全部数据能力
- **68 个 MCP 工具**：AssetMCP (23) + DataMCP (24) + AdminMCP (21)，Agent 通过 MCP 协议声明式访问认知资产
- **分布式计算**：Ray 2.41 集群（3 节点 12 CPU），Skill 代码包作为 Ray job 一等公民运行
- **统一模型服务**：litellm 网关 + fastembed 嵌入 (jina-zh, dim=768) + FunASR 语音识别
- **认知资产**：mem0 风格记忆（8 方法）、OKF 知识格式、技能管理（只存取不执行）
- **13 个容器**：全部运行，10 引擎全部健康

## 快速开始

```bash
cd LakeMindServer && docker compose --env-file .env --profile ray up -d
cd LakeMindMCP && docker compose --profile all up -d --build
cd LakeMindMonitor && docker compose up -d --build
python scripts/verify_full.py    # 286/286 PASS
```

## 验证结果

| 套件 | 测试数 | 结果 |
|------|--------|------|
| L0-L8 全分层 | 286 | ✅ ALL PASS |
| Ray 分布式 | 12 | ✅ ALL PASS |
| LLM 网关 | 10 | ✅ ALL PASS |
| Monitor | 18 | ✅ ALL PASS |

## 示例

- `examples/meeting-agent/` — 浏览器实时会议知识化 Agent（录音→ASR→摘要→知识萃取→入库→检索），17 分钟实时测试 100% 成功
- `examples/lakemind-connector/` — opencode AI Agent 统一连接器（36 methods: MCP + REST + Ray Jobs + ASR）

## 技术栈

全开源组件（Apache 2.0 / MIT / BSD），不引入闭源依赖。

## 反馈

请在 [GitHub Issues](https://github.com/fdb-data/LakeMind/issues) 报告问题或提出建议。

---

详见 [发布说明](docs/release-notes-v0.1.0.md) | [快速入门](docs/quickstart.md) | [核心概念](docs/glossary.md)
