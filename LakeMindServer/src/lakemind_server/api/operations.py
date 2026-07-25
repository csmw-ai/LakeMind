from __future__ import annotations
import asyncio
from fastapi import APIRouter, Request
from ..security.middleware import get_security_context
from ..services.operation_service import OperationService

router = APIRouter()


@router.post("")
async def create_operation(request: Request):
    ctx = get_security_context(request)
    body = await request.json()
    return await asyncio.to_thread(
        OperationService.create,
        op_type=body["op_type"],
        target_resource=body["target_resource"],
        initiator_id=ctx.principal_id,
        initiator_channel="rest",
        reason=body.get("reason"),
        risk_level=body.get("risk_level", "LOW"),
    )


@router.get("")
async def list_operations(request: Request):
    ctx = get_security_context(request)
    params = request.query_params
    return await asyncio.to_thread(
        OperationService.list,
        status=params.get("status"),
        op_type=params.get("op_type"),
        page=int(params.get("page", "1")),
    )


@router.get("/{op_id}")
async def get_operation(op_id: str):
    return await asyncio.to_thread(OperationService.get, op_id)


@router.post("/{op_id}/approve")
async def approve_operation(op_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(OperationService.approve, op_id, ctx.principal_id)


@router.post("/{op_id}/reject")
async def reject_operation(op_id: str, request: Request):
    ctx = get_security_context(request)
    body = await request.json()
    return await asyncio.to_thread(OperationService.reject, op_id, ctx.principal_id, body.get("reason", ""))


@router.post("/{op_id}/cancel")
async def cancel_operation(op_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(OperationService.cancel, op_id)
