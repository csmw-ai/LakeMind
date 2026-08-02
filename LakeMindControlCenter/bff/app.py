from __future__ import annotations
import os
import time
import json
import secrets
import hashlib
import httpx
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="LakeMind Control Center BFF", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_CONTROL_PLANE = os.environ.get("LAKEMIND_CONTROL_PLANE", "http://lakemind-server:10823")
_MODEL_SERVING = os.environ.get("MODEL_SERVING_URL", "http://lakemind-model-serving:10824")
_MODEL_SERVING_KEY = os.environ.get("MODELSERVING_API_KEY", "lakemind-modelserving-key")
_BFF_TOKEN = os.environ.get("LAKEMIND_BFF_TOKEN", "")
_VALKEY_HOST = os.environ.get("VALKEY_HOST", "lakemind-valkey")
_VALKEY_PORT = int(os.environ.get("VALKEY_PORT", "6379"))
_SESSION_TTL = int(os.environ.get("SESSION_TTL", "3600"))
_IDLE_TIMEOUT = int(os.environ.get("SESSION_IDLE_TIMEOUT", "1800"))
_MAX_LIFETIME = int(os.environ.get("SESSION_MAX_LIFETIME", "28800"))

_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        import redis
        _redis = redis.Redis(host=_VALKEY_HOST, port=_VALKEY_PORT, decode_responses=True)
    return _redis


class LoginRequest(BaseModel):
    username: str
    password: str


def _session_set(sid: str, data: dict) -> None:
    _get_redis().setex(f"cc:session:{sid}", _SESSION_TTL, json.dumps(data))


def _session_get(sid: str) -> dict | None:
    raw = _get_redis().get(f"cc:session:{sid}")
    if raw is None:
        return None
    data = json.loads(raw)
    now = time.time()
    if now - data.get("last_access", 0) > _IDLE_TIMEOUT:
        _session_del(sid)
        return None
    if now - data.get("created_at", 0) > _MAX_LIFETIME:
        _session_del(sid)
        return None
    return data


def _session_del(sid: str) -> None:
    _get_redis().delete(f"cc:session:{sid}")


def _session_touch(sid: str, data: dict) -> None:
    data["last_access"] = time.time()
    _session_set(sid, data)


async def _cp_request(method: str, path: str, token: str, *,
                      params: dict | None = None, body: dict | None = None,
                      request_id: str | None = None, correlation_id: str | None = None,
                      tenant_id: str | None = None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"}
    if request_id:
        headers["X-Request-Id"] = request_id
    if correlation_id:
        headers["X-Correlation-Id"] = correlation_id
    if tenant_id:
        headers["X-Tenant-Id"] = tenant_id
    async with httpx.AsyncClient() as client:
        return await client.request(
            method,
            f"{_CONTROL_PLANE}{path}",
            params=params,
            json=body,
            headers=headers,
            timeout=30.0,
        )


async def _ms_request(method: str, path: str, *,
                      params: dict | None = None,
                      request_id: str | None = None, correlation_id: str | None = None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {_MODEL_SERVING_KEY}"}
    if request_id:
        headers["X-Request-Id"] = request_id
    if correlation_id:
        headers["X-Correlation-Id"] = correlation_id
    async with httpx.AsyncClient() as client:
        return await client.request(
            method,
            f"{_MODEL_SERVING}{path}",
            params=params,
            headers=headers,
            timeout=30.0,
        )


def _get_session(request: Request) -> dict:
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="NOT_AUTHENTICATED")
    session = _session_get(session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="SESSION_EXPIRED")
    _session_touch(session_id, session)
    return session


def _check_csrf(request: Request, session: dict) -> None:
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        token = request.headers.get("X-CSRF-Token", "")
        if token != session.get("csrf_token"):
            raise HTTPException(status_code=403, detail="CSRF_TOKEN_MISMATCH")
        origin = request.headers.get("Origin", "")
        allowed = {"http://localhost:3000", "http://127.0.0.1:3000"}
        if origin and origin not in allowed:
            raise HTTPException(status_code=403, detail="ORIGIN_MISMATCH")


def _ctx_from_session(session: dict, request: Request) -> dict:
    return {
        "token": session["token"],
        "request_id": request.headers.get("X-Request-Id", secrets.token_hex(16)),
        "correlation_id": session.get("correlation_id"),
        "tenant_id": session.get("tenant_id", ""),
    }


async def _cp_passthrough(request: Request, path: str, *, method: str | None = None) -> JSONResponse:
    session = _get_session(request)
    _check_csrf(request, session)
    ctx = _ctx_from_session(session, request)
    m = method or request.method
    body = await request.json() if m in ("POST", "PUT", "PATCH") and request.headers.get("content-type", "").startswith("application/json") else None
    params = dict(request.query_params)
    clean_path = path.rstrip("/") if path.endswith("/") and len(path) > 1 else path
    resp = await _cp_request(m, clean_path, ctx["token"], params=params or None, body=body,
                             request_id=ctx["request_id"], correlation_id=ctx["correlation_id"],
                             tenant_id=ctx.get("tenant_id"))
    response = JSONResponse(status_code=resp.status_code, content=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"raw": resp.text})
    response.headers["X-Request-Id"] = ctx["request_id"]
    if ctx["correlation_id"]:
        response.headers["X-Correlation-Id"] = ctx["correlation_id"]
    return response


