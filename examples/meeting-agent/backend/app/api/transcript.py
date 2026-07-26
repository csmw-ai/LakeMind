from __future__ import annotations
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from ..security import get_auth_context
from ..db import get_db

router = APIRouter(prefix="/api/tasks")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/{task_id}/transcript")
async def get_transcript(task_id: str, request: Request):
    ctx = await get_auth_context(request)
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT task_id FROM meeting_tasks WHERE task_id = ? AND owner_principal_id = ?",
            (task_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
        segs = await db.execute_fetchall(
            "SELECT * FROM meeting_transcript_segments WHERE task_id = ? ORDER BY start_ms",
            (task_id,),
        )
        return {"segments": [dict(r) for r in segs]}


@router.patch("/{task_id}/transcript/segments/{segment_id}")
async def edit_segment(task_id: str, segment_id: str, request: Request):
    ctx = await get_auth_context(request)
    body = await request.json()
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT s.* FROM meeting_transcript_segments s "
            "JOIN meeting_tasks t ON s.task_id = t.task_id "
            "WHERE s.segment_id = ? AND t.owner_principal_id = ?",
            (segment_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="SEGMENT_NOT_FOUND")
        await db.execute(
            "UPDATE meeting_transcript_segments SET edited_text = ?, revision = revision + 1, updated_at = ? WHERE segment_id = ?",
            (body.get("text", ""), _now(), segment_id),
        )
        await db.commit()
        return {"ok": True}
