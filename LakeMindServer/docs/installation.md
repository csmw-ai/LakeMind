# 安装手册

> **⚠️ 部分内容过期**：本文档仍包含 Apache Gravitino 安装步骤。Gravitino 已被 PostgreSQL 16 替代，无需单独安装。相关内容仅作历史参考。

LakeMindServer 平台的完整安装步骤。按顺序执行即可从零搭建到验证通过。

---

## 1. 前置条件

| 依赖 | 最低版本 | 验证命令 |
|------|---------|---------|
| Docker Engine | 28.0 | `docker version` |
| Docker Compose | 2.30 | `docker compose version` |
| Python | 3.10+（推荐 3.14） | `python --version` |
| pip | 24.0+ | `pip --version` |

### 1.1 Windows 环境额外说明

- 操作系统：Windows 10/11，启用 WSL2 后端。
- Docker Desktop 设置 → Resources → Memory 建议至少 **4 GB**（Gravitino JVM 默认 2 GB）。
- PowerShell 中文输出乱码是显示问题，不影响功能。如需正确显示：
  ```powershell
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  chcp 65001
  ```

### 1.2 国产镜像加速（可选但推荐）

国内网络拉取 Docker Hub 镜像缓慢或超时，建议配置镜像源。

编辑 Docker Desktop 的 `daemon.json`（Settings → Docker Engine）：

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.mirrors.ustc.edu.cn"
  ]
}
```

保存后 Docker Desktop 会自动重启。验证：

```bash
docker info | grep -A5 "Registry Mirrors"
```

---

## 2. 获取代码

```bash
# 假设仓库已 clone 到本地
cd D:\csmw-ai.com\LakeMind\LakeMindServer
```

目录结构：

```
LakeMindServer/
  docker-compose.yml          # 三服务编排
  .env.example                # 环境变量模板
  config/
    seaweedfs/s3.json         # S3 网关身份配置
    versions.yaml             # 版本配套表
  scripts/
    bootstrap.py              # 启动时数据初始化
    migrate_v01_to_v02.py     # v0.1→v0.2 迁移
  docs/                       # 本文档目录
```

---

## 3. 配置环境变量

```bash
cp .env.example .env
```

打开 `.env`，按需修改（MVP 默认值可直接使用，详见[配置手册](configuration.md)）。

**必须确认的项：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `S3_ACCESS_KEY` | admin | 须与 `config/seaweedfs/s3.json` 中一致 |
| `S3_SECRET_KEY` | admin123456 | 须与 `config/seaweedfs/s3.json` 中一致 |
| `DRAGONFLY_PASSWORD` | （空） | 生产环境务必设置 |

---

## 4. 拉取镜像

```bash
docker compose --env-file .env pull
```

三个镜像总计约 **2.5 GB**：

| 镜像 | 大小 | 说明 |
|------|------|------|
| `chrislusf/seaweedfs:latest` | ~80 MB | SeaweedFS 全功能单进程 |
| `apache/gravitino:1.3.0` | ~1.6 GB | Gravitino + Jetty + JDK |
| `valkey/valkey:8.0` | ~13 MB | Valkey（Redis 兼容 KV） |

### 4.1 Gravitino 镜像拉取失败的处理

Gravitino 1.3.0 镜像较大（1.6 GB 大层），国内拉取可能超时。替代方案：

```bash
# 方案 A：用 daocloud 镜像源直接 curl 下载
curl -L -o gravitino.tar \
  https://docker.m.daocloud.io/apache/gravitino:1.3.0
docker load -i gravitino.tar

# 方案 B：断点续传（适用于大文件中断）
curl -L -C - -o gravitino.tar \
  https://docker.m.daocloud.io/apache/gravitino:1.3.0
docker load -i gravitino.tar
```

---

## 5. 创建数据目录

数据卷采用 bind mount，挂载到 `LakeMindServer/data/` 下：

```bash
# docker compose up 时会自动创建，也可手动预建：
mkdir -p data/seaweedfs data/postgres data/valkey data/lance
```

| 目录 | 容器内路径 | 内容 |
|------|-----------|------|
| `data/seaweedfs/` | `/data` | Filer LevelDB + Volume 数据 |
| `data/gravitino/` | `/gravitino/data` | H2 元数据库文件 |
| `data/valkey/` | `/data` | RDB/AOF 持久化文件 |
| `data/lance/` | （预留） | Lance 向量/多模态数据 |

> `data/` 已在 `.gitignore` 中忽略，不会误提交。

---

## 6. 启动平台

```bash
docker compose --env-file .env up -d
```

预期输出：

```
Network lakemind_lakemind  Created
Container lakemind-seaweedfs  Started
Container lakemind-valkey  Started
Container lakemind-gravitino  Started
```

等待约 15 秒让服务初始化，然后确认状态：

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

预期：

```
NAMES                STATUS                    PORTS
lakemind-valkey      Up                        0.0.0.0:6379->6379/tcp
lakemind-gravitino   Up                        0.0.0.0:8090->8090/tcp, 0.0.0.0:9001->9001/tcp
lakemind-seaweedfs   Up                        0.0.0.0:9333->9333/tcp, ...
```

---

## 7. 安装验证依赖

```bash
pip install boto3 redis
```

---

## 8. 运行验证脚本

```bash
python ../scripts/verify_full.py
```

预期输出（3/3 PASS）：

```
=== LakeMind 平台集成验证 ===
[PASS] SeaweedFS S3 CRUD (put/get/list/delete)
[PASS] Valkey set/get/TTL
[PASS] Gravitino->S3 fileset 集成 (S3 contents: ['knowledge/docs/'])

结果: 3 通过, 0 失败
```

如果出现 FAIL，请查阅[故障排查手册](troubleshooting.md)。

---

## 9. 安装完成检查清单

- [ ] Docker Desktop 运行中，WSL2 后端
- [ ] `.env` 文件已创建并配置
- [ ] 三个容器全部 Up（`docker ps`）
- [ ] `../scripts/verify_full.py` L0-L9 PASS
- [ ] `data/` 目录下有实际数据文件
- [ ] 版本配套表 `config/versions.yaml` 已查阅

---

## 10. 下一步

- 阅读[使用手册](usage.md)了解日常操作。
- 阅读[配置手册](configuration.md)了解参数调优。
- 开始实现 `LakeMindMCP` / `LakeMindSteward` / `LakeMindMonitor` 各包。
