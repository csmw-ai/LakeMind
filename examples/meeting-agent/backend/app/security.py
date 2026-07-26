from __future__ import annotations
import hashlib
import hmac
import uuid
from datetime import datetime, timezone
import aiosqlite
from fastapi import Request, HTTPException
from .config import SECRET_KEY, TENANT_ID, DB_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def create_session_cookie(token: str) -> str:
    sig = hmac.new(SECRET_KEY.encode(), token.encode(), hashlib.sha256).hexdigest()
    return f"{token}.{sig}"


def parse_session_cookie(cookie_val: str) -> str | None:
    if not cookie_val or "." not in cookie_val:
        return None
    token, sig = cookie_val.rsplit(".", 1)
    expected = hmac.new(SECRET_KEY.encode(), token.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    return token


class AuthContext:
    def __init__(self, principal_id: str, tenant_id: str, token: str, roles: list[str], capabilities: list[str]):
        self.principal_id = principal_id
        self.tenant_id = tenant_id
        self.token = token
        self.roles = roles
        self.capabilities = capabilities

    @property
    def is_admin(self) -> bool:
        return "platform_admin" in self.roles or "tenant_admin" in self.roles


async def verify_token(token: str) -> AuthContext:
    parts = token.split(":", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=401, detail="INVALID_TOKEN")
    principal_id, username = parts
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT principal_id FROM app_users WHERE principal_id = ? AND username = ?",
            (principal_id, username),
        )
        if not rows:
            raise HTTPException(status_code=401, detail="INVALID_TOKEN")
    return AuthContext(
        principal_id=principal_id,
        tenant_id=TENANT_ID,
        token=token,
        roles=["meeting_user"],
        capabilities=["read", "write"],
    )


async def get_auth_context(request: Request) -> AuthContext:
    cookie_val = request.cookies.get("session")
    if not cookie_val:
        raise HTTPException(status_code=401, detail="NOT_AUTHENTICATED")
    token = parse_session_cookie(cookie_val)
    if not token:
        raise HTTPException(status_code=401, detail="INVALID_SESSION")
    return await verify_token(token)


async def login_to_server(username: str, password: str) -> dict:
    password_hash = hash_password(password)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT principal_id, password_hash FROM app_users WHERE username = ?",
            (username,),
        )
        if not rows or rows[0]["password_hash"] != password_hash:
            raise HTTPException(status_code=401, detail="LOGIN_FAILED")
        principal_id = rows[0]["principal_id"]
    token = f"{principal_id}:{username}"
    return {"principal_id": principal_id, "token": token}


async def register_principal(username: str, password: str, display_name: str) -> dict:
    password_hash = hash_password(password)
    principal_id = f"prn_{uuid.uuid4().hex[:12]}"
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO app_users (principal_id, username, password_hash, tenant_id, display_name, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (principal_id, username, password_hash, TENANT_ID, display_name, _now_iso()),
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(status_code=409, detail="USERNAME_EXISTS")
    return {"principal_id": principal_id}
