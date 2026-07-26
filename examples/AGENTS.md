# AGENTS.md

## Repo purpose

Two LakeMind platform examples. **`meeting-agent/` is the primary project** (real-time meeting → ASR → minutes → knowledge extraction). `lakemind-connector/` is a smaller demo showing opencode registering/using a Skill to access LakeMind cognitive assets.

`lakemind-example-develop-guide.md` (root) is the **authoritative spec** for building any example on LakeMind — read it before changing architecture. It defines the MCP discipline, Skill/Job structure, S3 paths, auth, and Docker conventions referenced below.

## Prerequisites (hard)

- **LakeMind full stack running** (~12 containers): Server :10823, ModelServing :10824, AssetMCP :8401, DataMCP :8402, Ray head+workers. Verify with `docker ps | findstr lakemind`.
- **Python ≥3.12** + host **ffmpeg** on PATH. WebM→WAV conversion happens agent-side; Ray workers have no ffmpeg.
- Docker network `lakemind_lakemind` must exist as an external network; example containers join it.

## meeting-agent has TWO run paths (biggest gotcha)

They use different job names, skill refs, and config. Both live in the same dir:

| | Root demo | v0.2.0 app (what Docker ships) |
|---|---|---|
| Run | `python agent.py` | `cd backend && uvicorn app.main:app` (or `docker compose up`) |
| Files | `agent.py` + `lakemind_client.py` + `static/` | `backend/app/main.py` + React `frontend/dist/` |
| Skill env | `SKILL_URI=lake://skills/meeting-processing` | `SKILL_REF=lake://skills/meeting-processing@0.2.0` |
| Job names submitted | `asr`, `summarize`, `extract` | `asr_chunk`, `minutes_generate`, `knowledge_extract` |
| In Docker image? | **No** — `.dockerignore` excludes `agent.py`, `lakemind_client.py`, `static/` | **Yes** — `Dockerfile` + `entrypoint.sh` build/run this |

README "快速开始" documents the root demo; **Docker ships only the v0.2.0 backend**. `manifest.yaml` declares the v0.2.0 job names, so the root demo's `asr`/`summarize`/`extract` are the older set kept alongside in `skills/meeting-processing/jobs/`.

## Commands

```bash
# Root demo (simple single-file FastAPI on :9100)
cd meeting-agent
python scripts/setup.py        # health checks + pack/upload skill to S3
python agent.py                # open http://localhost:9100

# v0.2.0 backend (modular; what Docker builds)
cd meeting-agent/frontend && npm install && npm run build   # MUST build first
cd meeting-agent/backend && python -m uvicorn app.main:app --port 9100
# or, after building frontend/dist/:  docker compose up --build

# Frontend dev server (Vite)
cd meeting-agent/frontend && npm run dev

# One-shot ops (shared by both run paths)
python scripts/seed_models.py      # register model profiles in ModelServing
python scripts/publish_skill.py    # pack + upload skill zip + register/publish with Server
```

`scripts/` also has many ad-hoc `check_*.py` / `test_*.py` / `e2e_test.py` diagnostics — there is **no pytest config**; run them directly with `python`. No root-level lint/typecheck; frontend typechecks via `tsc` inside `npm run build`.

## Gotchas (verify before trusting)

- **`scripts/setup.py` defaults `TENANT_ID=retail`** (line 14), inconsistent with `.env.example` and `publish_skill.py` which use `examples-meeting-agent`. Always export `TENANT_ID`, or setup uploads the skill to the wrong tenant's S3 prefix.
- **Skill version drift across 3 values**: `manifest.yaml` = `0.2.4`, `publish_skill.py` hardcodes zip name `meeting-processing-v0.2.5.zip`, `backend/app/config.py` + `docker-compose.yml` reference `@0.2.0`. Sync all three when bumping the skill.
- **Dockerfile does not build the frontend** — it only `COPY frontend/dist/`. Run `npm run build` in `frontend/` before `docker compose build`, or the image serves a stale/missing SPA.
- **`docker-compose.yml` contains a real-looking `SERVER_API_KEY`**, not the `.env.example` placeholder. Don't add more secrets to compose; use `.env`.
- **Tenant IDs must be flat** (`[a-z0-9-]`, no `/`) — `/` breaks Iceberg namespace `{tenant}_data` and LanceDB paths. Hence `examples-meeting-agent`, not `examples/meeting-agent`.

## Architecture discipline (enforced by platform; see dev guide §2)

- **Agent backend → must use MCP**, never direct Server REST. S3/Ray/Iceberg → DataMCP (:8402); knowledge/memory → AssetMCP (:8401). `lakemind_client.py` and `backend/app/services/lake_client.py` are the MCP wrappers.
- **v0.2.0 backend auth is local SQLite** (`backend/app/security.py` + `app_users` table in `db.py`), NOT LakeMind Server security API. The Server's old `POST /api/v1/security/principals` (405) and `GET /api/v1/security/auth/me` (404) were removed after migration; password login is dead. The per-user token is unused for platform calls — `lake_client.py` always authenticates MCP with the static `MCP_TOKEN` and jobs with `SERVER_KEY`, so local auth is sufficient. `principal_id` is generated locally (`prn_{hex}`) and used only for SQLite row ownership + S3 paths.
- **Ray Jobs are the exception**: `skills/.../jobs/*/main.py` + `lakemind_utils.py` run inside Ray workers and **directly** call Server REST + ModelServing (no MCP). Jobs read params via `json.loads(os.environ["RAY_JOB_PARAMS"])` and write results to S3 + `print`.
- **Model calls use profile names** (`meeting-asr`, `meeting-minutes`, `meeting-knowledge-extract`, `meeting-embedding`), never hardcoded model names. Profiles are seeded by `scripts/seed_models.py` and can be repointed in ControlCenter without code changes.

## Skill / Job structure

```
skills/meeting-processing/
├── manifest.yaml           # declares jobs + model_profiles (source of truth for job names)
├── lakemind_utils.py        # runs in Ray worker: download_from_s3/upload_to_s3/asr/llm_chat/embed
└── jobs/<name>/
    ├── ray.yaml             # entrypoint + pip dependencies + resources
    ├── requirements.txt
    └── main.py              # reads RAY_JOB_PARAMS, calls lakemind_utils, writes result to S3
```

S3 convention: `s3://lakemind-filesets/{tenant_id}/...`; skill zips at `.../skills/{name}-v{version}.zip`.

## Key env vars (full list in `.env.example`)

`SERVER_API_URL`, `SERVER_API_KEY`, `MODEL_SERVING_URL`, `MODELSERVING_API_KEY`, `ASSET_MCP_URL`, `DATA_MCP_URL`, `MCP_TOKEN`, `TENANT_ID`, `SKILL_URI` (root demo) / `SKILL_REF` (v0.2.0), `FFMPEG_PATH`, `PORT`, `SUMMARIZE_INTERVAL`.
