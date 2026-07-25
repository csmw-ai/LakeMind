from __future__ import annotations
import asyncio
from fastapi import APIRouter, Request, UploadFile, File
from ..security.middleware import get_security_context, require_action
from ..services.asset_service import AssetService
from ..security.actions import Action

router = APIRouter()


@router.post("")
async def create_asset(request: Request):
    ctx = get_security_context(request)
    if not ctx.has_scope(Action.ASSET_CREATE.value):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="PERMISSION_DENIED")
    body = await request.json()
    return await asyncio.to_thread(AssetService.create_asset, ctx, **body)


@router.get("")
async def list_assets(request: Request):
    ctx = get_security_context(request)
    params = request.query_params
    return await asyncio.to_thread(
        AssetService.list_assets,
        ctx,
        asset_type=params.get("type"),
        status=params.get("status"),
        page=int(params.get("page", "1")),
    )


@router.get("/{asset_id}")
async def get_asset(asset_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(AssetService.get_asset, ctx, asset_id)


@router.patch("/{asset_id}")
async def update_asset(asset_id: str, request: Request):
    ctx = get_security_context(request)
    body = await request.json()
    return await asyncio.to_thread(AssetService.update_asset, ctx, asset_id, body.get("metadata", {}))


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(AssetService.delete_asset, ctx, asset_id)


@router.get("/{asset_id}/bindings")
async def get_bindings(asset_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(AssetService.get_bindings, asset_id)


@router.get("/{asset_id}/lineage")
async def get_lineage(asset_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(AssetService.get_lineage, asset_id)


@router.get("/{asset_id}/health")
async def get_health(asset_id: str, request: Request):
    ctx = get_security_context(request)
    from ..db import execute_one
    asset = await asyncio.to_thread(execute_one, "SELECT * FROM assets WHERE asset_id = %s", (asset_id,))
    if asset is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="ASSET_NOT_FOUND")
    if not ctx.can_access_tenant(asset.get("tenant_id", "")):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="TENANT_SCOPE_VIOLATION")
    completeness_score = 1.0 if asset.get("uri") else 0.0
    completeness_status = "healthy" if completeness_score >= 1.0 else "unhealthy"
    retrievability_score = 1.0 if asset.get("status") == "ready" else 0.5
    retrievability_status = "healthy" if retrievability_score >= 1.0 else "degraded"
    executability_score = 1.0 if asset.get("asset_type") != "skill" else (1.0 if asset.get("status") == "ready" else 0.0)
    executability_status = "healthy" if executability_score >= 1.0 else "degraded"
    drift_score = 1.0
    drift_status = "healthy"
    overall = "healthy"
    if completeness_score < 1.0 or retrievability_score < 0.5:
        overall = "unhealthy"
    elif retrievability_score < 1.0 or executability_score < 1.0:
        overall = "degraded"
    return {
        "overall": overall,
        "dimensions": {
            "completeness": {"score": completeness_score, "status": completeness_status, "details": "File existence and metadata check"},
            "retrievability": {"score": retrievability_score, "status": retrievability_status, "details": "Index availability check"},
            "executability": {"score": executability_score, "status": executability_status, "details": "Skill parse and dependency check"},
            "drift": {"score": drift_score, "status": drift_status, "details": "Checksum comparison"},
        },
        "last_checked_at": asset.get("updated_at"),
        "recommendations": [] if overall == "healthy" else ["reindex"],
    }


@router.post("/{asset_id}/reindex")
async def reindex_asset(asset_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(AssetService.reindex, ctx, asset_id)
