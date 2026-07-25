from __future__ import annotations
import asyncio
import json
import ulid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from ..security.middleware import get_security_context, require_action
from ..db import execute, execute_one
from ..services.audit_service import AuditService

router = APIRouter()


def _ulid(prefix: str) -> str:
    return f"{prefix}_{str(ulid.new())}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TenantService:

    @staticmethod
    def create(name: str, admin_principal_id: str, quotas: dict | None = None,
               allowed_models: list[str] | None = None, config_template: str | None = None,
               initiator_id: str = "") -> dict:
        existing = execute_one("SELECT tenant_id FROM tenants WHERE name = %s", (name,))
        if existing:
            raise ValueError("TENANT_NAME_EXISTS")

        admin = execute_one("SELECT principal_id FROM principals WHERE principal_id = %s", (admin_principal_id,))
        if admin is None:
            raise ValueError("ADMIN_PRINCIPAL_NOT_FOUND")

        tenant_id = _ulid("ten")

        membership_id = _ulid("mb")
        execute(
            "INSERT INTO principal_tenant_memberships (id, principal_id, tenant_id, membership_status, joined_at) "
            "VALUES (%s, %s, %s, 'ACTIVE', %s)",
            (membership_id, admin_principal_id, tenant_id, _now()),
        )

        scope_id = _ulid("cfg")
        execute(
            "INSERT INTO config_revisions (revision_id, scope, values, schema_version, created_by, is_active) "
            "VALUES (%s, %s, %s::jsonb, '1', %s, true)",
            (scope_id, f"tenant:{tenant_id}", json.dumps({"template": config_template or "default"}), initiator_id),
        )

        execute(
            "INSERT INTO tenants (tenant_id, name, status, quotas, allowed_models) "
            "VALUES (%s, %s, 'ACTIVE', %s::jsonb, %s::jsonb)",
            (tenant_id, name, json.dumps(quotas or {}), json.dumps(allowed_models or [])),
        )

        execute(
            "UPDATE principals SET security_version = security_version + 1 WHERE principal_id = %s",
            (admin_principal_id,),
        )

        AuditService.record(
            event_type="tenant.created",
            principal_id=initiator_id,
            tenant_id=tenant_id,
            resource_id=tenant_id,
            action="create_tenant",
            result="success",
            details={"name": name, "admin_principal_id": admin_principal_id},
        )

        return {"tenant_id": tenant_id, "name": name, "status": "ACTIVE"}

    @staticmethod
    def list_tenants(page: int = 1, page_size: int = 50) -> dict:
        items = execute("SELECT * FROM tenants ORDER BY created_at DESC")
        total = len(items)
        offset = (page - 1) * page_size
        return {"items": items[offset:offset + page_size], "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def get(tenant_id: str) -> dict:
        row = execute_one("SELECT * FROM tenants WHERE tenant_id = %s", (tenant_id,))
        if row is None:
            raise ValueError("TENANT_NOT_FOUND")
        return row

    @staticmethod
    def update(tenant_id: str, quotas: dict | None = None,
               allowed_models: list[str] | None = None) -> dict:
        parts = []
        params = []
        if quotas is not None:
            parts.append("quotas = %s::jsonb")
            params.append(json.dumps(quotas))
        if allowed_models is not None:
            parts.append("allowed_models = %s::jsonb")
            params.append(json.dumps(allowed_models))
        if not parts:
            return TenantService.get(tenant_id)
        params.append(tenant_id)
        execute(f"UPDATE tenants SET {', '.join(parts)} WHERE tenant_id = %s", tuple(params))
        return TenantService.get(tenant_id)

    @staticmethod
    def suspend(tenant_id: str, initiator_id: str = "") -> dict:
        execute("UPDATE tenants SET status = 'SUSPENDED' WHERE tenant_id = %s", (tenant_id,))
        execute(
            "UPDATE principals SET security_version = security_version + 1 "
            "WHERE principal_id IN (SELECT principal_id FROM principal_tenant_memberships WHERE tenant_id = %s)",
            (tenant_id,),
        )
        AuditService.record(
            event_type="tenant.suspended",
            principal_id=initiator_id,
            tenant_id=tenant_id,
            resource_id=tenant_id,
            action="suspend_tenant",
            result="success",
        )
        return {"tenant_id": tenant_id, "status": "SUSPENDED"}

    @staticmethod
    def resume(tenant_id: str, initiator_id: str = "") -> dict:
        execute("UPDATE tenants SET status = 'ACTIVE' WHERE tenant_id = %s", (tenant_id,))
        AuditService.record(
            event_type="tenant.resumed",
            principal_id=initiator_id,
            tenant_id=tenant_id,
            resource_id=tenant_id,
            action="resume_tenant",
            result="success",
        )
        return {"tenant_id": tenant_id, "status": "ACTIVE"}

    @staticmethod
    def archive(tenant_id: str, initiator_id: str = "") -> dict:
        execute("UPDATE tenants SET status = 'ARCHIVED' WHERE tenant_id = %s", (tenant_id,))
        execute(
            "UPDATE principal_tenant_memberships SET membership_status = 'REVOKED', revoked_at = %s WHERE tenant_id = %s",
            (_now(), tenant_id),
        )
        execute(
            "UPDATE principals SET security_version = security_version + 1 "
            "WHERE principal_id IN (SELECT principal_id FROM principal_tenant_memberships WHERE tenant_id = %s)",
            (tenant_id,),
        )
        AuditService.record(
            event_type="tenant.archived",
            principal_id=initiator_id,
            tenant_id=tenant_id,
            resource_id=tenant_id,
            action="archive_tenant",
            result="success",
        )
        return {"tenant_id": tenant_id, "status": "ARCHIVED"}

    @staticmethod
    def list_memberships(tenant_id: str) -> dict:
        items = execute(
            "SELECT m.*, p.name AS principal_name, p.principal_type "
            "FROM principal_tenant_memberships m JOIN principals p ON m.principal_id = p.principal_id "
            "WHERE m.tenant_id = %s ORDER BY m.joined_at DESC",
            (tenant_id,),
        )
        return {"items": items}

    @staticmethod
    def add_membership(tenant_id: str, principal_id: str, role_name: str, initiator_id: str = "") -> dict:
        membership_id = _ulid("mb")
        execute(
            "INSERT INTO principal_tenant_memberships (id, principal_id, tenant_id, membership_status, invited_by, joined_at) "
            "VALUES (%s, %s, %s, 'ACTIVE', %s, %s) "
            "ON CONFLICT (principal_id, tenant_id) DO UPDATE SET membership_status = 'ACTIVE', revoked_at = NULL",
            (membership_id, principal_id, tenant_id, initiator_id, _now()),
        )
        execute(
            "UPDATE principals SET security_version = security_version + 1 WHERE principal_id = %s",
            (principal_id,),
        )
        return {"id": membership_id, "principal_id": principal_id, "tenant_id": tenant_id, "membership_status": "ACTIVE"}

    @staticmethod
    def revoke_membership(tenant_id: str, membership_id: str, initiator_id: str = "") -> dict:
        row = execute_one(
            "SELECT principal_id FROM principal_tenant_memberships WHERE id = %s AND tenant_id = %s",
            (membership_id, tenant_id),
        )
        if row is None:
            raise ValueError("MEMBERSHIP_NOT_FOUND")
        execute(
            "UPDATE principal_tenant_memberships SET membership_status = 'REVOKED', revoked_at = %s WHERE id = %s",
            (_now(), membership_id),
        )
        execute(
            "UPDATE principals SET security_version = security_version + 1 WHERE principal_id = %s",
            (row["principal_id"],),
        )
        return {"id": membership_id, "membership_status": "REVOKED"}


@router.post("")
async def create_tenant(request: Request):
    ctx = get_security_context(request)
    if not ctx.is_platform_admin:
        raise HTTPException(status_code=403, detail="PERMISSION_DENIED")
    body = await request.json()
    try:
        return await asyncio.to_thread(
            TenantService.create,
            name=body["name"],
            admin_principal_id=body["admin_principal_id"],
            quotas=body.get("quotas"),
            allowed_models=body.get("allowed_models"),
            config_template=body.get("config_template"),
            initiator_id=ctx.principal_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("")
async def list_tenants(request: Request):
    ctx = get_security_context(request)
    if not ctx.is_platform_admin:
        item = await asyncio.to_thread(TenantService.get, ctx.tenant_id)
        return {"items": [item], "total": 1, "page": 1, "page_size": 50}
    params = request.query_params
    return await asyncio.to_thread(TenantService.list_tenants, page=int(params.get("page", "1")), page_size=int(params.get("page_size", "50")))


@router.get("/{tenant_id}")
async def get_tenant(tenant_id: str, request: Request):
    ctx = get_security_context(request)
    if not ctx.can_access_tenant(tenant_id):
        raise HTTPException(status_code=403, detail="TENANT_SCOPE_VIOLATION")
    try:
        return await asyncio.to_thread(TenantService.get, tenant_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="TENANT_NOT_FOUND")


@router.put("/{tenant_id}")
async def update_tenant(tenant_id: str, request: Request):
    ctx = get_security_context(request)
    if not ctx.is_platform_admin:
        raise HTTPException(status_code=403, detail="PERMISSION_DENIED")
    body = await request.json()
    return await asyncio.to_thread(TenantService.update, tenant_id, quotas=body.get("quotas"), allowed_models=body.get("allowed_models"))


@router.post("/{tenant_id}/suspend")
async def suspend_tenant(tenant_id: str, request: Request):
    ctx = get_security_context(request)
    if not ctx.is_platform_admin:
        raise HTTPException(status_code=403, detail="PERMISSION_DENIED")
    return await asyncio.to_thread(TenantService.suspend, tenant_id, ctx.principal_id)


@router.post("/{tenant_id}/resume")
async def resume_tenant(tenant_id: str, request: Request):
    ctx = get_security_context(request)
    if not ctx.is_platform_admin:
        raise HTTPException(status_code=403, detail="PERMISSION_DENIED")
    return await asyncio.to_thread(TenantService.resume, tenant_id, ctx.principal_id)


@router.post("/{tenant_id}/archive")
async def archive_tenant(tenant_id: str, request: Request):
    ctx = get_security_context(request)
    if not ctx.is_platform_admin:
        raise HTTPException(status_code=403, detail="PERMISSION_DENIED")
    return await asyncio.to_thread(TenantService.archive, tenant_id, ctx.principal_id)


@router.get("/{tenant_id}/memberships")
async def list_memberships(tenant_id: str, request: Request):
    ctx = get_security_context(request)
    if not ctx.can_access_tenant(tenant_id):
        raise HTTPException(status_code=403, detail="TENANT_SCOPE_VIOLATION")
    return await asyncio.to_thread(TenantService.list_memberships, tenant_id)


@router.post("/{tenant_id}/memberships")
async def add_membership(tenant_id: str, request: Request):
    ctx = get_security_context(request)
    if not ctx.is_tenant_admin:
        raise HTTPException(status_code=403, detail="PERMISSION_DENIED")
    body = await request.json()
    return await asyncio.to_thread(TenantService.add_membership, tenant_id, body["principal_id"], body.get("role_name", "agent"), ctx.principal_id)


@router.post("/{tenant_id}/memberships/{membership_id}/revoke")
async def revoke_membership(tenant_id: str, membership_id: str, request: Request):
    ctx = get_security_context(request)
    if not ctx.is_tenant_admin:
        raise HTTPException(status_code=403, detail="PERMISSION_DENIED")
    try:
        return await asyncio.to_thread(TenantService.revoke_membership, tenant_id, membership_id, ctx.principal_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="MEMBERSHIP_NOT_FOUND")
