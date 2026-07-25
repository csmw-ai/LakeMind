from __future__ import annotations
import asyncio
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from ..security.middleware import get_security_context
from ..services.secret_service import SecretService

router = APIRouter()


class CreateSecretBody(BaseModel):
    name: str
    value: str
    scope: str = "default"


class RotateSecretBody(BaseModel):
    value: str


@router.post("")
async def create_secret(body: CreateSecretBody, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(
        SecretService.create,
        scope=body.scope,
        name=body.name,
        value=body.value,
        created_by=ctx.principal_id,
    )


@router.get("")
async def list_secrets(request: Request):
    ctx = get_security_context(request)
    return {"items": await asyncio.to_thread(SecretService.list, scope=ctx.tenant_id)}


@router.get("/{scope}/{name}")
async def get_secret(scope: str, name: str, request: Request):
    ctx = get_security_context(request)
    row = await asyncio.to_thread(SecretService.get_ref, scope, name)
    if row is None:
        raise HTTPException(status_code=404, detail="Secret not found")
    return row


@router.post("/{scope}/{name}/rotate")
async def rotate_secret(scope: str, name: str, body: RotateSecretBody, request: Request):
    ctx = get_security_context(request)
    try:
        return await asyncio.to_thread(SecretService.rotate, scope, name, body.value, ctx.principal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{scope}/{name}")
async def delete_secret(scope: str, name: str, request: Request):
    from ..db import execute
    ctx = get_security_context(request)
    rows = await asyncio.to_thread(
        execute,
        "DELETE FROM v2_secrets WHERE scope = %s AND name = %s RETURNING secret_id",
        (scope, name),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Secret not found")
    return {"deleted": True, "count": len(rows)}
