from __future__ import annotations
import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from .config import load_config, ServerConfig
from .engines import Engines
from .auth import verify_api_key, get_tenant_context

logger = logging.getLogger(__name__)

cfg = load_config()
engines = Engines(cfg)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .plugins.compute.distributed.ray_execution_backend import RayExecutionBackend
    from .services.job_service import JobService
    from .services.job_sync_service import JobSyncService
    from .outbox.worker import register_default_handlers

    ray_backend = None
    try:
        ray_backend = RayExecutionBackend()
        logger.info("RayExecutionBackend initialized: %s", ray_backend._dashboard)
    except Exception as e:
        logger.warning("Ray backend unavailable: %s", e)
    app.state.ray_backend = ray_backend
    app.state.job_service = JobService(backend=ray_backend)
    app.state.job_sync_service = JobSyncService(backend=ray_backend)
    app.state.job_runtime_healthy = ray_backend is not None

    register_default_handlers()

    try:
        app.state.job_sync_service.recover_on_startup()
        logger.info("Job recovery completed")
    except Exception as e:
        logger.warning("Job recovery failed: %s", e)

    from .services.monitoring_service import start_monitoring
    start_monitoring(app)

    tasks = [
        asyncio.create_task(_job_sync_loop(app)),
        asyncio.create_task(_outbox_loop(app)),
    ]
    app.state._bg_tasks = tasks

    yield

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _job_sync_loop(app: FastAPI) -> None:
    sync_service = app.state.job_sync_service
    sync_interval = float(os.environ.get("JOB_SYNC_INTERVAL", "3"))
    timeout_interval = float(os.environ.get("JOB_TIMEOUT_INTERVAL", "30"))
    last_timeout = 0.0
    while True:
        try:
            await asyncio.to_thread(sync_service.sync_all)
            await asyncio.to_thread(sync_service.cleanup_zombies)
            now = asyncio.get_event_loop().time()
            if now - last_timeout >= timeout_interval:
                await asyncio.to_thread(sync_service.check_timeouts)
                last_timeout = now
        except Exception as e:
            logger.warning("Job sync loop error: %s", e)
        await asyncio.sleep(sync_interval)


async def _outbox_loop(app: FastAPI) -> None:
    from .outbox.worker import process_batch
    interval = float(os.environ.get("OUTBOX_INTERVAL", "1"))
    batch_size = int(os.environ.get("OUTBOX_BATCH_SIZE", "10"))
    while True:
        try:
            await asyncio.to_thread(process_batch, batch_size)
        except Exception as e:
            logger.warning("Outbox loop error: %s", e)
        await asyncio.sleep(interval)


from .api import objects, tables, vectors, kv, graph, sql, memory, metadata, system, secrets
from .api import security as security_api
from .api import configuration as config_api
from .api import audit as audit_api
from .api import operations as operations_api
from .api import instances as instances_api
from .api import assets as assets_api
from .api import knowledge as knowledge_api
from .api import skills as skills_api
from .api import memories as memories_api
from .api import jobs as jobs_api
from .api import secrets_v2 as secrets_v2_api
from .api import tenants as tenants_api
from .api import steward as steward_api
from .api import observability as observability_api
from .api import events as events_api
from .api import notifications as notifications_api
from .api import search as search_api

cfg = load_config()
engines = Engines(cfg)

app = FastAPI(title="LakeMind Server", version="0.2.0", lifespan=lifespan)

app.state.cfg = cfg
app.state.engines = engines

