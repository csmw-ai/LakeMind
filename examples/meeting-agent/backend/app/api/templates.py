from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from ..security import get_auth_context
from ..db import get_db

router = APIRouter(prefix="/api/templates")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


BUILTIN_TEMPLATES = [
    {
        "name": "通用会议",
        "config": {
            "transcription": {"language": "zh", "timestamps": "segment", "punctuation": True, "speaker_diarization": False},
            "minutes": {"preset": "general", "sections": ["会议摘要", "关键决策", "行动项", "讨论要点", "待解决问题"]},
            "knowledge": {"enabled_types": ["process", "rule", "insight", "risk", "case", "concept"], "auto_publish": False},
        },
    },
    {
        "name": "项目评审",
        "config": {
            "transcription": {"language": "zh", "timestamps": "segment", "punctuation": True},
            "minutes": {"preset": "project_review", "sections": ["目标", "当前进展", "评审结论", "问题", "风险", "行动项"]},
            "knowledge": {"enabled_types": ["process", "insight", "risk", "case"], "auto_publish": False},
        },
    },
    {
        "name": "需求访谈",
        "config": {
            "transcription": {"language": "zh", "timestamps": "segment", "punctuation": True},
            "minutes": {"preset": "requirement", "sections": ["业务背景", "用户角色", "现状问题", "需求", "规则", "约束", "未确认问题"]},
            "knowledge": {"enabled_types": ["rule", "concept", "process"], "auto_publish": False},
        },
    },
    {
        "name": "客户沟通",
        "config": {
            "transcription": {"language": "zh", "timestamps": "segment", "punctuation": True},
            "minutes": {"preset": "customer", "sections": ["客户背景", "核心诉求", "反馈", "承诺事项", "商机", "后续动作"]},
            "knowledge": {"enabled_types": ["process", "concept", "rule"], "auto_publish": False},
        },
    },
    {
        "name": "事故复盘",
        "config": {
            "transcription": {"language": "zh", "timestamps": "segment", "punctuation": True},
            "minutes": {"preset": "postmortem", "sections": ["事故摘要", "时间线", "影响", "已知原因", "处置", "改进项", "待验证假设"]},
            "knowledge": {"enabled_types": ["case", "process", "risk"], "auto_publish": False},
        },
    },
]


async def seed_builtin_templates():
    async for db in get_db():
        for tmpl in BUILTIN_TEMPLATES:
            existing = await db.execute_fetchall(
                "SELECT template_id FROM meeting_templates WHERE name = ? AND is_builtin = 1",
                (tmpl["name"],),
            )
            now = _now()
            if existing:
                template_id = existing[0]["template_id"]
                await db.execute(
                    "UPDATE meeting_template_versions SET config_json = ? WHERE template_id = ? AND version = 1",
                    (json.dumps(tmpl["config"]), template_id),
                )
                await db.execute(
                    "UPDATE meeting_templates SET updated_at = ? WHERE template_id = ?",
                    (now, template_id),
                )
                continue
            template_id = f"tpl_{uuid.uuid4().hex[:12]}"
            await db.execute(
                """INSERT INTO meeting_templates (template_id, tenant_id, name, status, current_version, is_builtin, created_at, updated_at)
                   VALUES (?, 'examples-meeting-agent', ?, 'ACTIVE', 1, 1, ?, ?)""",
                (template_id, tmpl["name"], now, now),
            )
            tv_id = f"tv_{uuid.uuid4().hex[:12]}"
            await db.execute(
                """INSERT INTO meeting_template_versions (template_version_id, template_id, version, config_json, created_at)
                   VALUES (?, ?, 1, ?, ?)""",
                (tv_id, template_id, json.dumps(tmpl["config"]), now),
            )
        await db.commit()


@router.get("")
async def list_templates(request: Request):
    ctx = await get_auth_context(request)
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT * FROM meeting_templates WHERE tenant_id = ? AND (owner_principal_id = ? OR is_builtin = 1) AND status = 'ACTIVE' ORDER BY is_builtin DESC, name",
            (ctx.tenant_id, ctx.principal_id),
        )
        result = []
        for r in rows:
            d = dict(r)
            latest = await db.execute_fetchall(
                "SELECT config_json FROM meeting_template_versions WHERE template_id = ? ORDER BY version DESC LIMIT 1",
                (r["template_id"],),
            )
            d["config"] = json.loads(latest[0]["config_json"]) if latest else {}
            result.append(d)
        return {"items": result}


@router.post("")
async def create_template(request: Request):
    ctx = await get_auth_context(request)
    body = await request.json()
    async for db in get_db():
        template_id = f"tpl_{uuid.uuid4().hex[:12]}"
        now = _now()
        await db.execute(
            """INSERT INTO meeting_templates (template_id, tenant_id, owner_principal_id, name, description, status, current_version, is_builtin, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'ACTIVE', 1, 0, ?, ?)""",
            (template_id, ctx.tenant_id, ctx.principal_id,
             body.get("name", ""), body.get("description", ""), now, now),
        )
        tv_id = f"tv_{uuid.uuid4().hex[:12]}"
        await db.execute(
            """INSERT INTO meeting_template_versions (template_version_id, template_id, version, config_json, created_by, created_at)
               VALUES (?, ?, 1, ?, ?, ?)""",
            (tv_id, template_id, json.dumps(body.get("config", {})), ctx.principal_id, now),
        )
        await db.commit()
        return {"template_id": template_id, "status": "ACTIVE"}


@router.post("/{template_id}/clone")
async def clone_template(template_id: str, request: Request):
    ctx = await get_auth_context(request)
    async for db in get_db():
        orig = await db.execute_fetchall(
            "SELECT * FROM meeting_templates WHERE template_id = ? AND status = 'ACTIVE'",
            (template_id,),
        )
        if not orig:
            raise HTTPException(status_code=404, detail="TEMPLATE_NOT_FOUND")
        latest = await db.execute_fetchall(
            "SELECT config_json FROM meeting_template_versions WHERE template_id = ? ORDER BY version DESC LIMIT 1",
            (template_id,),
        )
        config = latest[0]["config_json"] if latest else "{}"
        new_id = f"tpl_{uuid.uuid4().hex[:12]}"
        now = _now()
        await db.execute(
            """INSERT INTO meeting_templates (template_id, tenant_id, owner_principal_id, name, description, status, current_version, is_builtin, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'ACTIVE', 1, 0, ?, ?)""",
            (new_id, ctx.tenant_id, ctx.principal_id,
             f"{orig[0]['name']} (副本)", orig[0]["description"] or "", now, now),
        )
        tv_id = f"tv_{uuid.uuid4().hex[:12]}"
        await db.execute(
            """INSERT INTO meeting_template_versions (template_version_id, template_id, version, config_json, created_by, created_at)
               VALUES (?, ?, 1, ?, ?, ?)""",
            (tv_id, new_id, config, ctx.principal_id, now),
        )
        await db.commit()
        return {"template_id": new_id}


@router.post("/{template_id}/archive")
async def archive_template(template_id: str, request: Request):
    ctx = await get_auth_context(request)
    async for db in get_db():
        await db.execute(
            "UPDATE meeting_templates SET status = 'ARCHIVED', updated_at = ? WHERE template_id = ? AND owner_principal_id = ?",
            (_now(), template_id, ctx.principal_id),
        )
        await db.commit()
        return {"ok": True}
