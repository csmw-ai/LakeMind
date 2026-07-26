from __future__ import annotations
import asyncio
import json
from fastapi import APIRouter, Request, HTTPException, Response
from ..security import (
    get_auth_context, login_to_server, register_principal,
    create_session_cookie, parse_session_cookie, hash_password,
)

router = APIRouter(prefix="/api/auth")


@router.post("/register")
async def register(request: Request):
    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")
    display_name = body.get("display_name", username)

    if not username or not password:
        raise HTTPException(status_code=400, detail="USERNAME_AND_PASSWORD_REQUIRED")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="PASSWORD_TOO_SHORT")

    await register_principal(username, password, display_name)
    result = await login_to_server(username, password)

    resp = Response(json.dumps({"principal_id": result["principal_id"], "username": username}))
    resp.set_cookie(
        key="session", value=create_session_cookie(result["token"]),
        httponly=True, samesite="lax", max_age=86400,
    )
    return resp


@router.post("/login")
async def login(request: Request):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="USERNAME_AND_PASSWORD_REQUIRED")

    result = await login_to_server(username, password)

    resp = Response(json.dumps({"principal_id": result["principal_id"], "username": username}))
    resp.set_cookie(
        key="session", value=create_session_cookie(result["token"]),
        httponly=True, samesite="lax", max_age=86400,
    )
    return resp


@router.post("/logout")
async def logout(request: Request):
    resp = Response(json.dumps({"ok": True}))
    resp.delete_cookie(key="session")
    return resp


@router.get("/me")
async def me(request: Request):
    ctx = await get_auth_context(request)
    return {
        "principal_id": ctx.principal_id,
        "tenant_id": ctx.tenant_id,
        "roles": ctx.roles,
        "capabilities": ctx.capabilities,
    }
