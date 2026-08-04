# LakeMind — Multimodal Intelligent Data Lake

> An **Agent-native cognitive data foundation**. LakeMind gives your organization's agents one shared layer for knowledge, memory, skills, ontology, and multimodal data — accessed through a single declarative MCP interface, governed by one metadata and RBAC system.

[中文文档](./README.md) ｜ License: Apache 2.0

---

## Why you need LakeMind

You have 10 agents. Your team has 100. Your company has 1,000.

- **Cognitive chaos** — every agent maintains its own knowledge; the same concept means different things to different agents. No one can say "what do we actually know?"
- **Fragmented knowledge** — the experience agent A learned yesterday, agent B re-learns today. Hard-won skills live in scattered prompts, files, and chat logs — never searchable, reusable, or inheritable.
- **Lost memory** — the conversation ends, the context clears, the agent's cognition resets to zero. You wired up vector DBs, but ten incompatible ones with hand-rolled tenant isolation, permissions, and lifecycle management.
- **Splintered data** — structured data in Iceberg, vectors in LanceDB, files in S3, graphs in Neo4j, cache in Redis. Every agent must integrate five stores and six SDKs just to be useful.

**LakeMind fixes this.** One cognitive data foundation where all data, knowledge, memory, skills, and ontology live in one place — one API, one metadata layer, one permission system. Agents don't care which engine stores the data; they declare what asset they need, and LakeMind routes to the right engine, tenant, and permission boundary.

---

## What LakeMind is

LakeMind is an **Agent-native cognitive data foundation** (not a generic agent runtime). It is a **unified cognitive data layer** sitting above databases, vector stores, and RAG frameworks — converging multimodal storage, structured tables, vector search, graph storage, KV cache, distributed compute, LLM gateway, memory engine, asset orchestration, and tenant governance into a single data plane that agents can directly consume.

Agents connect to LakeMind over the **MCP protocol** and get **declarative asset access**: no SQL, no SDK juggling, no storage concerns. Declare "I need a knowledge base" or "recall last session's experience" — LakeMind handles the rest.

> **Analogy:** If Kubernetes is the operating system of the container era, LakeMind is the **data operating system of the agent era** — specifically for an agent's *cognitive* data.

![LakeMind Concept](docs/LakeMind-Concept.png)

---

## Quick Start

### Prerequisites

| Requirement | Minimum | Purpose |
|-------------|---------|---------|
| Docker + Docker Compose | Docker 24+ | Run 12 containers |
| Python | 3.12+ | Model pre-download script |
| Node.js | 18+ | Build example frontends |
| RAM | ≥ 8 GB | Includes Ray cluster |
| Disk | ≥ 20 GB | Images + models + data |

### 1. Clone & Configure

```bash
git clone https://github.com/csmw-ai/LakeMind.git
cd LakeMind
cp .env.example .env
```

Edit `.env`:

```bash
MAAS_BASE_URL=https://api.modelarts-maas.com/openai/v1   # or OpenAI / DeepSeek / Ollama
MAAS_API_KEY=<your-llm-api-key>
LAKEMIND_MASTER_KEY=<openssl rand -base64 32>
SERVER_API_KEY=<openssl rand -hex 32>
```

### 2. Pre-download models (offline mode, required)

LakeMind **forbids runtime model downloads**. Pre-download ASR and embedding models before starting:

```bash
pip install modelscope fastembed
python -c "from modelscope import snapshot_download; snapshot_download('iic/SenseVoiceSmall', local_dir='LakeMindModelServing/data/asr-models/asr/sensevoice-small')"
python -c "from modelscope import snapshot_download; snapshot_download('iic/speech_fsmn_vad_zh-cn-16k-common-pytorch', local_dir='LakeMindModelServing/data/asr-models/asr/fsmn-vad')"
python -c "from fastembed import TextEmbedding; m=TextEmbedding(model_name='jinaai/jina-embeddings-v2-base-zh', cache_dir='LakeMindModelServing/data/fastembed_cache'); list(m.embed(['init'])); print('OK')"
```

### 3. Start the platform

```bash
docker compose --env-file .env --profile ray --profile all pull
docker compose --env-file .env --profile ray --profile all up -d
```

### 4. Verify

```bash
curl http://localhost:10823/api/v1/system/health   # all 10 engines: true
```

Open ControlCenter: `http://localhost:3000` (admin login).

### 5. Run an example

```bash
cd examples/meeting-agent
cd frontend && npm install && npm run build && cd ..
docker compose up -d --build
# open http://localhost:9100
```

---

## Architecture

### Two data layers

| Layer | Role | Access | Notes |
|-------|------|--------|-------|
| **Cognitive Asset (ASSET)** | Semantic wrapping for agent cognition | AssetMCP | Knowledge, skills, memory, ontology — declarative YAML, 4 preset types, extensible |
| **Data (DATA)** | Multimodal data foundation, REST passthrough | DataMCP | Iceberg tables, Lance vectors, S3 files, Valkey KV, PG graph |

