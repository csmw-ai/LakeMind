from __future__ import annotations
import asyncio
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


def _eng(request: Request):
    return request.app.state.engines.metadata


def _ctx(request: Request):
    return {
        "tenant_id": request.headers.get("X-Tenant-Id", "default"),
        "agent_id": request.headers.get("X-Agent-Id", "unknown"),
    }


class CreateSecretBody(BaseModel):
    key_name: str
    value: str
    description: str = ""


class UpdateSecretBody(BaseModel):
    value: str
    description: str = ""


@router.post("")
async def create_secret(body: CreateSecretBody, request: Request):
    ctx = _ctx(request)
    return await asyncio.to_thread(
        _eng(request).create_secret,
        ctx["tenant_id"], body.key_name, body.value, body.description, ctx["agent_id"]
    )


@router.put("/{key_name}")
async def update_secret(key_name: str, body: UpdateSecretBody, request: Request):
    ctx = _ctx(request)
    result = await asyncio.to_thread(
        _eng(request).update_secret,
        ctx["tenant_id"], key_name, body.value, body.description
    )
    if not result.get("updated"):
        raise HTTPException(status_code=404, detail=f"secret '{key_name}' not found")
    return result


@router.delete("/{key_name}")
async def delete_secret(key_name: str, request: Request):
    ctx = _ctx(request)
    return await asyncio.to_thread(_eng(request).delete_secret, ctx["tenant_id"], key_name)


@router.get("")
async def list_secrets(request: Request):
    ctx = _ctx(request)
    return await asyncio.to_thread(_eng(request).list_secrets, ctx["tenant_id"])
