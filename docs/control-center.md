# Control Center 使用指南

> **适用版本**：v0.2.0+
> **访问地址**：`http://<host>:3000`
> **角色**：平台管理员 / 运维人员 / 租户管理员

Control Center 是 LakeMind 的统一管理入口，集监控、配置、运维、对话于一体。本文介绍它的页面结构、典型使用流程，并重点讲解**模型配置与发布**——如何把一个新模型接入 LakeMind 并对 Agent 可用。

---

## 1. Control Center 是什么

Control Center 是一个单容器（`lakemind-control-center`），内部由三部分组成：

```
lakemind-control-center (:3000)
├── nginx            → 静态前端 + 反代 /api → BFF
├── BFF  (:3001)     → 会话鉴权、转发到 LakeMindServer REST API (:10823)
└── Steward (:3002)  → LangGraph 运维 Agent，对话式巡检
```

它**不直连任何底层引擎**，全部操作通过 LakeMindServer 的 REST API 完成。这意味着 Control Center 上看到的所有数据（任务、模型、资产、指标）都是平台真实状态，没有第二份元数据。

### 与其他平面的关系

| 平面 | 入口 | 谁用 |
|------|------|------|
| 数据平面 `:10823` | REST API | MCP / BFF / 脚本 |
| 模型平面 `:10824` | REST API | Server 内部调用 |
| 运行平面 3 MCP | MCP 协议 | 业务 Agent |
| **Control Center `:3000`** | Web UI | **人类管理员** |

业务 Agent 永远走 MCP，不进 Control Center；管理员永远进 Control Center，不直连 MCP。

---

## 2. 登录与权限

### 2.1 首次登录

打开 `http://localhost:3000`，使用平台初始化时创建的管理员账号：

| 字段 | 默认值 |
|------|--------|
| 用户名 | `admin` |
| 租户 | `ten_default` |
| 角色 | `platform_admin` |

登录后 BFF 会建立会话 cookie，后续所有请求自动携带 `Authorization` 和 `X-Tenant-Id` 头。

### 2.2 能力驱动的菜单

左侧导航菜单由当前用户的能力（capabilities）动态渲染。`platform_admin` 拥有 `*` 通配能力，可见全部 10 个页面；租户管理员只能看到授权范围内的页面。无权限的路由会被 `RouteGuard` 拦截并重定向。

| 菜单 | 路由 | 所需能力 | 用途 |
|------|------|----------|------|
| Mission Control | `/mission-control` | `obs:view` | 全局健康仪表板 |
| Organization | `/organization` | `tenant:view` | 租户 / 用户 / Token |
| Assets | `/assets` | `asset:view` | 知识 / 记忆 / 技能资产 |
| Jobs | `/jobs` | `job:view` | Ray 任务列表与状态 |
| **Models** | `/models` | `model:view` | **模型定义与部署** |
| Services | `/services` | `obs:view` | 服务实例与健康 |
| Configuration | `/configuration` | `config:view` | 引擎配置 |
| Security | `/security` | `operation:view` | 密钥 / 凭据 |
| Operations | `/operations` | `operation:view` | 运维操作 |
| Audit | `/audit` | `audit:view` | 审计日志 |
| Steward | `/steward` | `steward:chat` | 与运维 Agent 对话 |

---

## 3. 监控：Mission Control

`/mission-control` 是首页，一张仪表板回答"系统现在健康吗"。

### 3.1 指标卡

每张卡显示当前值 + 采样时间 + 新鲜度标记（`stale` / `partial`）：

| 卡片 | 含义 | 数据来源 |
|------|------|----------|
| Pending Approvals | 待审批操作数 | `pending_approvals` |
| Failed Jobs | 失败任务数（近 24h） | `ray_jobs` 表 |
| Degraded Assets | 降级资产数 | 资产健康检查 |
| Unhealthy Deployments | 不健康部署数 | `model_deployments.health_status` |
| Service Health | 在线服务 / 总服务 | `service_instances` |
| CPU Usage | 集群 CPU 利用率 | `metrics_series`（30s 采样） |
| Memory Usage | 集群内存利用率 | `metrics_series` |
| Storage Usage | SeaweedFS 磁盘占用 | `metrics_series` |
| Job Queue Depth | Ray 任务队列深度 | `metrics_series` |
| Recent Changes | 近 1h 配置变更数 | `audit_log` |
| Outbox Backlog | 事件外发积压 | `event_outbox` |

