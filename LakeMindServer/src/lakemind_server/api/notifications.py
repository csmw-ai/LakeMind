from __future__ import annotations
import asyncio
from fastapi import APIRouter, Request, HTTPException
from ..security.middleware import get_security_context
from ..services.notification_service import NotificationService

router = APIRouter()


@router.get("")
async def list_notifications(request: Request):
    ctx = get_security_context(request)
    params = request.query_params
    unread_only = params.get("unread_only", "false").lower() == "true"
    page = int(params.get("page", "1"))
    page_size = int(params.get("page_size", "20"))
    return await asyncio.to_thread(
        NotificationService.list_for_principal,
        principal_id=ctx.principal_id,
        unread_only=unread_only,
        page=page, page_size=page_size,
    )


@router.get("/unread-count")
async def unread_count(request: Request):
    ctx = get_security_context(request)
    count = await asyncio.to_thread(NotificationService.unread_count, ctx.principal_id)
    return {"count": count}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str, request: Request):
    ctx = get_security_context(request)
    await asyncio.to_thread(NotificationService.mark_read, notification_id, ctx.principal_id)
    return {"ok": True}
