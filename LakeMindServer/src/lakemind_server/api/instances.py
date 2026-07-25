from __future__ import annotations
import asyncio
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from ..services.instance_registry import InstanceRegistry

router = APIRouter()


class RegisterRequest(BaseModel):
    service_type: str
    version: str
    endpoint: str
    capabilities: list[str] = []
    instance_id: str = ""


class HeartbeatRequest(BaseModel):
    health_status: str = "healthy"
    active_revision_id: str | None = None


@router.get("")
async def list_instances(request: Request):
    service_type = request.query_params.get("service_type")
    return await asyncio.to_thread(InstanceRegistry.list_instances, service_type)


@router.get("/{instance_id}")
async def get_instance(instance_id: str):
    return await asyncio.to_thread(InstanceRegistry.get_instance, instance_id)


@router.post("")
async def register_instance(body: RegisterRequest):
    existing = None
    if body.instance_id:
        existing = await asyncio.to_thread(InstanceRegistry.get_instance, body.instance_id)
    if existing:
        await asyncio.to_thread(InstanceRegistry.heartbeat, body.instance_id, "healthy")
        return existing
    return await asyncio.to_thread(
        InstanceRegistry.register,
        service_type=body.service_type,
        version=body.version,
        endpoint=body.endpoint,
        capabilities=body.capabilities,
    )


@router.put("/{instance_id}/heartbeat")
async def heartbeat_instance(instance_id: str, body: HeartbeatRequest):
    existing = await asyncio.to_thread(InstanceRegistry.get_instance, instance_id)
    if not existing:
        raise HTTPException(status_code=404, detail="INSTANCE_NOT_FOUND")
    await asyncio.to_thread(InstanceRegistry.heartbeat, instance_id, body.health_status, body.active_revision_id)
    return {"ok": True}
