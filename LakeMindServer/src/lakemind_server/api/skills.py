from __future__ import annotations
import asyncio
from fastapi import APIRouter, Request
from ..security.middleware import get_security_context
from ..security.actions import Action
from ..services.skill_service import SkillService

router = APIRouter()


@router.post("/register")
async def register_skill(request: Request):
    ctx = get_security_context(request)
    if not ctx.has_scope(Action.ASSET_CREATE.value):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="PERMISSION_DENIED")
    body = await request.json()
    return await asyncio.to_thread(SkillService.register, ctx, **body)


@router.post("/{skill_id}/validate")
async def validate_skill(skill_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(SkillService.validate, ctx, skill_id)


@router.post("/{skill_id}/publish")
async def publish_skill(skill_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(SkillService.publish, ctx, skill_id)


@router.post("/{skill_id}/revoke")
async def revoke_skill(skill_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(SkillService.revoke, ctx, skill_id)


@router.get("/{skill_id}")
async def get_skill(skill_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(SkillService.get_skill, ctx, skill_id)


@router.get("")
async def list_skills(request: Request):
    ctx = get_security_context(request)
    params = request.query_params
    return await asyncio.to_thread(
        SkillService.list_skills,
        ctx,
        publish_status=params.get("status"),
        page=int(params.get("page", "1")),
        page_size=int(params.get("page_size", "50")),
    )


@router.get("/{skill_id}/executable")
async def check_executable(skill_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(SkillService.is_executable, ctx, skill_id)
