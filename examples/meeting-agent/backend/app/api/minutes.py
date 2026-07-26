from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException
from ..security import get_auth_context
from ..db import get_db

router = APIRouter(prefix="/api/tasks")


@router.get("/{task_id}/minutes")
async def get_minutes(task_id: str, request: Request):
    ctx = await get_auth_context(request)
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT task_id FROM meeting_tasks WHERE task_id = ? AND owner_principal_id = ?",
            (task_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
        versions = await db.execute_fetchall(
            "SELECT * FROM meeting_minutes_versions WHERE task_id = ? ORDER BY version DESC",
            (task_id,),
        )
        return {"versions": [dict(r) for r in versions]}


@router.patch("/{task_id}/minutes")
async def edit_minutes(task_id: str, request: Request):
    from datetime import datetime, timezone
    ctx = await get_auth_context(request)
    body = await request.json()
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT task_id FROM meeting_tasks WHERE task_id = ? AND owner_principal_id = ?",
            (task_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
        latest = await db.execute_fetchall(
            "SELECT version FROM meeting_minutes_versions WHERE task_id = ? ORDER BY version DESC LIMIT 1",
            (task_id,),
        )
        ver = (latest[0]["version"] + 1) if latest else 1
        import uuid
        mv_id = f"mv_{uuid.uuid4().hex[:12]}"
        await db.execute(
            """INSERT INTO meeting_minutes_versions (minutes_version_id, task_id, version, content_markdown, status, created_at)
               VALUES (?, ?, ?, ?, 'FINAL', ?)""",
            (mv_id, task_id, ver, body.get("content", ""), datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
        return {"version": ver}