_USE_V2_AUTH = os.environ.get("LAKEMIND_V2_AUTH", "0") == "1"


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if _USE_V2_AUTH:
        from .security.middleware import security_middleware
        return await security_middleware(request, call_next)

    if request.url.path in ("/docs", "/openapi.json", "/redoc", "/api/v1/system/health", "/api/v1/security/auth/login") or request.url.path == "/api/v1/system/health":
        return await call_next(request)
    if not request.url.path.startswith("/api/v1/"):
        return await call_next(request)
    try:
        await verify_api_key(request, cfg)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    from .security.context import SecurityContext
    from .security.actions import actions_for_roles
    import uuid
    request.state.security_context = SecurityContext(
        principal_id="legacy-api-key",
        principal_type="api_key",
        tenant_id=request.headers.get("X-Tenant-Id", "default"),
        roles=["tenant_admin"],
        scopes=actions_for_roles(["tenant_admin"]),
        token_id="legacy",
        request_id=request.headers.get("X-Request-Id", str(uuid.uuid4())),
        correlation_id=request.headers.get("X-Correlation-Id"),
    )
    return await call_next(request)


_DEPRECATED_PREFIXES = (
    "/api/v1/storage/",
    "/api/v1/compute/",
    "/api/v1/cognitive/memory",
    "/api/v1/metadata",
)


@app.middleware("http")
async def deprecation_header_middleware(request: Request, call_next):
    response = await call_next(request)
    if any(request.url.path.startswith(p) for p in _DEPRECATED_PREFIXES):
        response.headers["X-Deprecated"] = "true"
        response.headers["X-Deprecated-Message"] = "Use v2 API endpoints instead"
    return response


app.include_router(objects.router, prefix="/api/v1/storage/objects", tags=["storage-objects"])
app.include_router(tables.router, prefix="/api/v1/storage/tables", tags=["storage-tables"])
app.include_router(vectors.router, prefix="/api/v1/storage/vectors", tags=["storage-vectors"])
app.include_router(kv.router, prefix="/api/v1/storage/kv", tags=["storage-kv"])
app.include_router(graph.router, prefix="/api/v1/storage/graph", tags=["storage-graph"])
app.include_router(sql.router, prefix="/api/v1/compute/sql", tags=["compute-sql"])
app.include_router(memory.router, prefix="/api/v1/cognitive/memory", tags=["cognitive-memory"])
app.include_router(metadata.router, prefix="/api/v1/metadata", tags=["metadata"])
app.include_router(secrets.router, prefix="/api/v1/metadata/secrets", tags=["metadata-secrets"])
app.include_router(system.router, prefix="/api/v1/system", tags=["system"])

app.include_router(security_api.router, prefix="/api/v1/security", tags=["security"])
app.include_router(config_api.router, prefix="/api/v1/configuration", tags=["configuration"])
app.include_router(audit_api.router, prefix="/api/v1/audit", tags=["audit"])
app.include_router(operations_api.router, prefix="/api/v1/operations", tags=["operations"])
app.include_router(instances_api.router, prefix="/api/v1/instances", tags=["instances"])

app.include_router(assets_api.router, prefix="/api/v1/assets", tags=["assets"])
app.include_router(knowledge_api.router, prefix="/api/v1/knowledge", tags=["knowledge"])
app.include_router(skills_api.router, prefix="/api/v1/skills", tags=["skills"])
app.include_router(memories_api.router, prefix="/api/v1/memories", tags=["memories"])

app.include_router(jobs_api.router, prefix="/api/v1/jobs", tags=["jobs"])

app.include_router(secrets_v2_api.router, prefix="/api/v1/secrets", tags=["secrets-v2"])

app.include_router(tenants_api.router, prefix="/api/v1/tenants", tags=["tenants"])

app.include_router(steward_api.router, prefix="/api/v1/steward", tags=["steward"])

app.include_router(observability_api.router, prefix="/api/v1/observability", tags=["observability"])
app.include_router(events_api.router, prefix="/api/v1/events", tags=["events"])
app.include_router(notifications_api.router, prefix="/api/v1/notifications", tags=["notifications"])
app.include_router(search_api.router, prefix="/api/v1/search", tags=["search"])


@app.get("/api/v1/health", tags=["system"])
async def health():
    return {
        "status": "ok",
        "version": "0.2.0",
        "job_runtime": "healthy" if getattr(app.state, "job_runtime_healthy", False) else "degraded",
    }
