from __future__ import annotations
import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Response
from ..security import get_auth_context
from ..db import get_db
from ..config import S3_BUCKET, TENANT_ID
from ..services.lake_client import lake, MCPError
from ..services.sse_broker import sse_broker
from ..services.pipeline_service import PipelineService

router = APIRouter(prefix="/api/tasks")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _s3_chunk_path(principal_id: str, task_id: str, sequence: int, ext: str = "webm") -> str:
    return f"s3://{S3_BUCKET}/{TENANT_ID}/users/{principal_id}/meetings/{task_id}/audio/chunks/{sequence:06d}.{ext}"


@router.post("/{task_id}/start")
async def start_recording(task_id: str, request: Request):
    ctx = await get_auth_context(request)
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT * FROM meeting_tasks WHERE task_id = ? AND owner_principal_id = ?",
            (task_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
        await db.execute(
            "UPDATE meeting_tasks SET status = 'RECORDING', started_at = ?, updated_at = ? WHERE task_id = ?",
            (_now(), _now(), task_id),
        )
        await db.commit()
        await sse_broker.broadcast(task_id, "task.status_changed", {"status": "RECORDING"})
        return {"status": "RECORDING"}


@router.put("/{task_id}/audio/chunks/{sequence}")
async def upload_chunk(task_id: str, sequence: int, request: Request):
    ctx = await get_auth_context(request)
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="EMPTY_BODY")

    checksum = request.headers.get("X-Chunk-Checksum", "")
    if not checksum:
        checksum = hashlib.sha256(audio).hexdigest()
    duration_ms = int(request.headers.get("X-Chunk-Duration-Ms", "0"))
    mime_type = request.headers.get("Content-Type", "audio/webm")

    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT * FROM meeting_tasks WHERE task_id = ? AND owner_principal_id = ?",
            (task_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")

        existing = await db.execute_fetchall(
            "SELECT * FROM meeting_audio_chunks WHERE task_id = ? AND sequence_no = ?",
            (task_id, sequence),
        )
        if existing:
            if existing[0]["checksum"] == checksum:
                return {"chunk_id": existing[0]["chunk_id"], "sequence": sequence, "duplicate": True}
            raise HTTPException(status_code=409, detail="CHECKSUM_CONFLICT")

        ext = "webm" if "webm" in mime_type else "wav"
        chunk_uri = _s3_chunk_path(ctx.principal_id, task_id, sequence, ext)
        try:
            await lake.s3_put(chunk_uri, audio, token=ctx.token)
        except MCPError as e:
            raise HTTPException(status_code=502, detail=f"音频上传失败 [{e.stage}]: {e.message}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"音频上传失败: {type(e).__name__}: {e}")

        chunk_id = f"chk_{uuid.uuid4().hex[:12]}"
        await db.execute(
            """INSERT INTO meeting_audio_chunks
               (chunk_id, task_id, sequence_no, duration_ms, mime_type, size_bytes, checksum, object_uri, upload_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'UPLOADED', ?)""",
            (chunk_id, task_id, sequence, duration_ms, mime_type, len(audio), checksum, chunk_uri, _now()),
        )
        await db.commit()

        await sse_broker.broadcast(task_id, "chunk.uploaded", {"sequence": sequence, "size": len(audio)})

        asyncio.create_task(PipelineService.run_asr(ctx, task_id, sequence, chunk_uri, chunk_id))

        return {"chunk_id": chunk_id, "sequence": sequence, "size": len(audio)}


@router.post("/{task_id}/stop")
async def stop_recording(task_id: str, request: Request):
    ctx = await get_auth_context(request)
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT * FROM meeting_tasks WHERE task_id = ? AND owner_principal_id = ?",
            (task_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")

        chunks = await db.execute_fetchall(
            "SELECT SUM(duration_ms) as total_ms, COUNT(*) as cnt FROM meeting_audio_chunks WHERE task_id = ?",
            (task_id,),
        )
        total_ms = chunks[0]["total_ms"] or 0 if chunks else 0

        await db.execute(
            "UPDATE meeting_tasks SET status = 'FINALIZING', stopped_at = ?, duration_ms = ?, updated_at = ? WHERE task_id = ?",
            (_now(), total_ms, _now(), task_id),
        )
        await db.commit()

        await sse_broker.broadcast(task_id, "task.status_changed", {"status": "FINALIZING"})

        asyncio.create_task(PipelineService.run_final(ctx, task_id))

        return {"status": "FINALIZING", "duration_ms": total_ms}


@router.post("/{task_id}/audio/upload")
async def upload_recording(task_id: str, request: Request):
    ctx = await get_auth_context(request)
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="EMPTY_BODY")

    mime_type = request.headers.get("Content-Type", "audio/wav")
    ext = "wav"
    if "mp3" in mime_type:
        ext = "mp3"
    elif "m4a" in mime_type:
        ext = "m4a"
    elif "webm" in mime_type:
        ext = "webm"

    checksum = hashlib.sha256(audio).hexdigest()
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT * FROM meeting_tasks WHERE task_id = ? AND owner_principal_id = ?",
            (task_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")

        chunk_uri = _s3_chunk_path(ctx.principal_id, task_id, 1, ext)
        await lake.s3_put(chunk_uri, audio, token=ctx.token)

        chunk_id = f"chk_{uuid.uuid4().hex[:12]}"
        await db.execute(
            """INSERT INTO meeting_audio_chunks
               (chunk_id, task_id, sequence_no, duration_ms, mime_type, size_bytes, checksum, object_uri, upload_status, created_at)
               VALUES (?, ?, 1, 0, ?, ?, ?, ?, 'UPLOADED', ?)""",
            (chunk_id, task_id, mime_type, len(audio), checksum, chunk_uri, _now()),
        )
        await db.execute(
            "UPDATE meeting_tasks SET source_type = 'UPLOAD', status = 'FINALIZING', updated_at = ? WHERE task_id = ?",
            (_now(), task_id),
        )
        await db.commit()

        asyncio.create_task(PipelineService.run_asr(ctx, task_id, 1, chunk_uri, chunk_id))
        asyncio.create_task(PipelineService.run_final(ctx, task_id))

        return {"chunk_id": chunk_id, "size": len(audio)}


@router.get("/{task_id}/audio/manifest")
async def audio_manifest(task_id: str, request: Request):
    ctx = await get_auth_context(request)
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT task_id FROM meeting_tasks WHERE task_id = ? AND owner_principal_id = ?",
            (task_id, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
        chunks = await db.execute_fetchall(
            "SELECT sequence_no, duration_ms, mime_type, size_bytes FROM meeting_audio_chunks WHERE task_id = ? ORDER BY sequence_no",
            (task_id,),
        )
        return {"task_id": task_id, "chunks": [dict(r) for r in chunks]}


@router.get("/{task_id}/audio/chunks/{sequence}")
async def get_chunk_audio(task_id: str, sequence: int, request: Request):
    ctx = await get_auth_context(request)
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT c.* FROM meeting_audio_chunks c "
            "JOIN meeting_tasks t ON c.task_id = t.task_id "
            "WHERE c.task_id = ? AND c.sequence_no = ? AND t.owner_principal_id = ?",
            (task_id, sequence, ctx.principal_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="CHUNK_NOT_FOUND")
        audio = await lake.s3_get(row[0]["object_uri"], token=ctx.token)
        return Response(content=audio, media_type=row[0]["mime_type"] or "audio/webm")
