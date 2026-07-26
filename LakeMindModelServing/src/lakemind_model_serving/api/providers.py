from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from ..auth import check_auth

router = APIRouter()


class CreateProviderRequest(BaseModel):
    name: str
    type: str
    base_url: str = ""
    api_key: str = ""
    status: str = "enabled"


@router.get("/v1/providers")
async def list_providers(request: Request):
    check_auth(request)
    registry = request.app.state.registry
    return {"object": "list", "data": registry.list_providers()}


@router.get("/v1/providers/{provider_id}")
async def get_provider(provider_id: str, request: Request):
    check_auth(request)
    registry = request.app.state.registry
    provider = registry.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")
    return provider


@router.post("/v1/providers")
async def create_provider(body: CreateProviderRequest, request: Request):
    check_auth(request)
    registry = request.app.state.registry
    existing = registry.get_provider_by_name(body.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Provider name '{body.name}' already exists")
    try:
        data = body.model_dump()
        data["ptype"] = data.pop("type")
        return registry.create_provider(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/v1/providers/{provider_id}")
async def update_provider(provider_id: str, request: Request):
    check_auth(request)
    registry = request.app.state.registry
    body = await request.json()
    try:
        return registry.update_provider(provider_id, **body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/v1/providers/{provider_id}")
async def delete_provider(provider_id: str, request: Request):
    check_auth(request)
    registry = request.app.state.registry
    try:
        return registry.delete_provider(provider_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