@app.post("/auth/login")
async def login(req: LoginRequest):
    password_hash = hashlib.sha256(req.password.encode()).hexdigest()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_CONTROL_PLANE}/api/v1/security/auth/login",
            json={"username": req.username, "password_hash": password_hash},
            timeout=10.0,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="INVALID_CREDENTIALS")
        data = resp.json()

    session_id = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    correlation_id = secrets.token_hex(16)
    now = time.time()
    session_data = {
        "username": req.username,
        "token": data.get("token", ""),
        "principal_id": data.get("principal_id", ""),
        "tenant_id": data.get("tenant_id", ""),
        "role": data.get("role", "tenant_admin"),
        "security_version": data.get("security_version", 0),
        "csrf_token": csrf_token,
        "correlation_id": correlation_id,
        "created_at": now,
        "last_access": now,
    }
    _session_set(session_id, session_data)

    response = JSONResponse({
        "session_id": session_id,
        "role": session_data["role"],
        "csrf_token": csrf_token,
        "principal_id": session_data["principal_id"],
        "tenant_id": session_data["tenant_id"],
    })
    response.set_cookie("session_id", session_id, httponly=True,
                        secure=os.environ.get("COOKIE_SECURE", "0") == "1",
                        max_age=_SESSION_TTL, samesite="lax", path="/")
    return response


@app.post("/auth/logout")
async def logout(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id:
        session = _session_get(session_id)
        if session:
            try:
                import redis as redis_mod
                r = _get_redis()
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{_CONTROL_PLANE}/api/v1/security/auth/logout",
                        headers={"Authorization": f"Bearer {session['token']}"},
                        timeout=5.0,
                    )
            except Exception:
                pass
        _session_del(session_id)
    response = JSONResponse({"ok": True})
    response.delete_cookie("session_id", path="/")
    return response


@app.get("/auth/csrf")
async def get_csrf(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="NOT_AUTHENTICATED")
    session = _session_get(session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="SESSION_EXPIRED")
    _session_touch(session_id, session)
    response = JSONResponse({"ok": True})
    response.headers["X-CSRF-Token"] = session.get("csrf_token", "")
    return response


@app.get("/auth/me")
async def get_me(request: Request):
    session = _get_session(request)
    ctx = _ctx_from_session(session, request)
    resp = await _cp_request("GET", "/api/v1/security/auth/me", ctx["token"],
                             request_id=ctx["request_id"], correlation_id=ctx["correlation_id"], tenant_id=ctx.get("tenant_id"))
    if resp.status_code != 200:
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    data = resp.json()
    data["username"] = session.get("username")
    return JSONResponse(data)


