# LakeMind v0.2.0 Provider 契约定义

> 日期：2026-07-13  
> 状态：accepted  
> 依据：[设计方案](../../../reports/v0.2.0-design/LakeMind_v0.2.0_设计方案.md) §12.8 + v0.1.0 `protocols.py`

---

## 1. 概述

v0.1.0 的 `plugins/protocols.py` 包含 11 个 `typing.Protocol`。v0.2.0 正式化为 10 个 Provider 契约。

### 1.1 变化总表

| Provider | v0.1.0 Protocol | v0.2.0 变化 | 用途 |
|----------|-----------------|-------------|------|
| ObjectStorageProvider | `ObjectStoragePlugin` | 保留，增加 `protected_prefix` 校验 | S3/SeaweedFS |
| TableStorageProvider | `TabularStoragePlugin` | 保留 | Iceberg |
| VectorIndexProvider | `VectorStoragePlugin` | 保留，增加 `embedding_space_id` 参数 | Lance/LanceDB |
| GraphProjectionProvider | `GraphStoragePlugin` | 保留，标记 Experimental | PG Graph |
| CacheProvider | `KVStoragePlugin` | 保留 | Valkey |
| ExecutionBackend | `DistributedComputePlugin` | **重命名 + 简化**：5 方法 | Ray |
| ModelProvider | `EmbeddingPlugin` + `LLMPlugin` | **合并**：chat/embed/asr/list_models/health | ModelServing |
| AuthorizationProvider | 无（新增） | 新增 | PG 驱动 |
| SecretProvider | 无（新增） | 新增 | PG 加密 |
| ConfigurationProvider | 无（新增） | 新增 | PG 驱动 |

> **注意**：v0.1.0 的 `MetadataStorePlugin` 和 `MemoryPlugin` 不作为独立 Provider，其能力由 Control Plane Service 层 + 上述 Provider 组合实现。`SQLComputePlugin` 归入 `TableStorageProvider` 的即席计算能力。

---

## 2. Provider 契约定义

### 2.1 ObjectStorageProvider

```python
class ObjectStorageProvider(Protocol):
    def put(self, bucket: str, key: str, body: bytes) -> None: ...
    def get(self, bucket: str, key: str) -> bytes: ...
    def delete(self, bucket: str, key: str) -> None: ...
    def exists(self, bucket: str, key: str) -> bool: ...
    def list(self, bucket: str, prefix: str = "", limit: int = 1000) -> list[str]: ...
    def ensure_bucket(self, bucket: str) -> None: ...
    def health(self) -> bool: ...
    # v0.2.0 新增
    def check_protected(self, key: str) -> bool:
        """检查 key 是否在 Protected Namespace 内（ten_*/ast_*）"""
        ...
```

### 2.2 TableStorageProvider

```python
class TableStorageProvider(Protocol):
    def create_table(self, namespace: str, table: str, schema: pa.Schema, location: str | None = None) -> str: ...
    def table_exists(self, namespace: str, table: str) -> bool: ...
    def list_tables(self, namespace: str) -> list[str]: ...
    def list_namespaces(self) -> list[str]: ...
    def ensure_namespace(self, namespace: str) -> None: ...
    def append(self, namespace: str, table: str, data: pa.Table) -> int: ...
    def overwrite(self, namespace: str, table: str, data: pa.Table) -> int: ...
    def scan(self, namespace: str, table: str, columns: list[str] | None = None, filter: str | None = None, limit: int | None = None) -> pa.Table: ...
    def describe(self, namespace: str, table: str) -> dict: ...
    def drop_table(self, namespace: str, table: str) -> None: ...
    def execute_sql(self, sql: str, tables: dict[str, pa.Table] | None = None) -> list[dict]: ...
    def health(self) -> bool: ...
```

### 2.3 VectorIndexProvider

```python
class VectorIndexProvider(Protocol):
    def create_table(self, db: str, name: str, data: pa.Table, mode: str = "overwrite") -> None: ...
    def table_exists(self, db: str, name: str) -> bool: ...
    def list_tables(self, db: str) -> list[str]: ...
    def add(self, db: str, name: str, data: pa.Table) -> int: ...
    def search(self, db: str, name: str, query_vec: list[float], top_k: int = 5, filter: str | None = None, embedding_space_id: str | None = None) -> list[dict]: ...
    def count_rows(self, db: str, name: str) -> int: ...
    def describe(self, db: str, name: str) -> dict: ...
    def health(self) -> bool: ...
```

### 2.4 GraphProjectionProvider（Experimental）

```python
class GraphProjectionProvider(Protocol):
    def add_node(self, graph: str, node_id: str, label: str, properties: dict, tenant_id: str) -> None: ...
    def add_edge(self, graph: str, edge_id: str, src: str, dst: str, rel: str, properties: dict, tenant_id: str) -> None: ...
    def query_nodes(self, graph: str, tenant_id: str, label: str | None = None) -> list[dict]: ...
    def query_edges(self, graph: str, src: str, tenant_id: str) -> list[dict]: ...
    def delete_node(self, graph: str, node_id: str, tenant_id: str) -> None: ...
    def health(self) -> bool: ...
```

### 2.5 CacheProvider

