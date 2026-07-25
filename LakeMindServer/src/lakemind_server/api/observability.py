from __future__ import annotations
import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from ..security.middleware import get_security_context
from ..services.metrics_service import MetricsService, CardinalityViolation

router = APIRouter()


@router.get("/metrics")
async def query_metrics(request: Request):
    ctx = get_security_context(request)
    params = request.query_params
    metric_name = params.get("name", "")
    if not metric_name:
        raise HTTPException(status_code=400, detail="metric name required")
    labels = None
    if params.get("labels"):
        try:
            labels = json.loads(params["labels"])
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid labels JSON")
    from_time = datetime.fromisoformat(params["from"]) if params.get("from") else None
    to_time = datetime.fromisoformat(params["to"]) if params.get("to") else None
    page_size = int(params.get("page_size", "500"))
    scope_filter = ctx.accessible_scope_filter()
    scope_type = scope_filter.get("scope_type")
    scope_id = scope_filter.get("scope_id")
    result = await asyncio.to_thread(
        MetricsService.query,
        metric_name=metric_name, labels=labels,
        from_time=from_time, to_time=to_time, page_size=page_size,
    )
    if scope_type:
        result["items"] = [
            m for m in result["items"]
            if m.get("scope_type") == scope_type
            and (scope_id is None or m.get("scope_id") == scope_id)
        ]
        result["total"] = len(result["items"])
    return result


@router.post("/metrics")
async def write_metrics(request: Request):
    ctx = get_security_context(request)
    if not ctx.is_platform_admin and ctx.principal_type != "api_key":
        raise HTTPException(status_code=403, detail="PERMISSION_DENIED")
    body = await request.json()
    metrics = body.get("metrics", [])
    try:
        count = await asyncio.to_thread(MetricsService.write_batch, metrics)
    except CardinalityViolation as exc:
        raise HTTPException(status_code=400, detail={"error": "CARDINALITY_VIOLATION", "forbidden": list(exc.forbidden)})
    return {"written": count}