### Three MCP services

| MCP | Port | Scope | Tools | Responsibility |
|-----|------|-------|-------|----------------|
| LakeMindAssetMCP | 8401 | `asset` | 23 | Cognitive assets: knowledge, skills, memory, ontology |
| LakeMindDataMCP | 8402 | `data` | 24 | Data plane: Iceberg/DuckDB/LanceDB/S3/Valkey/Graph + Ray jobs |
| LakeMindAdminMCP | 8403 | `admin` | 21 | Management: users/tenants/tokens/health |

### Core services

| Service | Port | Responsibility |
|---------|------|----------------|
| LakeMindServer | 10823 | REST API gateway (40+ routes) + 10 engines + Job Runtime |
| LakeMindModelServing | 10824 | litellm LLM gateway + model management API |
| Ray Serve | — | ASR (asr-app) + Embedding (embedding-app) inference |
| LakeMindControlCenter | 3000 | Unified management UI (frontend + BFF + Steward) |

### Engine stack (all open source)

| Engine | Choice | Use |
|--------|--------|-----|
| Object storage | SeaweedFS | S3-compatible, all data files |
| Table format | Apache Iceberg | Structured tables |
| Vector / multimodal | PyLance + LanceDB | Vector search |
| Metadata / graph | PostgreSQL 16 | Iceberg catalog + graph + users/tenants |
| KV cache | Valkey | Redis-compatible TTL KV |
| Ad-hoc SQL | DuckDB | In-process SQL |
| Distributed compute | Ray 2.41 | Job Runtime + Serve |
| Embedding | fastembed | jina-v2-base-zh, dim=768 |
| LLM gateway | litellm | multi-provider routing + fallback |
| ASR | SenseVoice (funasr) | local speech recognition |

---

## Data domain → engine mapping

| Domain | Engine | MCP asset |
|--------|--------|-----------|
| Structured data | Iceberg + PG catalog | DataMCP |
| Knowledge / multimodal RAG | Lance + LanceDB | `lake://knowledge` |
| Short-term / working memory | Valkey (TTL KV) | `lake://memory` |
| Long-term / semantic memory | Lance vectors + PG meta | `lake://memory` |
| Skills | S3 + PG + LanceDB | `lake://skills` |
| Ontology / graph | PG graph_nodes/edges | `lake://ontology` |

---

## Examples

| Example | Path | Validates | Status |
|---------|------|-----------|--------|
| meeting-agent | `examples/meeting-agent/` | Recording → ASR → notes → knowledge (full pipeline) | ✅ verified v0.2.1 |
| lakemind-connector | `examples/lakemind-connector/` | Skill register/retrieve/execute + cognitive asset I/O | ✅ verified |

---

## Tech stack (Apache 2.0 / MIT / BSD only)

SeaweedFS · Apache Iceberg · PyLance + LanceDB · PostgreSQL 16 · Valkey · DuckDB · Ray · fastembed · litellm · SenseVoice (funasr) · FastMCP · LangGraph

---

## Documentation

- **Getting started:** [Quickstart](docs/quickstart.md) · [Model offline download](docs/model-offline-download.md) · [Glossary](docs/glossary.md) · [ControlCenter guide](docs/control-center.md)
- **Develop & architecture:** [Dev guide](docs/develop-guide.md) · [Architecture](docs/architecture.md) · [MCP tools](docs/mcp-tools.md) · [REST API](docs/api-reference.md)
- **Operations:** [Configuration](docs/configuration.md) · [Deployment](docs/deployment.md)

---

## Community & Feedback

- **Bug reports / feature requests:** [GitHub Issues](https://github.com/csmw-ai/LakeMind/issues)
- **Discussions:** [GitHub Discussions](https://github.com/csmw-ai/LakeMind/discussions)
- **Contributing:** see [CONTRIBUTING.md](CONTRIBUTING.md)
- **Code of conduct:** [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

---

## Roadmap

| Version | Planned | Status |
|---------|---------|--------|
| v0.1.0 | MVP: 13 containers, 10 engines, 68 MCP tools | ✅ released |
| v0.2.0 | ControlCenter, RBAC, Job Runtime, model mgmt, Meeting Agent | ✅ released |
| v0.2.1 | Ray Serve migration (ASR+embedding), MCP 2.0, bug fixes | ✅ released |
| v0.2.2 | Docs refresh, model offline-download guide, examples tuning | ✅ released |
| v0.3 | LakeMindStudio (Tauri desktop client) | planned |

---

## License

Apache 2.0. See [LICENSE](LICENSE). Trademark "LakeMind" is owned by the LakeMind project — see [TRADEMARK.md](TRADEMARK.md).