```python
class CacheProvider(Protocol):
    def get(self, db: int, key: str) -> str | None: ...
    def set(self, db: int, key: str, value: str, ttl: int | None = None) -> None: ...
    def delete(self, db: int, key: str) -> bool: ...
    def scan(self, db: int, pattern: str = "*", limit: int = 1000) -> list[str]: ...
    def health(self) -> bool: ...
```

### 2.6 ExecutionBackend

```python
class ExecutionBackend(Protocol):
    """v0.2.0 简化：从 7 方法简化为 5 方法。
    submit_skill_job 和 get_job_status 合并到 JobService 层。"""
    def submit(self, entrypoint: str, params: dict, env_vars: dict, resources: dict, job_id: str) -> str: ...
    def cancel(self, job_id: str) -> dict: ...
    def get_status(self, job_id: str) -> dict: ...
    def get_logs(self, job_id: str) -> str: ...
    def get_result(self, job_id: str) -> Any: ...
```

### 2.7 ModelProvider

```python
class ModelProvider(Protocol):
    """v0.2.0 合并 EmbeddingPlugin + LLMPlugin。
    由 LakeMindModelServing 统一实现。"""
    def chat(self, messages: list[dict], model: str = "", temperature: float = 0.7, max_tokens: int = 0, **kwargs) -> dict: ...
    def embed(self, texts: list[str], model: str = "") -> list[list[float]]: ...
    def asr(self, audio_path: str, language: str = "zh", **kwargs) -> dict: ...
    def list_models(self) -> list[dict]: ...
    def health(self) -> bool: ...
```

### 2.8 AuthorizationProvider（新增）

```python
class AuthorizationProvider(Protocol):
    def authenticate(self, token: str) -> dict | None: ...
    def authorize(self, principal_id: str, action: str, resource: str) -> bool: ...
    def check_tenant(self, principal_id: str, tenant_id: str) -> bool: ...
```

### 2.9 SecretProvider（新增）

```python
class SecretProvider(Protocol):
    def create(self, scope: str, name: str, value: str) -> str: ...
    def get_ref(self, scope: str, name: str) -> str: ...
    def resolve(self, ref: str, requester_id: str) -> str: ...
    def rotate(self, scope: str, name: str) -> str: ...
    def list(self, scope: str | None = None) -> list[dict]: ...
    def log_usage(self, ref: str, requester: str, purpose: str) -> None: ...
```

### 2.10 ConfigurationProvider（新增）

```python
class ConfigurationProvider(Protocol):
    def get(self, scope: str, key: str) -> dict: ...
    def set(self, scope: str, key: str, value: Any, reason: str) -> str: ...
    def get_revision(self, revision_id: str) -> dict: ...
    def activate(self, revision_id: str) -> str: ...
    def rollback(self, revision_id: str) -> str: ...
    def get_effective(self, scope: str) -> dict: ...
```

---

## 3. 关键改造

### 3.1 ExecutionBackend 简化

v0.1.0 的 `DistributedComputePlugin` 有 7 个方法：
- `submit(func, args)` — 通用提交
- `status(job_id)` — 状态查询
- `result(job_id)` — 结果获取
- `submit_skill_job(skill_zip, job_name, env_vars, resources, job_id)` — Skill 提交
- `get_job_status(ray_job_id)` — Ray 原始状态
- `cancel_job(ray_job_id)` — 取消
- `health()` — 健康

v0.2.0 简化为 5 个标准方法：
- `submit(entrypoint, params, env_vars, resources, job_id)` — 统一提交
- `cancel(job_id)` — 取消
- `get_status(job_id)` — 状态
- `get_logs(job_id)` — 日志
- `get_result(job_id)` — 结果

`submit_skill_job` 和 `get_job_status` 合并到 JobService 层，ExecutionBackend 不感知 Skill 概念。

### 3.2 ModelProvider 合并

v0.1.0 有两个独立 Plugin：
- `EmbeddingPlugin` — 仅 fastembed 实现
- `LLMPlugin` — 无注册实现（vestigial）

v0.2.0 合并为 `ModelProvider`，由 LakeMindModelServing 统一实现：
- `chat()` — LLM 对话（litellm 路由）
- `embed()` — 嵌入（fastembed）
- `asr()` — 语音识别（faster-whisper, faster-whisper-small）
- `list_models()` — 模型列表
- `health()` — 健康检查

### 3.3 新增 3 个 Provider

| Provider | 对应 Service | 实现方式 |
|----------|-------------|----------|
| AuthorizationProvider | AuthorizationService | PG 驱动（users / tokens / roles 表） |
| SecretProvider | SecretService | PG 加密存储（tenant_secrets 表 + AES-GCM） |
| ConfigurationProvider | ConfigurationService | PG 驱动（config_revisions 表） |

---

## 4. Provider 契约不外泄规则

- API 响应中不出现 `s3_key` / `lance_uri` / `ray_job_id` / `iceberg_namespace` 等物理标识
- Provider 接口方法签名使用逻辑参数（`asset_id` / `binding_id`），物理路径由 Service 层解析
- Provider 实现细节（SeaweedFS endpoint / Lance DB path / Ray cluster URL）不出现在 OpenAPI spec 中

---

## 5. 评审标准

- [x] 10 个 Provider 契约全部定义
- [x] ExecutionBackend 简化为 5 方法
- [x] ModelProvider 合并 chat/embed/asr
- [x] 新增 3 个 Provider 有完整接口（Authorization / Secret / Configuration）
- [x] 不外泄规则明确