@app.get("/overview")
async def overview(request: Request):
    session = _get_session(request)
    ctx = _ctx_from_session(session, request)
    import asyncio
    results = await asyncio.gather(
        _cp_request("GET", "/api/v1/instances", ctx["token"], request_id=ctx["request_id"], correlation_id=ctx["correlation_id"], tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", "/api/v1/assets", ctx["token"], params={"page_size": "1"}, request_id=ctx["request_id"], correlation_id=ctx["correlation_id"], tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", "/api/v1/jobs", ctx["token"], params={"page_size": "1"}, request_id=ctx["request_id"], correlation_id=ctx["correlation_id"], tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", "/api/v1/audit", ctx["token"], params={"page_size": "5"}, request_id=ctx["request_id"], correlation_id=ctx["correlation_id"], tenant_id=ctx.get("tenant_id")),
        return_exceptions=True,
    )
    resp = JSONResponse({
        "instances": results[0].json() if not isinstance(results[0], Exception) and results[0].status_code == 200 else {"items": []},
        "assets_total": results[1].json().get("total", 0) if not isinstance(results[1], Exception) and results[1].status_code == 200 else 0,
        "jobs_total": results[2].json().get("total", 0) if not isinstance(results[2], Exception) and results[2].status_code == 200 else 0,
        "recent_audit": results[3].json().get("items", []) if not isinstance(results[3], Exception) and results[3].status_code == 200 else [],
    })
    return resp


@app.post("/auth/switch-tenant")
async def switch_tenant(request: Request):
    session = _get_session(request)
    _check_csrf(request, session)
    ctx = _ctx_from_session(session, request)
    body = await request.json()
    resp = await _cp_request("POST", "/api/v1/security/switch-tenant", ctx["token"],
                             body=body, request_id=ctx["request_id"], correlation_id=ctx["correlation_id"], tenant_id=ctx.get("tenant_id"))
    if resp.status_code == 200:
        data = resp.json()
        session["tenant_id"] = data.get("tenant_id", session.get("tenant_id"))
        _session_set(request.cookies.get("session_id"), session)
    return JSONResponse(status_code=resp.status_code, content=resp.json())


@app.get("/feature-flags")
async def feature_flags(request: Request):
    session = _get_session(request)
    return JSONResponse({
        "steward_context_panel": {"enabled": True},
        "realtime_sse": {"enabled": True},
        "global_search": {"enabled": True},
        "mission_control_v2": {"enabled": True},
        "tenant_create_wizard": {"enabled": True},
    })


@app.get("/view/mission-control")
async def view_mission_control(request: Request):
    session = _get_session(request)
    ctx = _ctx_from_session(session, request)
    import asyncio
    token = ctx["token"]
    rid = ctx["request_id"]
    cid = ctx["correlation_id"]

    results = await asyncio.gather(
        _cp_request("GET", "/api/v1/operations", token, params={"status": "APPROVAL_REQUIRED", "page_size": "100"}, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", "/api/v1/jobs", token, params={"status": "FAILED", "page_size": "100"}, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", "/api/v1/assets", token, params={"health": "DEGRADED", "page_size": "100"}, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        _ms_request("GET", "/v1/models", request_id=rid, correlation_id=cid),
        _cp_request("GET", "/api/v1/observability/metrics", token, params={"name": "service.health"}, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", "/api/v1/observability/metrics", token, params={"name": "cpu.usage"}, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", "/api/v1/observability/metrics", token, params={"name": "memory.usage"}, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", "/api/v1/observability/metrics", token, params={"name": "storage.usage"}, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", "/api/v1/observability/metrics", token, params={"name": "job.queue_depth"}, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", "/api/v1/audit", token, params={"page_size": "5"}, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", "/api/v1/system/reconcile/drifts", token, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        return_exceptions=True,
    )

    def _safe(idx, key=None):
        r = results[idx]
        if isinstance(r, Exception):
            return None
        if r.status_code != 200:
            return None
        try:
            return r.json() if key is None else r.json().get(key)
        except Exception:
            return None

    partial_failures = []
    for idx, name in enumerate(["operations", "jobs", "assets", "deployments", "svc_health", "cpu", "mem", "storage", "job_q", "audit", "reconcile"]):
        if _safe(idx) is None:
            partial_failures.append(name)

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    def _count_card(idx):
        data = _safe(idx)
        if data is None:
            return {"value": None, "observed_at": None, "freshness_seconds": None, "stale": True, "partial": True, "total": 0}
        if isinstance(data, dict) and "items" in data:
            items = data["items"] if isinstance(data["items"], list) else []
            t = data.get("total", len(items))
            return {"value": t, "observed_at": now_iso, "freshness_seconds": 0, "stale": False, "partial": False, "total": t}
        if isinstance(data, list):
            return {"value": len(data), "observed_at": now_iso, "freshness_seconds": 0, "stale": False, "partial": False, "total": len(data)}
        return {"value": data, "observed_at": now_iso, "freshness_seconds": 0, "stale": False, "partial": False}

    def _unhealthy_models_card(idx):
        data = _safe(idx)
        if data is None:
            return {"value": None, "observed_at": None, "freshness_seconds": None, "stale": True, "partial": True, "total": 0}
        models = []
        if isinstance(data, dict) and "data" in data:
            models = data["data"] if isinstance(data["data"], list) else []
        elif isinstance(data, list):
            models = data
        unhealthy = [m for m in models if isinstance(m, dict) and m.get("health_status") == "unhealthy"]
        return {"value": len(unhealthy), "observed_at": now_iso, "freshness_seconds": 0, "stale": False, "partial": False, "total": len(models)}

    def _items_card(idx):
        data = _safe(idx)
        if data is None:
            return {"value": [], "observed_at": None, "freshness_seconds": None, "stale": True, "partial": True, "total": 0}
        if isinstance(data, dict) and "items" in data:
            items = data["items"] if isinstance(data["items"], list) else []
            return {"value": items, "observed_at": now_iso, "freshness_seconds": 0, "stale": False, "partial": False, "total": data.get("total", len(items))}
        if isinstance(data, list):
            return {"value": data, "observed_at": now_iso, "freshness_seconds": 0, "stale": False, "partial": False, "total": len(data)}
        return {"value": [], "observed_at": now_iso, "freshness_seconds": 0, "stale": False, "partial": False}

    def _metric_card(idx):
        data = _safe(idx)
        if data is None:
            return {"value": None, "observed_at": None, "freshness_seconds": None, "stale": True, "partial": True}
        if isinstance(data, dict) and "items" in data:
            items = data["items"] if isinstance(data["items"], list) else []
            latest = items[0] if items else None
            return {"value": latest.get("value") if latest else None, "observed_at": data.get("observed_at", now_iso), "freshness_seconds": data.get("freshness_seconds"), "stale": data.get("stale", False), "partial": False, "total": len(items)}
        return {"value": data, "observed_at": now_iso, "freshness_seconds": 0, "stale": False, "partial": False}

    return JSONResponse({
        "_meta": {
            "request_id": rid,
            "correlation_id": cid,
            "partial": len(partial_failures) > 0,
            "partial_failure": partial_failures,
            "observed_at": now_iso,
        },
        "pending_approvals": _count_card(0),
        "failed_jobs": _count_card(1),
        "degraded_assets": _count_card(2),
        "unhealthy_deployments": _unhealthy_models_card(3),
        "service_health": _metric_card(4),
        "cpu_usage": _metric_card(5),
        "memory_usage": _metric_card(6),
        "storage_usage": _metric_card(7),
        "job_queue_depth": _metric_card(8),
        "recent_changes": _items_card(9),
        "outbox_backlog": _count_card(10),
    })


@app.get("/view/tenant-detail/{tenant_id}")
async def view_tenant_detail(tenant_id: str, request: Request):
    session = _get_session(request)
    ctx = _ctx_from_session(session, request)
    import asyncio
    token = ctx["token"]
    rid = ctx["request_id"]
    cid = ctx["correlation_id"]
    base = f"/api/v1/tenants/{tenant_id}"
    results = await asyncio.gather(
        _cp_request("GET", base, token, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", f"{base}/memberships", token, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", "/api/v1/audit", token, params={"tenant_id": tenant_id, "page_size": "20"}, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        return_exceptions=True,
    )
    def _safe(idx):
        r = results[idx]
        if isinstance(r, Exception) or r.status_code != 200:
            return None
        try:
            return r.json()
        except Exception:
            return None
    _tenant = _safe(0)
    _members = _safe(1) or {}
    _audit = _safe(2) or {}
    return JSONResponse({
        "_meta": {"request_id": rid, "correlation_id": cid, "observed_at": datetime.now(timezone.utc).isoformat()},
        "tenant": _tenant,
        "members": _members.get("items", []) if isinstance(_members, dict) else [],
        "recent_audit": _audit.get("items", []) if isinstance(_audit, dict) else [],
    })


@app.get("/view/job-detail/{job_id}")
async def view_job_detail(job_id: str, request: Request):
    session = _get_session(request)
    ctx = _ctx_from_session(session, request)
    import asyncio
    token = ctx["token"]
    rid = ctx["request_id"]
    cid = ctx["correlation_id"]
    results = await asyncio.gather(
        _cp_request("GET", f"/api/v1/jobs/{job_id}", token, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", f"/api/v1/jobs/{job_id}/attempts", token, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        _cp_request("GET", f"/api/v1/jobs/{job_id}/events", token, request_id=rid, correlation_id=cid, tenant_id=ctx.get("tenant_id")),
        return_exceptions=True,
    )
    def _safe(idx):
        r = results[idx]
        if isinstance(r, Exception) or r.status_code != 200:
            return None
        try:
            return r.json()
        except Exception:
            return None
    return JSONResponse({
        "_meta": {"request_id": rid, "correlation_id": cid, "observed_at": datetime.now(timezone.utc).isoformat()},
        "job": _safe(0),
        "attempts": _safe(1),
        "events": _safe(2),
    })


@app.get("/view/jobs-dashboard")
async def view_jobs_dashboard(request: Request):
    session = _get_session(request)
    ctx = _ctx_from_session(session, request)
    import asyncio
    token = ctx["token"]
    rid = ctx["request_id"]
    cid = ctx["correlation_id"]
    tid = ctx.get("tenant_id")

    results = await asyncio.gather(
        _cp_request("GET", "/api/v1/jobs", token, params={"status": "SUCCEEDED", "page_size": "1"}, request_id=rid, correlation_id=cid, tenant_id=tid),
        _cp_request("GET", "/api/v1/jobs", token, params={"status": "FAILED", "page_size": "1"}, request_id=rid, correlation_id=cid, tenant_id=tid),
        _cp_request("GET", "/api/v1/jobs", token, params={"status": "RUNNING", "page_size": "1"}, request_id=rid, correlation_id=cid, tenant_id=tid),
        _cp_request("GET", "/api/v1/jobs", token, params={"status": "QUEUED", "page_size": "1"}, request_id=rid, correlation_id=cid, tenant_id=tid),
        _cp_request("GET", "/api/v1/jobs", token, params={"page_size": "200"}, request_id=rid, correlation_id=cid, tenant_id=tid),
        return_exceptions=True,
    )

    def _safe(idx):
        r = results[idx]
        if isinstance(r, Exception) or r.status_code != 200:
            return None
        try:
            return r.json()
        except Exception:
            return None

    def _total(idx):
        data = _safe(idx)
        if data is None:
            return None
        if isinstance(data, dict):
            return data.get("total", len(data.get("items", [])))
        if isinstance(data, list):
            return len(data)
        return None

    recent = _safe(4)
    recent_items: list = []
    recent_total = 0
    if recent and isinstance(recent, dict):
        recent_items = recent.get("items", []) if isinstance(recent.get("items"), list) else []
        recent_total = recent.get("total", len(recent_items))
    elif recent and isinstance(recent, list):
        recent_items = recent
        recent_total = len(recent)

    partial_failures: list[str] = []
    for idx, name in enumerate(["succeeded", "failed", "running", "pending", "recent"]):
        if _safe(idx) is None:
            partial_failures.append(name)

    now_iso = datetime.now(timezone.utc).isoformat()

    return JSONResponse({
        "_meta": {
            "request_id": rid,
            "correlation_id": cid,
            "partial": len(partial_failures) > 0,
            "partial_failure": partial_failures,
            "observed_at": now_iso,
        },
        "total": recent_total,
        "succeeded": _total(0),
        "failed": _total(1),
        "running": _total(2),
        "pending": _total(3),
        "recent_jobs": recent_items,
    })


@app.get("/view/asset-detail/{asset_id}")
async def view_asset_detail(asset_id: str, request: Request):
    return await _cp_passthrough(request, f"/api/v1/assets/{asset_id}")


@app.get("/view/deployment-detail/{deployment_id}")
async def view_deployment_detail(deployment_id: str, request: Request):
    return await _cp_passthrough(request, f"/api/v1/models/deployments/{deployment_id}")


@app.get("/view/service-detail/{service_id}")
async def view_service_detail(service_id: str, request: Request):
    return await _cp_passthrough(request, f"/api/v1/instances/{service_id}")


@app.api_route("/events", methods=["GET"])
@app.api_route("/events/{path:path}", methods=["GET"])
async def events_proxy(request: Request, path: str = ""):
    return await _cp_passthrough(request, f"/api/v1/events/{path}")


@app.api_route("/events/stream", methods=["GET"])
async def events_stream(request: Request):
    session = _get_session(request)
    ctx = _ctx_from_session(session, request)
    import httpx
    from fastapi.responses import StreamingResponse

    headers = {"Authorization": f"Bearer {ctx['token']}"}
    last_event_id = request.headers.get("Last-Event-ID")
    if last_event_id:
        headers["Last-Event-ID"] = last_event_id
    if ctx["correlation_id"]:
        headers["X-Correlation-Id"] = ctx["correlation_id"]
    if ctx.get("tenant_id"):
        headers["X-Tenant-Id"] = ctx["tenant_id"]

    async def proxy_stream():
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", f"{_CONTROL_PLANE}/api/v1/events/stream",
                                     headers=headers, timeout=None) as resp:
                async for chunk in resp.aiter_text():
                    yield chunk

    return StreamingResponse(proxy_stream(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                                       "X-Accel-Buffering": "no"})


@app.api_route("/notifications", methods=["GET", "POST"])
@app.api_route("/notifications/{path:path}", methods=["GET", "POST"])
async def notifications_proxy(request: Request, path: str = ""):
    return await _cp_passthrough(request, f"/api/v1/notifications/{path}")


@app.api_route("/search", methods=["GET"])
async def search_proxy(request: Request):
    return await _cp_passthrough(request, "/api/v1/search")


@app.api_route("/observability", methods=["GET", "POST"])
@app.api_route("/observability/{path:path}", methods=["GET", "POST"])
async def observability_proxy(request: Request, path: str = ""):
    return await _cp_passthrough(request, f"/api/v1/observability/{path}")


@app.api_route("/assets", methods=["GET", "POST"])
@app.api_route("/assets/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def assets_proxy(request: Request, path: str = ""):
    return await _cp_passthrough(request, f"/api/v1/assets/{path}")


@app.api_route("/jobs", methods=["GET", "POST"])
@app.api_route("/jobs/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def jobs_proxy(request: Request, path: str = ""):
    return await _cp_passthrough(request, f"/api/v1/jobs/{path}")


async def _ms_passthrough(request: Request, target_path: str):
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            request.method,
            f"{_MODEL_SERVING}{target_path}",
            headers={"Authorization": f"Bearer {_MODEL_SERVING_KEY}", "Content-Type": "application/json"},
            content=await request.body(),
            params=request.query_params,
        )
        try:
            data = resp.json()
        except Exception:
            data = {"detail": resp.text}
        return JSONResponse(content=data, status_code=resp.status_code)


@app.api_route("/providers", methods=["GET", "POST"])
async def providers_root(request: Request):
    return await _ms_passthrough(request, "/v1/providers")


@app.api_route("/providers/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def providers_proxy(request: Request, path: str):
    return await _ms_passthrough(request, f"/v1/providers/{path}")


@app.api_route("/models", methods=["GET", "POST"])
async def models_root(request: Request):
    return await _ms_passthrough(request, "/v1/models")


@app.api_route("/models/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def models_proxy(request: Request, path: str):
    return await _ms_passthrough(request, f"/v1/models/{path}")


@app.api_route("/profiles", methods=["GET", "POST"])
async def profiles_root(request: Request):
    return await _ms_passthrough(request, "/v1/profiles")


@app.api_route("/profiles/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def profiles_proxy(request: Request, path: str):
    return await _ms_passthrough(request, f"/v1/profiles/{path}")


@app.api_route("/instances", methods=["GET"])
@app.api_route("/instances/{path:path}", methods=["GET"])
async def instances_proxy(request: Request, path: str = ""):
    return await _cp_passthrough(request, f"/api/v1/instances/{path}")


@app.api_route("/configuration", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("/configuration/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def config_proxy(request: Request, path: str = ""):
    return await _cp_passthrough(request, f"/api/v1/configuration/{path}")


@app.api_route("/security", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("/security/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def security_proxy(request: Request, path: str = ""):
    return await _cp_passthrough(request, f"/api/v1/security/{path}")


@app.api_route("/operations", methods=["GET", "POST"])
@app.api_route("/operations/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def operations_proxy(request: Request, path: str = ""):
    return await _cp_passthrough(request, f"/api/v1/operations/{path}")


@app.api_route("/audit", methods=["GET"])
@app.api_route("/audit/{path:path}", methods=["GET"])
async def audit_proxy(request: Request, path: str = ""):
    return await _cp_passthrough(request, f"/api/v1/audit/{path}")


@app.api_route("/tenants", methods=["GET", "POST"])
@app.api_route("/tenants/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def tenants_proxy(request: Request, path: str = ""):
    return await _cp_passthrough(request, f"/api/v1/tenants/{path}")


@app.api_route("/steward", methods=["GET", "POST"])
@app.api_route("/steward/{path:path}", methods=["GET", "POST"])
async def steward_proxy(request: Request, path: str = ""):
    return await _cp_passthrough(request, f"/api/v1/steward/{path}")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "control-center-bff", "version": "2.1.0"}
