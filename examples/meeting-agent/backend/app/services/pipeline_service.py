from __future__ import annotations
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from ..security import AuthContext
from ..db import get_db
from ..config import SKILL_REF, SUMMARIZE_INTERVAL, S3_BUCKET, TENANT_ID
from ..services.lake_client import lake, MCPError
from ..services.sse_broker import sse_broker

logger = logging.getLogger("meeting-agent")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineService:

    @staticmethod
    async def run_asr(ctx: AuthContext, task_id: str, sequence: int, chunk_uri: str, chunk_id: str):
        try:
            async for db in get_db():
                await db.execute(
                    "UPDATE meeting_audio_chunks SET asr_status = 'RUNNING' WHERE chunk_id = ?", (chunk_id,)
                )
                await db.commit()

            stage_run_id = f"sr_{uuid.uuid4().hex[:12]}"
            async for db in get_db():
                await db.execute(
                    """INSERT INTO meeting_stage_runs (stage_run_id, task_id, stage, status, started_at, created_at)
                       VALUES (?, ?, 'asr', 'RUNNING', ?, ?)""",
                    (stage_run_id, task_id, _now(), _now()),
                )
                await db.commit()

            job = await lake.submit_job(
                skill_ref=SKILL_REF,
                inputs={"chunk_uri": chunk_uri, "result_key": f"asr/{sequence}"},
                model_profile="meeting-asr",
                idempotency_key=f"asr-{task_id}-{sequence}",
                token=ctx.token,
            )
            job_id = job["job_id"]

            async for db in get_db():
                await db.execute(
                    "UPDATE meeting_stage_runs SET job_id = ? WHERE stage_run_id = ?",
                    (job_id, stage_run_id),
                )
                await db.commit()

            await PipelineService._poll_job(job_id, ctx)

            result_uri = chunk_uri.rsplit("/audio/chunks/", 1)[0] + f"/results/asr/{sequence}.json"
            result_raw = await lake.s3_get(result_uri, token=ctx.token)
            result = json.loads(result_raw)
            segments = result.get("segments", [])
            text = result.get("text", "")

            async for db in get_db():
                for seg in segments:
                    seg_id = f"seg_{uuid.uuid4().hex[:12]}"
                    await db.execute(
                        """INSERT INTO meeting_transcript_segments
                           (segment_id, task_id, chunk_sequence, start_ms, end_ms, speaker_label,
                            original_text, confidence, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (seg_id, task_id, sequence,
                         seg.get("start_ms", 0), seg.get("end_ms", 0),
                         seg.get("speaker", ""),
                         seg.get("text", text), seg.get("confidence", 0.9),
                         _now(), _now()),
                    )
                if not segments and text:
                    seg_id = f"seg_{uuid.uuid4().hex[:12]}"
                    await db.execute(
                        """INSERT INTO meeting_transcript_segments
                           (segment_id, task_id, chunk_sequence, original_text, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (seg_id, task_id, sequence, text, _now(), _now()),
                    )
                await db.execute(
                    "UPDATE meeting_audio_chunks SET asr_status = 'SUCCEEDED' WHERE chunk_id = ?", (chunk_id,)
                )
                await db.execute(
                    "UPDATE meeting_stage_runs SET status = 'SUCCEEDED', finished_at = ? WHERE stage_run_id = ?",
                    (_now(), stage_run_id),
                )
                await db.commit()

            await sse_broker.broadcast(task_id, "transcript.segment_ready", {
                "sequence": sequence, "text": text, "segments": segments,
            })

            if sequence % SUMMARIZE_INTERVAL == 0:
                asyncio.create_task(PipelineService._run_minutes_live(ctx, task_id))

        except Exception as e:
            err_msg = str(e)
            if isinstance(e, MCPError):
                err_msg = f"ASR MCP调用失败 [{e.stage}]: {e.message}"
            else:
                err_msg = f"ASR处理失败: {type(e).__name__}: {e}"
            logger.error(f"ASR failed for task={task_id} seq={sequence}: {err_msg}")
            async for db in get_db():
                await db.execute(
                    "UPDATE meeting_audio_chunks SET asr_status = 'FAILED' WHERE chunk_id = ?", (chunk_id,)
                )
                await db.execute(
                    "UPDATE meeting_stage_runs SET status = 'FAILED', error_message = ?, finished_at = ? WHERE stage_run_id = ?",
                    (err_msg, _now(), stage_run_id),
                )
                await db.commit()
            await sse_broker.broadcast(task_id, "error", {"stage": "asr", "sequence": sequence, "message": err_msg})

    @staticmethod
    async def _run_minutes_live(ctx: AuthContext, task_id: str):
        try:
            suffix = str(int(datetime.now(timezone.utc).timestamp()))
            await PipelineService._run_minutes(ctx, task_id, idempotency_suffix=suffix)
            await PipelineService._run_knowledge_extract(ctx, task_id, idempotency_suffix=suffix)
        except Exception as e:
            logger.warning(f"Live minutes/knowledge failed for task={task_id}: {e}")

    @staticmethod
    async def run_final(ctx: AuthContext, task_id: str):
        try:
            await asyncio.sleep(2)

            await PipelineService._run_minutes(ctx, task_id)
            await PipelineService._run_knowledge_extract(ctx, task_id)
            await PipelineService._run_memory(ctx, task_id)

            async for db in get_db():
                await db.execute(
                    "UPDATE meeting_tasks SET status = 'REVIEW_REQUIRED', updated_at = ? WHERE task_id = ?",
                    (_now(), task_id),
                )
                await db.commit()
            await sse_broker.broadcast(task_id, "task.status_changed", {"status": "REVIEW_REQUIRED"})

        except Exception as e:
            err_msg = str(e)
            if isinstance(e, MCPError):
                err_msg = f"纪要/知识生成失败 [{e.stage}]: {e.message}"
            else:
                err_msg = f"后处理失败: {type(e).__name__}: {e}"
            logger.error(f"Final pipeline failed for task={task_id}: {err_msg}")
            async for db in get_db():
                await db.execute(
                    "UPDATE meeting_tasks SET status = 'FAILED', error_message = ?, updated_at = ? WHERE task_id = ?",
                    (err_msg, _now(), task_id),
                )
                await db.commit()
            await sse_broker.broadcast(task_id, "error", {"stage": "final", "message": err_msg})

    @staticmethod
    async def _run_minutes(ctx: AuthContext, task_id: str, idempotency_suffix: str = ""):
        async for db in get_db():
            segs = await db.execute_fetchall(
                "SELECT original_text, edited_text FROM meeting_transcript_segments WHERE task_id = ? ORDER BY start_ms",
                (task_id,),
            )
            task = await db.execute_fetchall(
                "SELECT title, template_snapshot FROM meeting_tasks WHERE task_id = ?", (task_id,)
            )
            if not segs or not task:
                return

            transcript_text = " ".join(
                (r["edited_text"] or r["original_text"]) for r in segs
            )
            template = json.loads(task[0]["template_snapshot"])
            title = task[0]["title"]

            stage_run_id = f"sr_{uuid.uuid4().hex[:12]}"
            await db.execute(
                """INSERT INTO meeting_stage_runs (stage_run_id, task_id, stage, status, started_at, created_at)
                   VALUES (?, ?, 'minutes_generate', 'RUNNING', ?, ?)""",
                (stage_run_id, task_id, _now(), _now()),
            )
            await db.commit()

        job = await lake.submit_job(
            skill_ref=SKILL_REF,
            inputs={
                "transcript": transcript_text,
                "meeting_title": title,
                "template_snapshot": template,
                "result_key": "minutes",
                "result_uri": f"s3://{S3_BUCKET}/{TENANT_ID}/users/{ctx.principal_id}/meetings/{task_id}/results/minutes.json",
            },
            model_profile="meeting-minutes",
            idempotency_key=f"minutes-{task_id}-{idempotency_suffix}" if idempotency_suffix else f"minutes-{task_id}",
            token=ctx.token,
        )
        await PipelineService._poll_job(job["job_id"], ctx)

        result_uri = f"s3://{S3_BUCKET}/{TENANT_ID}/users/{ctx.principal_id}/meetings/{task_id}/results/minutes.json"
        result_raw = await lake.s3_get(result_uri, token=ctx.token)
        result = json.loads(result_raw)
        minutes_md = result.get("minutes", "")

        async for db in get_db():
            version = await db.execute_fetchall(
                "SELECT COUNT(*) + 1 as v FROM meeting_minutes_versions WHERE task_id = ?", (task_id,)
            )
            ver = version[0]["v"] if version else 1
            mv_id = f"mv_{uuid.uuid4().hex[:12]}"
            await db.execute(
                """INSERT INTO meeting_minutes_versions (minutes_version_id, task_id, version, content_markdown, status, created_at)
                   VALUES (?, ?, ?, ?, 'FINAL', ?)""",
                (mv_id, task_id, ver, minutes_md, _now()),
            )
            await db.execute(
                "UPDATE meeting_stage_runs SET status = 'SUCCEEDED', job_id = ?, finished_at = ? WHERE stage_run_id = ?",
                (job["job_id"], _now(), stage_run_id),
            )
            await db.commit()

        await sse_broker.broadcast(task_id, "minutes.preview_ready", {"version": ver})

    @staticmethod
    async def _run_knowledge_extract(ctx: AuthContext, task_id: str, idempotency_suffix: str = ""):
        async for db in get_db():
            segs = await db.execute_fetchall(
                "SELECT original_text, edited_text, segment_id, start_ms, end_ms FROM meeting_transcript_segments WHERE task_id = ? ORDER BY start_ms",
                (task_id,),
            )
            minutes = await db.execute_fetchall(
                "SELECT content_markdown FROM meeting_minutes_versions WHERE task_id = ? ORDER BY version DESC LIMIT 1",
                (task_id,),
            )
            task = await db.execute_fetchall(
                "SELECT title, template_snapshot FROM meeting_tasks WHERE task_id = ?", (task_id,)
            )
            if not task:
                return

            transcript_text = " ".join((r["edited_text"] or r["original_text"]) for r in segs)
            minutes_md = minutes[0]["content_markdown"] if minutes else ""
            template = json.loads(task[0]["template_snapshot"])

            stage_run_id = f"sr_{uuid.uuid4().hex[:12]}"
            await db.execute(
                """INSERT INTO meeting_stage_runs (stage_run_id, task_id, stage, status, started_at, created_at)
                   VALUES (?, ?, 'knowledge_extract', 'RUNNING', ?, ?)""",
                (stage_run_id, task_id, _now(), _now()),
            )
            await db.commit()

        job = await lake.submit_job(
            skill_ref=SKILL_REF,
            inputs={
                "transcript": transcript_text,
                "minutes": minutes_md,
                "template_snapshot": template,
                "result_key": "knowledge",
                "result_uri": f"s3://{S3_BUCKET}/{TENANT_ID}/users/{ctx.principal_id}/meetings/{task_id}/results/knowledge.json",
            },
            model_profile="meeting-knowledge-extract",
            idempotency_key=f"knowledge-{task_id}-{idempotency_suffix}" if idempotency_suffix else f"knowledge-{task_id}",
            token=ctx.token,
        )
        await PipelineService._poll_job(job["job_id"], ctx)

        result_uri = f"s3://{S3_BUCKET}/{TENANT_ID}/users/{ctx.principal_id}/meetings/{task_id}/results/knowledge.json"
        result_raw = await lake.s3_get(result_uri, token=ctx.token)
        result = json.loads(result_raw)
        items = result.get("items", [])

        async for db in get_db():
            for item in items:
                item_id = f"ki_{uuid.uuid4().hex[:12]}"
                await db.execute(
                    """INSERT INTO meeting_knowledge_items
                       (item_id, task_id, item_type, title, body, tags, evidence_segment_ids,
                        evidence_start_ms, evidence_end_ms, confidence, review_status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?)""",
                    (item_id, task_id, item.get("type", "fact"),
                     item.get("title", ""), item.get("body", ""),
                     json.dumps(item.get("tags", [])),
                     json.dumps(item.get("evidence", {}).get("segment_ids", [])),
                     item.get("evidence", {}).get("start_ms"),
                     item.get("evidence", {}).get("end_ms"),
                     item.get("confidence", 0.8),
                     _now(), _now()),
                )
            await db.execute(
                "UPDATE meeting_stage_runs SET status = 'SUCCEEDED', job_id = ?, finished_at = ? WHERE stage_run_id = ?",
                (job["job_id"], _now(), stage_run_id),
            )
            await db.commit()

        await sse_broker.broadcast(task_id, "knowledge.draft_ready", {"count": len(items)})

    @staticmethod
    async def _run_memory(ctx: AuthContext, task_id: str):
        try:
            async for db in get_db():
                task = await db.execute_fetchall(
                    "SELECT title, duration_ms FROM meeting_tasks WHERE task_id = ?", (task_id,)
                )
                if not task:
                    return
                title = task[0]["title"]
                duration = task[0]["duration_ms"] or 0

            await lake.memory_add(
                messages=[{
                    "role": "user",
                    "content": f"会议 '{title}' 已结束，时长 {duration // 1000}s。",
                }],
                metadata={"meeting_id": task_id, "title": title},
                token=ctx.token,
            )
        except Exception:
            pass

    @staticmethod
    async def _poll_job(job_id: str, ctx: AuthContext, timeout: float = 900) -> dict:
        elapsed = 0.0
        while elapsed < timeout:
            job = await lake.get_job(job_id, token=ctx.token)
            status = job.get("status", "")
            if status in ("SUCCEEDED", "COMPLETED", "completed"):
                result = await lake.get_job_result(job_id, token=ctx.token)
                return result.get("result", result)
            if status in ("FAILED", "CANCELLED", "LOST", "TIMED_OUT"):
                raise RuntimeError(f"Job {job_id} status: {status}")
            await asyncio.sleep(2)
            elapsed += 2
        raise RuntimeError(f"Job {job_id} timed out")
