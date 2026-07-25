from __future__ import annotations
import asyncio
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from ..security.middleware import require_action, get_security_context
from ..services.authorization_service import AuthorizationService

router = APIRouter()


@router.post("/auth/login")
async def login_endpoint(request: Request):
    body = await request.json()
    try:
        result = await asyncio.to_thread(
            AuthorizationService.login,
            username=body["username"],
            password_hash=body["password_hash"],
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=401, detail={"error": {"code": str(exc), "message": str(exc)}})


@router.post("/tokens")
async def issue_token_endpoint(request: Request):
    ctx = get_security_context(request)
    body = await request.json()
    result = await asyncio.to_thread(
        AuthorizationService.issue_token,
        principal_id=body["principal_id"],
        tenant_id=body.get("tenant_id", ctx.tenant_id),
        scopes=body.get("scopes", []),
        expires_at=datetime.fromisoformat(body["expires_at"]) if body.get("expires_at") else None,
    )
    return result


@router.delete("/tokens/{token_id}")
async def revoke_token_endpoint(token_id: str, request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(AuthorizationService.revoke_token, token_id, ctx)


@router.get("/tokens")
async def list_tokens_endpoint(request: Request):
    ctx = get_security_context(request)
    return await asyncio.to_thread(AuthorizationService.list_tokens, ctx)


@router.get("/roles")
async def list_roles_endpoint():
    from ..db import execute
    return await asyncio.to_thread(execute, "SELECT role_id, name, permissions, is_builtin FROM roles ORDER BY name")


@router.get("/principals")
async def list_principals_endpoint(request: Request):
    ctx = get_security_context(request)
    from ..db import execute
    items = await asyncio.to_thread(
        execute,
        "SELECT principal_id, principal_type, tenant_id, status FROM principals "
        "WHERE tenant_id = %s ORDER BY principal_id",
        (ctx.tenant_id,),
    )
    return {"items": items}


@router.post("/principals")
async def create_principal_endpoint(request: Request):
    ctx = get_security_context(request)
    if not ctx.is_tenant_admin:
        raise HTTPException(status_code=403, detail="PERMISSION_DENIED")

    body = await request.json()
    username = body.get("username", "")
    password_hash = body.get("password_hash", "")
    display_name = body.get("display_name", username)
    tenant_id = body.get("tenant_id", ctx.tenant_id)
    role_name = body.get("role_name", "meeting_user")

    if not username or not password_hash:
        raise HTTPException(status_code=400, detail="USERNAME_AND_PASSWORD_REQUIRED")
    if ctx.tenant_id != tenant_id and not ctx.is_platform_admin:
        raise HTTPException(status_code=403, detail="CANNOT_CREATE_IN_OTHER_TENANT")

    from ..db import execute, execute_one
    existing = await asyncio.to_thread(execute_one, "SELECT principal_id FROM principals WHERE username = %s", (username,))
    if existing:
        raise HTTPException(status_code=409, detail="USERNAME_EXISTS")

    role_row = await asyncio.to_thread(execute_one, "SELECT role_id FROM roles WHERE name = %s", (role_name,))
    if role_row is None:
        raise HTTPException(status_code=400, detail=f"ROLE_NOT_FOUND: {role_name}")

    import ulid, json
    from datetime import datetime, timezone
    principal_id = f"prn_{str(ulid.new())}"
    now = datetime.now(timezone.utc)

    await asyncio.to_thread(
        execute,
        "INSERT INTO principals (principal_id, principal_type, name, tenant_id, username, password_hash, status, metadata) "
        "VALUES (%s, 'user', %s, %s, %s, %s, 'active', %s::jsonb)",
        (principal_id, display_name, tenant_id, username, password_hash, json.dumps({"created_by": ctx.principal_id})),
    )

    binding_id = f"rb_{str(ulid.new())}"
    await asyncio.to_thread(
        execute,
        "INSERT INTO role_bindings (binding_id, principal_id, role_id, tenant_id) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (principal_id, role_id, tenant_id) DO NOTHING",
        (binding_id, principal_id, role_row["role_id"], tenant_id),
    )

    inviter_row = await asyncio.to_thread(execute_one, "SELECT principal_id FROM principals WHERE principal_id = %s", (ctx.principal_id,))
    invited_by = inviter_row["principal_id"] if inviter_row else None
    membership_id = f"mb_{str(ulid.new())}"
    await asyncio.to_thread(
        execute,
        "INSERT INTO principal_tenant_memberships (id, principal_id, tenant_id, membership_status, invited_by, joined_at) "
        "VALUES (%s, %s, %s, 'ACTIVE', %s, %s) "
        "ON CONFLICT (principal_id, tenant_id) DO UPDATE SET membership_status = 'ACTIVE', revoked_at = NULL",
        (membership_id, principal_id, tenant_id, invited_by, now),
    )

    await asyncio.to_thread(
        execute,
        "UPDATE principals SET security_version = security_version + 1 WHERE principal_id = %s",
        (principal_id,),
    )

    from ..services.audit_service import AuditService
    await asyncio.to_thread(
        AuditService.record,
        event_type="principal.created",
        principal_id=ctx.principal_id,
        tenant_id=tenant_id,
        resource_id=principal_id,
        action="create_principal",
        result="success",
        details={"username": username, "role": role_name},
    )

    return {"principal_id": principal_id, "status": "active", "username": username, "tenant_id": tenant_id, "role": role_name}


@router.get("/auth/me")
async def get_me_endpoint(request: Request):
    ctx = get_security_context(request)
    from ..db import execute
    from ..security.actions import ALL_CAPABILITIES

    available_tenants = []
    if ctx.is_platform_admin:
        available_tenants = await asyncio.to_thread(
            execute,
            "SELECT t.tenant_id, t.name, 'platform_admin' AS role "
            "FROM tenants t WHERE LOWER(t.status) != 'archived' ORDER BY t.name"
        )
    else:
        available_tenants = await asyncio.to_thread(
            execute,
            "SELECT t.tenant_id, t.name, "
            "COALESCE(rb.role_id, 'tenant_admin') AS role "
            "FROM principal_tenant_memberships m "
            "JOIN tenants t ON m.tenant_id = t.tenant_id "
            "LEFT JOIN role_bindings rb ON m.role_binding_id = rb.binding_id "
            "WHERE m.principal_id = %s AND m.membership_status = 'ACTIVE' AND LOWER(t.status) != 'archived' "
            "ORDER BY t.name",
            (ctx.principal_id,),
        )

    caps = ctx.capabilities
    effective_permissions = {cap: (cap in caps) for cap in ALL_CAPABILITIES}

    return {
        "principal_id": ctx.principal_id,
        "principal_type": ctx.principal_type,
        "tenant_id": ctx.tenant_id,
        "roles": ctx.roles,
        "capabilities": caps,
        "effective_permissions": effective_permissions,
        "security_version": ctx.security_version,
        "active_tenant_id": ctx.tenant_id,
        "available_tenants": available_tenants,
    }


@router.post("/switch-tenant")
async def switch_tenant_endpoint(request: Request):
    ctx = get_security_context(request)
    body = await request.json()
    target_tenant_id = body.get("tenant_id", "")
    from ..db import execute_one

    if ctx.is_platform_admin:
        tenant = await asyncio.to_thread(execute_one, "SELECT tenant_id FROM tenants WHERE tenant_id = %s AND LOWER(status) = 'active'", (target_tenant_id,))
        if not tenant:
            raise HTTPException(status_code=404, detail="TENANT_NOT_FOUND")
        return {"tenant_id": target_tenant_id, "security_version": ctx.security_version}

    membership = await asyncio.to_thread(
        execute_one,
        "SELECT m.* FROM principal_tenant_memberships m "
        "JOIN tenants t ON m.tenant_id = t.tenant_id "
        "WHERE m.principal_id = %s AND m.tenant_id = %s "
        "AND m.membership_status = 'ACTIVE' AND LOWER(t.status) = 'active'",
        (ctx.principal_id, target_tenant_id),
    )
    if not membership:
        raise HTTPException(status_code=403, detail="NO_MEMBERSHIP")

    return {"tenant_id": target_tenant_id, "security_version": ctx.security_version}
