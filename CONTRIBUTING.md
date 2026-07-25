# 贡献指南

感谢你对 LakeMind 的关注！本文档说明如何参与项目开发。

---

## 1. 报告 Bug

1. 在 [GitHub Issues](https://github.com/anomalyco/LakeMind/issues) 搜索是否已有相同问题。
2. 如果没有，点击 **New Issue** → 选择 **Bug Report** 模板。
3. 填写模板中的各项信息，特别是**复现步骤**和**环境信息**。
4. 维护者会在 `needs-triage` 标签移除时确认优先级。

### Bug 优先级定义

| 优先级 | 含义 | 响应时间 |
|--------|------|----------|
| **P0** | 崩溃 / 数据丢失 / 核心功能完全不可用 | 24h 内确认 |
| **P1** | 功能异常，有变通方法 | 3 天内确认 |
| **P2** | 体验问题（文档错误、日志不清晰、性能低） | 1 周内确认 |

---

## 2. 提出新功能

1. 在 [GitHub Issues](https://github.com/anomalyco/LakeMind/issues) 点击 **New Issue** → 选择 **Feature Request** 模板。
2. 描述使用场景和动机，说明为什么现有功能无法满足。
3. 如果可能，描述你期望的实现方式。

---

## 3. 提交代码

### 3.1 开发环境

- Python 3.12+
- Docker + Docker Compose
- 可用内存 ≥ 8GB（含 Ray 集群）
- 磁盘空间 ≥ 20GB

### 3.2 工作流

```
1. Fork 仓库
2. git checkout -b fix/your-bug-description
3. 编写代码 + 测试
4. python scripts/verify_full.py    # 确保全部通过
5. git commit -m "fix: 简要描述"
6. git push origin fix/your-bug-description
7. 在 GitHub 创建 Pull Request
```

### 3.3 提交信息约定

| 前缀 | 用途 |
|------|------|
| `fix:` | Bug 修复 |
| `feat:` | 新功能 |
| `refactor:` | 重构 |
| `docs:` | 文档 |
| `chore:` | 构建 / 配置 / 杂项 |

### 3.4 代码约定

- **不加注释**，除非逻辑非显而易见。
- **代码标识符用英文**，**设计文档用中文**。
- **不引入闭源依赖**（仅 Apache 2.0 / MIT / BSD）。
- **版本号保持统一**：所有 `pyproject.toml` 的 `version` 字段一致。
- PowerShell 下读写中文文件名需设置 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`。

### 3.5 PR 审查

- 维护者会在 3 个工作日内开始审查。
- PR 必须通过 `verify_full.py` 全部测试。
- 审查通过后合并到 `main` 分支。

---

## 4. Bug 修复流程

```
Issue 报告 → 维护者确认 + 分配优先级 → 开发者认领 → 创建分支 → 修复 + 测试 → PR → 审查 → 合并 → 关闭 Issue
```

1. **报告**：用户通过 Issue 模板提交 Bug。
2. **确认**：维护者复现问题，移除 `needs-triage` 标签，分配优先级和 `bug` 标签。
3. **修复**：开发者认领 Issue，创建分支 `fix/issue-{编号}-描述`。
4. **测试**：修复后运行 `python scripts/verify_full.py`，确保全部通过。如有必要，新增测试用例。
5. **PR**：提交 Pull Request，关联 Issue（`Closes #{编号}`）。
6. **审查**：维护者审查代码质量和测试覆盖。
7. **合并**：审查通过后合并到 `main`。
8. **关闭**：Issue 自动关闭。

---

## 5. 项目结构

详见 [AGENTS.md](AGENTS.md) 第 2 节"仓库包结构"。

关键目录：

| 目录 | 职责 |
|------|------|
| `LakeMindServer/` | 数据平面（REST API + 10 引擎 + 13 容器） |
| `LakeMindModelServing/` | 统一模型服务（litellm + fastembed + SenseVoice funasr） |
| `LakeMindMCP/` | 3 个 MCP 服务 |
| `LakeMindSteward/` | 管理运维 Agent |
| `LakeMindMonitor/` | 人类仪表板 |
| `examples/` | 示例 Agent |
| `docs/` | 发布文档 |
| `scripts/` | 验证脚本 |

---

## 6. 反馈渠道

- **Bug / 功能请求**：[GitHub Issues](https://github.com/anomalyco/LakeMind/issues)
- **代码贡献**：Pull Request
- **讨论**：[GitHub Discussions](https://github.com/anomalyco/LakeMind/discussions)（如有）
