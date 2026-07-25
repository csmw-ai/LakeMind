from __future__ import annotations
import asyncio
import json
import hashlib
import ulid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from ..security.middleware import get_security_context
from ..db import execute, execute_one

router = APIRouter()


def _ulid(prefix: str) -> str:
    return f"{prefix}_{str(ulid.new())}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(category: str, affected_objects: list, title: str) -> str:
    raw = f"{category}:{json.dumps(affected_objects, sort_keys=True)}:{title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class StewardFindingService:

    @staticmethod
    def upsert(category: str, severity: str, title: str,
               evidence: list | None = None, affected_objects: list | None = None,
               suggested_action: str | None = None, confidence: str | None = None) -> dict:
        fp = _fingerprint(category, affected_objects or [], title)
        existing = execute_one(
            "SELECT id, occurrence_count FROM steward_findings WHERE fingerprint = %s AND status = 'OPEN'",
            (fp,),
        )
        now = _now()
        if existing:
            execute(
                "UPDATE steward_findings SET occurrence_count = occurrence_count + 1, last_seen_at = %s, "
                "evidence = %s::jsonb, updated_at = %s WHERE id = %s",
                (now, json.dumps(evidence or []), now, existing["id"]),
            )
            return {"id": existing["id"], "fingerprint": fp, "occurrence_count": existing["occurrence_count"] + 1}
        finding_id = _ulid("fnd")
        execute(
            "INSERT INTO steward_findings (id, category, severity, title, evidence, affected_objects, "
            "suggested_action, confidence, fingerprint, status, first_seen_at, last_seen_at) "
            "VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, 'OPEN', %s, %s)",
            (finding_id, category, severity, title, json.dumps(evidence or []),
             json.dumps(affected_objects or []), suggested_action, confidence, fp, now, now),
        )
        return {"id": finding_id, "fingerprint": fp, "occurrence_count": 1}

    @staticmethod
    def list(status: str | None = None, severity: str | None = None,
             page: int = 1, page_size: int = 50) -> dict:
        query = "SELECT * FROM steward_findings WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = %s"; params.append(status)
        if severity:
            query += " AND severity = %s"; params.append(severity)
        query += " ORDER BY last_seen_at DESC"
        items = execute(query, tuple(params) if params else None)
        total = len(items)
        offset = (page - 1) * page_size
        return {"items": items[offset:offset + page_size], "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def acknowledge(finding_id: str, principal_id: str) -> dict:
        row = execute_one("SELECT status FROM steward_findings WHERE id = %s", (finding_id,))
        if row is None:
            raise ValueError("FINDING_NOT_FOUND")
        if row["status"] != "OPEN":
            raise ValueError(f"Cannot acknowledge finding in status: {row['status']}")
        execute(
            "UPDATE steward_findings SET status = 'ACKNOWLEDGED', acknowledged_by = %s, acknowledged_at = %s, updated_at = %s WHERE id = %s",
            (principal_id, _now(), _now(), finding_id),
        )
        return {"id": finding_id, "status": "ACKNOWLEDGED"}

    @staticmethod
    def resolve(finding_id: str, note: str | None = None) -> dict:
        execute(
            "UPDATE steward_findings SET status = 'RESOLVED', resolved_at = %s, resolution_note = %s, updated_at = %s WHERE id = %s",
            (_now(), note, _now(), finding_id),
        )
        return {"id": finding_id, "status": "RESOLVED"}

    @staticmethod
    def suppress(finding_id: str) -> dict:
        execute(
            "UPDATE steward_findings SET status = 'SUPPRESSED', updated_at = %s WHERE id = %s",
            (_now(), finding_id),
        )
        return {"id": finding_id, "status": "SUPPRESSED"}


@router.get("/findings")
async def list_findings(request: Request):
    ctx = get_security_context(request)
    params = request.query_params
    return await asyncio.to_thread(
        StewardFindingService.list,
        status=params.get("status"),
        severity=params.get("severity"),
        page=int(params.get("page", "1")),
        page_size=int(params.get("page_size", "50")),
    )


@router.post("/findings/{finding_id}/acknowledge")
async def acknowledge_finding(finding_id: str, request: Request):
    ctx = get_security_context(request)
    try:
        return await asyncio.to_thread(StewardFindingService.acknowledge, finding_id, ctx.principal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/findings/{finding_id}/resolve")
async def resolve_finding(finding_id: str, request: Request):
    ctx = get_security_context(request)
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    return await asyncio.to_thread(StewardFindingService.resolve, finding_id, body.get("note"))


@router.post("/findings/{finding_id}/suppress")
async def suppress_finding(finding_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(StewardFindingService.suppress, finding_id)
