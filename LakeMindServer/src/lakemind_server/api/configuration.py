from __future__ import annotations
import asyncio
from fastapi import APIRouter, Request
from ..security.middleware import get_security_context
from ..services.configuration_service import ConfigurationService

router = APIRouter()


@router.get("")
async def get_effective_config(request: Request):
    ctx = get_security_context(request)
    scope = request.query_params.get("scope", "platform")
    return await asyncio.to_thread(ConfigurationService.get_effective, scope)


@router.get("/{scope}")
async def get_config(scope: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(ConfigurationService.get, scope)


@router.put("/{scope}")
async def set_config(scope: str, request: Request):
    ctx = get_security_context(request)
    body = await request.json()
    return await asyncio.to_thread(
        ConfigurationService.set,
        scope=scope,
        key=body["key"],
        value=body["value"],
        reason=body.get("reason", ""),
        created_by=ctx.principal_id,
    )


@router.get("/revisions/all")
async def list_revisions(request: Request):
    ctx = get_security_context(request)
    scope = request.query_params.get("scope")
    page = int(request.query_params.get("page", "1"))
    return await asyncio.to_thread(ConfigurationService.list_revisions, scope, page)


@router.post("/revisions/{revision_id}/activate")
async def activate_revision(revision_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(ConfigurationService.activate, revision_id, ctx.principal_id)


@router.post("/revisions/{revision_id}/rollback")
async def rollback_revision(revision_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(ConfigurationService.rollback, revision_id, ctx.principal_id)
