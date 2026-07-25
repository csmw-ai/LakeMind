# 配置参考

LakeMind 通过 `engines.yaml` 统一配置所有引擎，支持运行时切换插件实现，不改代码。

## 配置文件位置

- 容器内：`/etc/lakemind/engines.yaml`（bind mount from `config/engines.yaml`）
- 环境变量：`LAKE_CONFIG` 可覆盖路径

## 环境变量解析

配置中 `${VAR}` 语法自动解析为环境变量：

```yaml
api_key: "${MAAS_API_KEY}"    # → os.environ["MAAS_API_KEY"]
```

支持嵌套 list/dict 递归解析。

## 完整配置结构

```yaml
server:
  host: "0.0.0.0"
  port: 10823
  api_key: "lakemind-internal-api-key"

storage:
  object:       # 对象存储
  tabular:      # 结构化表
  vector:       # 向量存储
  kv:           # KV 缓存
  graph:        # 图存储
  metadata:     # 元数据

compute:
  sql:          # 即席 SQL
  distributed:  # 分布式计算

cognitive:
  memory:       # 记忆引擎
    model_serving_url: "http://lakemind-model-serving:10824"
```

## 1. 对象存储

```yaml
storage:
  object:
    plugin: seaweedfs
    config:
      endpoint: "http://lakemind-seaweedfs:8333"
      access_key: "admin"
      secret_key: "admin123456"
      region: "us-east-1"
      path_style: true
```

切换到 AWS S3：

```yaml
    plugin: aws_s3
    config:
      endpoint: "https://s3.amazonaws.com"
      access_key: "${AWS_ACCESS_KEY_ID}"
      secret_key: "${AWS_SECRET_ACCESS_KEY}"
      region: "us-east-1"
      path_style: false
```

## 2. 结构化表

```yaml
storage:
  tabular:
    plugin: iceberg
    config:
      catalog_name: "lakemind"
      warehouse: "s3://lakemind-iceberg/warehouse"
      sql_uri: "postgresql+psycopg2://lakemind:lakemind_pass@lakemind-postgres:5432/lakemind"
```

## 3. 向量存储

```yaml
storage:
  vector:
    plugin: lancedb
    config:
      uri: "/data/lance"
```

## 4. KV 缓存

```yaml
storage:
  kv:
    plugin: valkey
    config:
      host: "lakemind-valkey"
      port: 6379
      password: ""
```

切换到 Redis：

```yaml
    plugin: redis
    config:
      host: "my-redis"
      port: 6379
```

## 5. 图存储

```yaml
storage:
  graph:
    plugin: postgres_graph
    config:
      host: "lakemind-postgres"
      port: 5432
      db: "lakemind"
      user: "lakemind"
      password: "lakemind_pass"
```

## 6. 元数据

```yaml
storage:
  metadata:
    plugin: postgres
    config:
      host: "lakemind-postgres"
      port: 5432
      db: "lakemind"
      user: "lakemind"
      password: "lakemind_pass"
      pool_size: 20
```

## 7. 即席 SQL

```yaml
compute:
  sql:
    plugin: duckdb
    config:
      memory_limit: "2GB"
```

## 8. 分布式计算

```yaml
compute:
  distributed:
    plugin: ray
    config:
      address: "ray://lakemind-ray-head:10001"
```

切换回嵌入式（无 Ray）：

```yaml
    plugin: embedded
    config: {}
```

## 9. Embedding

Embedding 配置已移至 LakeMindModelServing，见 `LakeMindModelServing/config/models.yaml`。

## 10. 记忆引擎

```yaml
cognitive:
  memory:
    plugin: basic
    config:
      host: "lakemind-postgres"
      port: 5432
      db: "lakemind"
      user: "lakemind"
      password: "lakemind_pass"
      kv_host: "lakemind-valkey"
      kv_port: 6379
      lance_uri: "/data/lance"
      embedding_model: "jinaai/jina-embeddings-v2-base-zh"
      embedding_dim: 768
      llm_model: "deepseek-v4-flash"
      model_serving_url: "http://lakemind-model-serving:10824"
```

## 11. LLM 推理网关

LLM 推理网关配置已移至 LakeMindModelServing，见 `LakeMindModelServing/config/models.yaml`。配置从 `engines.yaml` 迁移至 `models.yaml`。

## 12. LakeMindModelServing 配置

配置文件：`LakeMindModelServing/config/models.yaml`

包含：
- litellm provider 配置（modelarts/openai/anthropic/ollama）
- fastembed 嵌入配置
- faster-whisper 语音识别配置
- 模型注册表（PG model_registry 表）

## .env 环境变量

```env
# SeaweedFS
SEAWEEDFS_IMAGE=chrislusf/seaweedfs:latest
S3_ACCESS_KEY=admin
S3_SECRET_KEY=admin123456

# PostgreSQL
PG_DB=lakemind
PG_USER=lakemind
PG_PASSWORD=lakemind_pass

# Valkey
VALKEY_IMAGE=valkey/valkey:8.0

# Ray
RAY_IMAGE=lakemind/ray:2.41.0-py3.12
RAY_HEAD_CPUS=4
RAY_WORKER_CPUS=4

# LLM 网关
MAAS_API_KEY=your-key-here
# OPENAI_API_KEY=your-openai-key
# ANTHROPIC_API_KEY=your-anthropic-key
```
