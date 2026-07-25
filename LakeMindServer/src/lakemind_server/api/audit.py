from __future__ import annotations
import asyncio
from datetime import datetime
from fastapi import APIRouter, Request
from ..security.middleware import get_security_context
from ..services.audit_service import AuditService

router = APIRouter()


@router.get("")
async def query_audit(request: Request):
    ctx = get_security_context(request)
    params = request.query_params
    return await asyncio.to_thread(
        AuditService.query,
        event_type=params.get("event_type"),
        principal_id=params.get("principal_id"),
        tenant_id=params.get("tenant_id", ctx.tenant_id if not ctx.is_platform_admin else None),
        resource_id=params.get("resource_id"),
        action=params.get("action"),
        result=params.get("result"),
        request_id=params.get("request_id"),
        correlation_id=params.get("correlation_id"),
        operation_id=params.get("operation_id"),
        job_id=params.get("job_id"),
        start_time=datetime.fromisoformat(params["start_time"]) if params.get("start_time") else None,
        end_time=datetime.fromisoformat(params["end_time"]) if params.get("end_time") else None,
        page=int(params.get("page", "1")),
        page_size=int(params.get("page_size", "50")),
    )


@router.get("/export")
async def export_audit(request: Request):
    ctx = get_security_context(request)
    params = request.query_params
    return await asyncio.to_thread(
        AuditService.export,
        event_type=params.get("event_type"),
        tenant_id=params.get("tenant_id", ctx.tenant_id if not ctx.is_platform_admin else None),
        start_time=datetime.fromisoformat(params["start_time"]) if params.get("start_time") else None,
        end_time=datetime.fromisoformat(params["end_time"]) if params.get("end_time") else None,
    )
