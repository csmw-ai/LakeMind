from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from ..security import get_auth_context
from ..db import get_db
from ..services.lake_client import lake

router = APIRouter(prefix="/api/tasks")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/{task_id}/knowledge")
async def get_knowledge(task_id: str, request: Request):
    ctx = await get_auth_context(request)
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT task_id FROM meeting_tasks WHERE task_id = ? AND owner_principal_id = ?",
            (task_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
        items = await db.execute_fetchall(
            "SELECT * FROM meeting_knowledge_items WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        )
        result = []
        for r in items:
            d = dict(r)
            d["tags"] = json.loads(d["tags"] or "[]")
            d["evidence_segment_ids"] = json.loads(d["evidence_segment_ids"] or "[]")
            result.append(d)
        return {"items": result}


@router.patch("/{task_id}/knowledge/{item_id}")
async def edit_knowledge_item(task_id: str, item_id: str, request: Request):
    ctx = await get_auth_context(request)
    body = await request.json()
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT k.* FROM meeting_knowledge_items k "
            "JOIN meeting_tasks t ON k.task_id = t.task_id "
            "WHERE k.item_id = ? AND t.owner_principal_id = ?",
            (item_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="ITEM_NOT_FOUND")
        updates = []
        params = []
        for field in ("title", "body", "item_type"):
            if field in body:
                updates.append(f"{field} = ?")
                params.append(body[field])
        if "tags" in body:
            updates.append("tags = ?")
            params.append(json.dumps(body["tags"]))
        if updates:
            updates.append("updated_at = ?")
            params.append(_now())
            params.append(item_id)
            await db.execute(f"UPDATE meeting_knowledge_items SET {', '.join(updates)} WHERE item_id = ?", params)
            await db.commit()
        return {"ok": True}


@router.post("/{task_id}/knowledge/{item_id}/accept")
async def accept_item(task_id: str, item_id: str, request: Request):
    ctx = await get_auth_context(request)
    async for db in get_db():
        await db.execute(
            "UPDATE meeting_knowledge_items SET review_status = 'ACCEPTED', reviewed_at = ? WHERE item_id = ?",
            (_now(), item_id),
        )
        await db.commit()
        return {"review_status": "ACCEPTED"}


@router.post("/{task_id}/knowledge/{item_id}/reject")
async def reject_item(task_id: str, item_id: str, request: Request):
    ctx = await get_auth_context(request)
    async for db in get_db():
        await db.execute(
            "UPDATE meeting_knowledge_items SET review_status = 'REJECTED', reviewed_at = ? WHERE item_id = ?",
            (_now(), item_id),
        )
        await db.commit()
        return {"review_status": "REJECTED"}


@router.post("/{task_id}/knowledge/publish")
async def publish_knowledge(task_id: str, request: Request):
    ctx = await get_auth_context(request)
    async for db in get_db():
        items = await db.execute_fetchall(
            "SELECT * FROM meeting_knowledge_items WHERE task_id = ? AND review_status = 'ACCEPTED'",
            (task_id,),
        )
        if not items:
            raise HTTPException(status_code=400, detail="NO_ACCEPTED_ITEMS")

        published = []
        for item in items:
            content = f"# {item['title']}\n\n{item['body']}"
            try:
                result = await lake.knowledge_ingest(
                    name=item["title"],
                    content=content,
                    kb_name="meetings",
                    token=ctx.token,
                )
                await db.execute(
                    "UPDATE meeting_knowledge_items SET review_status = 'PUBLISHED', reviewed_at = ? WHERE item_id = ?",
                    (_now(), item["item_id"]),
                )
                published.append({"item_id": item["item_id"], "asset_id": result.get("asset_id")})
            except Exception as e:
                published.append({"item_id": item["item_id"], "error": str(e)})

        await db.commit()
        return {"published": published}


@router.post("/{task_id}/knowledge/reextract")
async def reextract(task_id: str, request: Request):
    ctx = await get_auth_context(request)
    from ..services.pipeline_service import PipelineService
    async for db in get_db():
        await db.execute("DELETE FROM meeting_knowledge_items WHERE task_id = ? AND review_status = 'DRAFT'", (task_id,))
        await db.commit()
    asyncio.create_task(PipelineService._run_knowledge_extract(ctx, task_id))
    return {"ok": True}


import asyncio