点击任意卡片跳转到对应详情页。

### 3.2 新鲜度规则

- **stale**：采样时间距现在 > 5 分钟（红色标签）
- **partial**：该指标部分采集失败（橙色标签），值仍是有效的部分结果

如果整张仪表板都 stale，说明 `monitoring_service` 后台采集线程停了，去 `/services` 看 `lakemind-server-api` 是否健康。

---

## 4. 模型配置与发布（重点）

`/models` 页面是管理员最常用的页面之一。LakeMind 的模型管理采用**两层模型**：

```
Model Definition（逻辑层）         Deployment（物理层）
┌──────────────────────┐          ┌──────────────────────────┐
│ name: deepseek-v4    │ 1 ──── N │ provider: openai         │
│ type: chat           │          │ endpoint: http://...:10824│
│ provider_family:openai│         │ secret_ref: secret://...  │
│ context_length: 64000│          │ priority: 1              │
│ capabilities:[chat]  │          │ status: enabled          │
└──────────────────────┘          └──────────────────────────┘
```

- **Definition** 回答"这是什么模型"：类型、provider 家族、上下文长度、嵌入维度。
- **Deployment** 回答"它部署在哪、怎么调用"：endpoint URL、API 密钥引用、优先级、启停状态。
- 一个 Definition 可以有**多个 Deployment**（同一模型多 endpoint 高可用 / 多 provider 路由）。
- Agent 调用时，ModelServing 网关按 `priority` 升序选择 `status=enabled` 且 `health_status=healthy` 的 Deployment。

### 4.1 三个 Tab

| Tab | 内容 | 操作 |
|-----|------|------|
| Model Definitions | 全部模型定义 | 新增 / 编辑 |
| Deployments | 全部部署实例 | 新增 / 编辑 / Enable / Disable / **Test** |
| Profiles & Routes | 路由策略 + Profile→Deployment 映射 | 新增 Profile / 新增 Route / 删除 Route |

### 4.2 Deployment 检测（Test）

每个 Deployment 行有 **Test** 按钮，点击后系统向该 endpoint 发送一个探测请求：

| 模型类型 | 探测方式 |
|----------|----------|
| chat | `POST {endpoint}` `{"model":name, "messages":[{"role":"user","content":"hi"}], "max_tokens":1}` |
| embedding | `POST {endpoint}` `{"model":name, "input":["test"]}` |
| asr | `GET {base_url}/health` |

检测结果弹窗显示：成功/失败、HTTP 状态码、延迟（ms）、错误信息、响应预览。同时自动更新 Deployment 的 `health_status`（`healthy` / `unhealthy`）。

**用途**：新增 Deployment 后立即验证是否可达；排查容器间网络问题（`localhost` endpoint 在容器内不可达会显示 `Connection refused`）。

### 4.2 发布一个新模型：完整流程

以"接入 OpenAI `gpt-4o-mini` 作为新的 chat 模型"为例。

#### 步骤 1：在 ModelServing 网关配置 provider

模型真正能被调用，前提是 `LakeMindModelServing/config/models.yaml` 里声明了对应 provider。编辑文件：

```yaml
llm_providers:
  - name: "modelarts"
    type: "openai"
    base_url: "https://api.modelarts-maas.com/openai/v1"
    api_key: "${MAAS_API_KEY}"
    models:
      - id: "deepseek-v4-flash"
        litellm_model: "openai/deepseek-v4-flash"
        context: 64000
        tags: [chat]
    priority: 1
  # ↓ 新增 OpenAI provider
  - name: "openai"
    type: "openai"
    api_key: "${OPENAI_API_KEY}"
    models:
      - id: "gpt-4o-mini"
        litellm_model: "openai/gpt-4o-mini"
        context: 128000
        tags: [chat]
    priority: 2
```

重启模型平面：

```bash
docker restart lakemind-model-serving
```

> **设计原则**：LakeMind 禁止运行时动态下载模型。所有 provider/模型必须在部署前配置好，运行时只读配置。本地模型（如 faster-whisper）需提前把权重放到 `/models/asr/` 持久化路径。

#### 步骤 2：在 Control Center 注册 Model Definition

打开 `http://localhost:3000/models` → **Model Definitions** Tab → **Add Definition**：

