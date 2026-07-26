from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from ..auth import check_auth

router = APIRouter()


class CreateModelRequest(BaseModel):
    name: str
    model_type: str
    provider: str
    provider_id: str | None = None
    source: str = "external"
    model_path: str = ""
    config: dict | None = None
    capabilities: list | None = None
    context_length: int | None = None
    embedding_dim: int | None = None
    priority: int = 100
    status: str = "enabled"


@router.get("/v1/models")
async def list_models(request: Request):
    check_auth(request)
    registry = request.app.state.registry
    params = request.query_params
    models = registry.list_models(params.get("type"))
    return {"object": "list", "data": models}


@router.get("/v1/models/types")
async def list_model_types(request: Request):
    check_auth(request)
    return {"types": ["chat", "embedding", "asr"]}


@router.get("/v1/models/{model_id}")
async def get_model(model_id: str, request: Request):
    check_auth(request)
    registry = request.app.state.registry
    model = registry.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    return model


@router.post("/v1/models")
async def create_model(body: CreateModelRequest, request: Request):
    check_auth(request)
    registry = request.app.state.registry
    existing = registry.get_model_by_name(body.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Model name '{body.name}' already exists")
    try:
        data = body.model_dump()
        if "config" in data:
            data["model_config"] = data.pop("config")
        return registry.create_model(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/v1/models/{model_id}")
async def update_model(model_id: str, request: Request):
    check_auth(request)
    registry = request.app.state.registry
    body = await request.json()
    try:
        return registry.update_model(model_id, **body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/v1/models/{model_id}")
async def delete_model(model_id: str, request: Request):
    check_auth(request)
    registry = request.app.state.registry
    try:
        return registry.delete_model(model_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/v1/models/{model_id}/enable")
async def enable_model(model_id: str, request: Request):
    check_auth(request)
    registry = request.app.state.registry
    try:
        return registry.enable_model(model_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/v1/models/{model_id}/disable")
async def disable_model(model_id: str, request: Request):
    check_auth(request)
    registry = request.app.state.registry
    try:
        return registry.disable_model(model_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/v1/models/{model_id}/test")
async def test_model(model_id: str, request: Request):
    check_auth(request)
    registry = request.app.state.registry
    try:
        return registry.test_model(model_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
