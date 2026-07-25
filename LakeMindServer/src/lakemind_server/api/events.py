from __future__ import annotations
import asyncio
from fastapi import APIRouter, Request, HTTPException
from ..security.middleware import get_security_context
from ..services.event_service import EventService

router = APIRouter()


@router.get("")
async def query_events(request: Request):
    ctx = get_security_context(request)
    params = request.query_params
    after_sequence = int(params.get("after_sequence", "0"))
    event_type = params.get("event_type")
    resource_type = params.get("resource_type")
    page_size = int(params.get("page_size", "100"))
    scope_filter = ctx.accessible_scope_filter()
    result = await asyncio.to_thread(
        EventService.query,
        after_sequence=after_sequence,
        event_type=event_type,
        resource_type=resource_type,
        scope_type=scope_filter.get("scope_type"),
        scope_id=scope_filter.get("scope_id"),
        page_size=page_size,
    )
    return result


@router.get("/stream")
async def event_stream(request: Request):
    from fastapi.responses import StreamingResponse
    import json as _json
    import asyncio

    ctx = get_security_context(request)
    last_event_id = request.headers.get("Last-Event-ID", "0")
    try:
        last_seq = int(last_event_id)
    except ValueError:
        last_seq = 0

    scope_filter = ctx.accessible_scope_filter()
    scope_type = scope_filter.get("scope_type")
    scope_id = scope_filter.get("scope_id")

    async def generate():
        nonlocal last_seq
        while True:
            result = await asyncio.to_thread(
                EventService.query,
                after_sequence=last_seq,
                scope_type=scope_type,
                scope_id=scope_id,
                page_size=50,
            )
            for event in result["items"]:
                last_seq = event["sequence"]
                data = {
                    "event_id": str(event["event_id"]),
                    "event_type": event["event_type"],
                    "sequence": event["sequence"],
                    "scope_type": event["scope_type"],
                    "scope_id": event["scope_id"],
                    "resource_type": event["resource_type"],
                    "resource_id": event["resource_id"],
                    "created_at": event["created_at"].isoformat() if event["created_at"] else None,
                    "payload": event["payload"],
                }
                yield f"id: {last_seq}\nevent: {event['event_type']}\ndata: {_json.dumps(data)}\n\n"
            if not result["items"]:
                yield ": heartbeat\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
