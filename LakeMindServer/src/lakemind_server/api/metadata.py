from __future__ import annotations
import asyncio
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


def _eng(request: Request):
    return request.app.state.engines.metadata


class CreateTenantBody(BaseModel):
    tenant_id: str
    name: str


class UpdateTenantBody(BaseModel):
    name: str | None = None
    status: str | None = None


class CreateUserBody(BaseModel):
    username: str
    tenant_id: str
    role: str = "user"


class UpdateUserBody(BaseModel):
    username: str | None = None
    role: str | None = None
    status: str | None = None


class IssueTokenBody(BaseModel):
    agent_id: str
    tenant_id: str
    scopes: list[str]


class RegisterAssetTypeBody(BaseModel):
    type: str
    yaml_def: str


@router.post("/tenants")
async def create_tenant(body: CreateTenantBody, request: Request):
    return await asyncio.to_thread(_eng(request).create_tenant, body.tenant_id, body.name)


@router.get("/tenants")
async def list_tenants(request: Request):
    return await asyncio.to_thread(_eng(request).list_tenants)


@router.put("/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, body: UpdateTenantBody, request: Request):
    return await asyncio.to_thread(_eng(request).update_tenant, tenant_id, body.name, body.status)


@router.delete("/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str, request: Request):
    return await asyncio.to_thread(_eng(request).delete_tenant, tenant_id)


@router.post("/users")
async def create_user(body: CreateUserBody, request: Request):
    return await asyncio.to_thread(_eng(request).create_user, body.username, body.tenant_id, body.role)


@router.get("/users")
async def list_users(request: Request, tenant_id: str | None = None):
    return await asyncio.to_thread(_eng(request).list_users, tenant_id)


@router.put("/users/{user_id}")
async def update_user(user_id: str, body: UpdateUserBody, request: Request):
    return await asyncio.to_thread(_eng(request).update_user, user_id, body.username, body.role, body.status)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, request: Request):
    return await asyncio.to_thread(_eng(request).delete_user, user_id)


@router.post("/tokens")
async def issue_token(body: IssueTokenBody, request: Request):
    return await asyncio.to_thread(_eng(request).issue_token, body.agent_id, body.tenant_id, body.scopes)


@router.get("/tokens")
async def list_tokens(request: Request, tenant_id: str | None = None, agent_id: str | None = None):
    return await asyncio.to_thread(_eng(request).list_tokens, tenant_id, agent_id)


@router.delete("/tokens/{token}")
async def revoke_token(token: str, request: Request):
    return await asyncio.to_thread(_eng(request).revoke_token, token)


@router.post("/asset-types")
async def register_asset_type(body: RegisterAssetTypeBody, request: Request):
    return await asyncio.to_thread(_eng(request).register_asset_type, body.type, body.yaml_def)


@router.get("/asset-types")
async def list_asset_types(request: Request):
    return await asyncio.to_thread(_eng(request).list_asset_types)


@router.delete("/asset-types/{type}")
async def unregister_asset_type(type: str, request: Request):
    return await asyncio.to_thread(_eng(request).unregister_asset_type, type)
