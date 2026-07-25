from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException
from ..security.middleware import get_security_context
from ..security.actions import Action

router = APIRouter()


def _svc(request: Request):
    return request.app.state.job_service


def _check_perm(ctx, action: str) -> None:
    if not ctx.has_scope(action):
        raise HTTPException(status_code=403, detail="PERMISSION_DENIED")


@router.post("")
async def submit_job(request: Request):
    ctx = get_security_context(request)
    _check_perm(ctx, Action.JOB_SUBMIT.value)
    body = await request.json()
    return _svc(request).submit(ctx, **body)


@router.get("")
async def list_jobs(request: Request):
    ctx = get_security_context(request)
    params = request.query_params
    return _svc(request).list_jobs(
        ctx,
        status=params.get("status"),
        page=int(params.get("page", "1")),
        page_size=int(params.get("page_size", "50")),
    )


@router.get("/{job_id}")
async def get_job(job_id: str, request: Request):
    ctx = get_security_context(request)
    return _svc(request).get_job(ctx, job_id)


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request):
    ctx = get_security_context(request)
    _check_perm(ctx, Action.JOB_CANCEL.value)
    return _svc(request).cancel(ctx, job_id)


@router.post("/{job_id}/retry")
async def retry_job(job_id: str, request: Request):
    ctx = get_security_context(request)
    _check_perm(ctx, Action.JOB_SUBMIT.value)
    return _svc(request).retry(ctx, job_id)


@router.get("/{job_id}/result")
async def get_result(job_id: str, request: Request):
    ctx = get_security_context(request)
    return _svc(request).get_result(ctx, job_id)


@router.get("/{job_id}/attempts")
async def get_attempts(job_id: str, request: Request):
    ctx = get_security_context(request)
    return _svc(request).get_attempts(ctx, job_id)


@router.get("/{job_id}/logs")
async def get_logs(job_id: str, request: Request):
    ctx = get_security_context(request)
    from ..db import execute_one
    job = execute_one("SELECT * FROM job_runs WHERE job_id = %s", (job_id,))
    if job is None:
        raise HTTPException(status_code=404, detail="JOB_NOT_FOUND")
    if not ctx.can_access_tenant(job.get("tenant_id", "")):
        raise HTTPException(status_code=403, detail="TENANT_SCOPE_VIOLATION")

    status = job.get("status", "")
    log_uri = job.get("log_uri")

    if log_uri:
        return {"job_id": job_id, "available": True, "complete": True,
                "source": "archive", "lines": [], "log_uri": log_uri, "next_cursor": None}

    if status in ("RUNNING", "QUEUED"):
        backend = getattr(request.app.state, "ray_backend", None)
        if backend:
            attempt = execute_one(
                "SELECT ray_job_id FROM job_attempts WHERE job_id = %s "
                "AND status IN ('QUEUED','RUNNING') ORDER BY attempt_number DESC LIMIT 1",
                (job_id,),
            )
            if attempt and attempt["ray_job_id"]:
                try:
                    logs = backend.get_logs(attempt["ray_job_id"])
                    lines = logs.splitlines() if logs else []
                    return {"job_id": job_id, "available": True, "complete": False,
                            "source": "live", "lines": lines, "next_cursor": None}
                except Exception:
                    pass
        return {"job_id": job_id, "available": False, "complete": False,
                "source": "live", "lines": [], "next_cursor": None,
                "reason": "Ray backend unavailable"}

    if status == "LOST":
        return {"job_id": job_id, "available": False, "complete": True,
                "source": "lost", "lines": [], "next_cursor": None,
                "reason": "Job status is LOST"}

    return {"job_id": job_id, "available": False, "complete": True,
            "source": "archive", "lines": [], "next_cursor": None,
            "reason": "No archived log"}


@router.get("/{job_id}/timeline")
async def get_timeline(job_id: str, request: Request):
    ctx = get_security_context(request)
    from ..db import execute
    job_events = execute(
        "SELECT id, job_id, event_type, event_seq, occurred_at, payload, correlation_id "
        "FROM job_events WHERE job_id = %s ORDER BY event_seq ASC",
        (job_id,),
    )
    audit_events = execute(
        "SELECT audit_id, event_type, action, result, created_at, request_id "
        "FROM audit_log WHERE resource_id = %s ORDER BY created_at ASC",
        (job_id,),
    )
    events = []
    for e in job_events:
        events.append({"source": "job_event", "id": e["id"], "event_type": e["event_type"],
                        "seq": e["event_seq"], "occurred_at": e["occurred_at"],
                        "payload": e["payload"], "correlation_id": e["correlation_id"]})
    for a in audit_events:
        events.append({"source": "audit", "id": a["audit_id"], "event_type": a["event_type"],
                        "action": a["action"], "result": a["result"],
                        "occurred_at": a["created_at"], "request_id": a["request_id"]})
    events.sort(key=lambda x: x["occurred_at"] if x["occurred_at"] else "")
    return {"events": events}