| 字段 | 填写 | 说明 |
|------|------|------|
| Name | `gpt-4o-mini` | 显示名 |
| Type | `chat` | chat / completion / embedding / asr |
| Provider Family | `openai` | provider 家族，用于路由分组 |
| Capabilities | `chat, vision` | 逗号分隔的能力标签 |
| Context Length | `128000` | 最大上下文 token 数 |
| Embedding Dim | （留空） | 仅 embedding 类型填 |
| Metadata | `{"litellm_model": "openai/gpt-4o-mini"}` | 透传给 litellm 的模型 ID |

保存后系统生成 `mdl_xxx`，此时 Definition 已存在但**还没有 Deployment，不可调用**。

#### 步骤 3：创建 Deployment

切到 **Deployments** Tab → **Add Deployment**：

| 字段 | 填写 | 说明 |
|------|------|------|
| Model ID | 选择 `gpt-4o-mini (chat)` | 关联到上一步的 Definition |
| Provider | `openai` | 实际 provider 名（对应 models.yaml 里的 `name`） |
| Endpoint | `http://lakemind-model-serving:10824/v1/chat/completions` | ModelServing 网关地址 |
| Secret Ref | `secret://default/openai-api-key` | 引用 Security 页面存的密钥 |
| Priority | `2` | 数字越小优先级越高 |
| Timeout (ms) | `120000` | 单次请求超时 |
| Max Concurrency | `10` | 并发上限 |

保存后 Deployment 状态默认 `enabled`，ModelServing 健康检查会把它标为 `healthy`。

#### 步骤 4：（可选）配置 Profile 路由

**Profiles & Routes** Tab 可以定义"用途 → 模型"的路由策略：

1. **Add Profile** — 创建一个命名的路由策略（如 `meeting-asr`、`meeting-minutes`）
2. **Add Route** — 把 Profile 映射到一个 Deployment，设置 priority 和是否 fallback

例如 meeting-agent 的路由配置：

| Profile | Deployment | 说明 |
|---------|------------|------|
| `meeting-asr` | whisper-large-v3-turbo @ lakemind-model-serving | 会议转写 ASR |
| `meeting-minutes` | deepseek-v4-flash @ lakemind-model-serving | 纪要生成 LLM |
| `meeting-knowledge-extract` | deepseek-v4-flash @ lakemind-model-serving | 知识萃取 LLM |
| `meeting-embedding` | jina-embeddings-v2-base-zh @ lakemind-model-serving | 知识嵌入 |
| `default` | 全部 pri=1 部署 | 平台默认路由 |

Agent 调用模型时传 profile 名，网关查 `model_routes` 表找到对应 Deployment。Routes 表可以删除重新映射。

#### 步骤 5：验证

在 Mission Control 看 `Unhealthy Deployments` 卡片应为 0。也可以直接 curl 验证：

```bash
curl -X POST http://localhost:10824/v1/chat/completions \
  -H "Authorization: Bearer lakemind-modelserving-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}'
```

返回正常即发布成功，业务 Agent 通过 AssetMCP 调用 `llm_chat` 时即可选到该模型。

### 4.3 修改现有模型

点表格行的 **Edit** 按钮即可修改。Definition 和 Deployment 都支持编辑：

- **改 Definition**：调整 context_length、capabilities、metadata 等逻辑属性。
- **改 Deployment**：切换 endpoint、调整 priority、改 secret_ref。修改 `status` 字段等价于 Enable/Disable。

> 编辑走 `PATCH` 方法，只更新提交的字段，未提交字段保持不变。

### 4.4 启停与下线

| 操作 | 做法 | 效果 |
|------|------|------|
| 临时停用 | Deployments → Disable | 网关不再路由到该部署，但配置保留 |
| 重新启用 | Deployments → Enable | 恢复路由 |
| 彻底下线 | 先 Disable，再 Delete（API） | 从数据库删除，不可恢复 |

下线前确认没有 Profile 把它设为默认或唯一 fallback，否则 Agent 调用会失败。

### 4.5 当前已注册模型（参考）

| Definition | Type | Provider Family | 用途 |
|------------|------|-----------------|------|
| `deepseek-v4-flash` | chat | openai | 默认 LLM（ModelArts MaaS） |
| `jinaai/jina-embeddings-v2-base-zh` | embedding | fastembed | 默认嵌入（768 维） |
| `jina-embeddings-v2-base-zh` | embedding | fastembed | 嵌入备选 |
| `Systran/faster-whisper-small` | asr | faster-whisper | 语音识别（faster-whisper） |
| `whisper-large-v3-turbo` | asr | faster-whisper | 语音识别（faster-whisper） |

