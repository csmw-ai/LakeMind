from __future__ import annotations
import asyncio
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    engines = request.app.state.engines
    return await asyncio.to_thread(engines.all_health)


@router.get("/nodes")
async def nodes(request: Request):
    return {
        "nodes": [
            {"name": "server-api", "status": "active", "port": 10823},
            {"name": "postgres", "status": "active"},
            {"name": "seaweedfs", "status": "active"},
            {"name": "valkey", "status": "active"},
        ]
    }


@router.get("/metrics")
async def metrics(request: Request):
    engines = request.app.state.engines
    health = await asyncio.to_thread(engines.all_health)
    return {
        "engines": health,
        "healthy_count": sum(1 for v in health.values() if v),
        "total_count": len(health),
    }


@router.post("/reconcile")
async def reconcile(request: Request):
    from ..services.reconciliation_service import ReconciliationService
    return await asyncio.to_thread(ReconciliationService.scan_all)


@router.get("/reconcile/drifts")
async def get_drifts(request: Request):
    from ..services.reconciliation_service import ReconciliationService
    params = request.query_params
    return await asyncio.to_thread(
        ReconciliationService.get_drifts,
        category=params.get("category"),
        page=int(params.get("page", "1")),
        page_size=int(params.get("page_size", "50")),
    )
