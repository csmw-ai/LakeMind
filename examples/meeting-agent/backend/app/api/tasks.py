from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Query
from ..security import get_auth_context
from ..db import get_db
from ..services.sse_broker import sse_broker

router = APIRouter(prefix="/api/tasks")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_to_dict(row) -> dict:
    return {
        "task_id": row["task_id"],
        "title": row["title"],
        "participants": json.loads(row["participants"]),
        "remarks": row["remarks"] if "remarks" in row.keys() else "",
        "source_type": row["source_type"],
        "status": row["status"],
        "current_stage": row["current_stage"],
        "template_id": row["template_id"],
        "template_snapshot": json.loads(row["template_snapshot"]),
        "language": row["language"],
        "started_at": row["started_at"],
        "stopped_at": row["stopped_at"],
        "duration_ms": row["duration_ms"],
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("")
async def list_tasks(
    request: Request,
    status: str | None = Query(None),
    source_type: str | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    ctx = await get_auth_context(request)
    async for db in get_db():
        where = "WHERE tenant_id = ? AND owner_principal_id = ?"
        params: list = [ctx.tenant_id, ctx.principal_id]
        if status:
            where += " AND status = ?"
            params.append(status)
        if source_type:
            where += " AND source_type = ?"
            params.append(source_type)
        if q:
            where += " AND title LIKE ?"
            params.append(f"%{q}%")
        offset = (page - 1) * page_size
        rows = await db.execute_fetchall(
            f"SELECT * FROM meeting_tasks {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, page_size, offset),
        )
        count_row = await db.execute_fetchall(
            f"SELECT COUNT(*) as cnt FROM meeting_tasks {where}", params
        )
        total = count_row[0]["cnt"] if count_row else 0
        return {"items": [_task_to_dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.post("")
async def create_task(request: Request):
    ctx = await get_auth_context(request)
    body = await request.json()
    async for db in get_db():
        task_id = f"meeting-{uuid.uuid4().hex[:12]}"
        now = _now()
        template_snapshot = json.dumps(body.get("template_snapshot", {}))
        await db.execute(
            """INSERT INTO meeting_tasks
               (task_id, tenant_id, owner_principal_id, title, participants, source_type,
                status, template_id, template_snapshot, language, remarks, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?, ?, ?, ?, ?)""",
            (task_id, ctx.tenant_id, ctx.principal_id,
             body.get("title", "未命名会议"),
             json.dumps(body.get("participants", [])),
             body.get("source_type", "LIVE"),
             body.get("template_id"),
             template_snapshot,
             body.get("language", "zh"),
             body.get("remarks", ""),
             now, now),
        )
        await db.commit()
        return {"task_id": task_id, "status": "DRAFT"}


@router.get("/{task_id}")
async def get_task(task_id: str, request: Request):
    ctx = await get_auth_context(request)
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT * FROM meeting_tasks WHERE task_id = ? AND owner_principal_id = ?",
            (task_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
        return _task_to_dict(row[0])


@router.patch("/{task_id}")
async def update_task(task_id: str, request: Request):
    ctx = await get_auth_context(request)
    body = await request.json()
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT * FROM meeting_tasks WHERE task_id = ? AND owner_principal_id = ?",
            (task_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
        updates = []
        params = []
        for field in ("title", "participants", "status", "current_stage", "error_message", "remarks"):
            if field in body:
                updates.append(f"{field} = ?")
                params.append(json.dumps(body[field]) if field == "participants" else body[field])
        if "template_snapshot" in body:
            updates.append("template_snapshot = ?")
            params.append(json.dumps(body["template_snapshot"]))
        if updates:
            updates.append("updated_at = ?")
            params.append(_now())
            params.extend([task_id, ctx.principal_id])
            await db.execute(
                f"UPDATE meeting_tasks SET {', '.join(updates)} WHERE task_id = ? AND owner_principal_id = ?",
                params,
            )
            await db.commit()
        return {"ok": True}


@router.delete("/{task_id}")
async def delete_task(task_id: str, request: Request):
    ctx = await get_auth_context(request)
    from ..services.lake_client import lake
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT * FROM meeting_tasks WHERE task_id = ? AND owner_principal_id = ?",
            (task_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")

        chunks = await db.execute_fetchall(
            "SELECT object_uri FROM meeting_audio_chunks WHERE task_id = ?", (task_id,)
        )
        for chunk in chunks:
            try:
                await lake.s3_delete(chunk["object_uri"], token=ctx.token)
            except Exception:
                pass

        await db.execute("DELETE FROM meeting_audio_chunks WHERE task_id = ?", (task_id,))
        await db.execute("DELETE FROM meeting_stage_runs WHERE task_id = ?", (task_id,))
        await db.execute("DELETE FROM meeting_transcript_segments WHERE task_id = ?", (task_id,))
        await db.execute("DELETE FROM meeting_minutes_versions WHERE task_id = ?", (task_id,))
        await db.execute("DELETE FROM meeting_knowledge_items WHERE task_id = ?", (task_id,))
        await db.execute("DELETE FROM meeting_tasks WHERE task_id = ?", (task_id,))
        await db.commit()
        return {"ok": True}


@router.get("/{task_id}/events")
async def task_events(task_id: str, request: Request):
    from fastapi.responses import StreamingResponse
    ctx = await get_auth_context(request)
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT task_id FROM meeting_tasks WHERE task_id = ? AND owner_principal_id = ?",
            (task_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")

    queue = sse_broker.subscribe(task_id)

    async def event_stream():
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            sse_broker.unsubscribe(task_id, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


import asyncio