### 4.6 接入本地模型（Ollama 示例）

本地模型遵循同一套流程，只是 endpoint 指向本地：

1. `models.yaml` 加 ollama provider（`base_url: http://host.docker.internal:11434`）。
2. Control Center 加 Definition：name=`qwen2.5:7b`, type=`chat`, provider_family=`ollama`, context_length=`32768`。
3. 加 Deployment：endpoint=`http://lakemind-model-serving:10824/v1/chat/completions`, priority 设高一些（降级用）。
4. Profile 里把它加到 fallback 链末尾。

> 本地模型权重必须提前 `ollama pull` 到宿主机，LakeMind 运行时不触发下载。

---

## 5. 其他监控页面速览

### 5.1 Services `/services`

列出 8 个已注册服务实例及健康状态：

| 服务 | 端口 | 健康检查 |
|------|------|----------|
| lakemind-server-api | 10823 | `/system/health` |
| lakemind-model-serving | 10824 | `/health` |
| asset-mcp / data-mcp / admin-mcp | 8401/8402/8403 | MCP ping |
| steward / monitor / control-center | 3002/3000 | HTTP |

服务通过 `POST /api/v1/instances` 自注册，`PUT /api/v1/instances/{id}/heartbeat` 定期心跳。心跳超时则标 `unhealthy`。

### 5.2 Jobs `/jobs`

Ray 任务列表，显示任务 ID、状态（PENDING/RUNNING/SUCCEEDED/FAILED）、提交时间、skill_ref。`platform_admin` 可看跨租户全部任务。

### 5.3 Assets `/assets`

认知资产浏览：知识库、记忆、技能、本体。只读视图，编辑走 Studio 或 MCP。

### 5.4 Organization `/organization`

租户、用户、Token 管理。新建租户会自动初始化默认角色和能力集。

### 5.5 Configuration `/configuration`

引擎配置（`engines.yaml`）的只读视图，展示当前 10 个引擎的插件和参数。修改需编辑配置文件并重启 Server。

### 5.6 Security `/security`

密钥与凭据管理。Deployment 的 `secret_ref` 指向这里存储的密钥。支持 `secret://<scope>/<name>` 引用语法。

### 5.7 Steward `/steward`

与 Steward 运维 Agent 对话窗口。可以自然语言问"现在系统健康吗"、"最近有失败的任务吗"，Steward 通过 AdminMCP + DataMCP 查询并回答。

---

## 6. 常见问题

### Q1：Models 页面显示空？

确认登录用户有 `model:view` 能力。`platform_admin` 有 `*` 通配能力，租户用户需在 Organization 页面授权。

### Q2：新增 Deployment 后 health 一直是 `unknown`？

ModelServing 健康检查周期约 30s，稍等片刻会刷新。若长期 `unhealthy`，检查：
- endpoint 是否从 ModelServing 容器可达（容器内网络）
- secret_ref 指向的密钥是否存在且有效
- `models.yaml` 是否声明了对应 provider

### Q3：编辑后前端没刷新？

硬刷新浏览器（Ctrl+Shift+R）。前端缓存策略较激进，PATCH 成功后会自动 reload 数据，但偶尔需要手动刷新。

### Q4：能不能不重启 ModelServing 就加模型？

不能。`models.yaml` 是启动时加载的静态配置，新增 provider 必须重启 `lakemind-model-serving`。Definition/Deployment 的增删改则不需要重启，Control Center 操作即时生效。

### Q5：本地模型权重放哪？

| 模型类型 | 路径 | 配置项 |
|----------|------|--------|
| ASR (faster-whisper) | `/models/asr/<model>/` | `asr.built_in.model_path` |
| Embedding (fastembed) | `/data/fastembed_cache/` | `embedding.built_in.cache_dir` |
| Ollama LLM | 宿主机 `~/.ollama/models/` | ollama 自管理 |

所有路径在 `docker-compose.yml` 里通过 volume 挂载到容器，运行时不下载。

---

## 7. 相关文档

- [架构设计](architecture.md) — 三平面分层、MCP 职责
- [配置参考](configuration.md) — `engines.yaml` 完整字段
- [API 参考](api-reference.md) — REST API 路径
- [MCP 工具](mcp-tools.md) — 3 MCP 的 tools/resources/prompts
- `LakeMindModelServing/DESIGN.md` — 模型平面设计细节
