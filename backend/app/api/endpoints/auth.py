"""认证端点"""
from fastapi import APIRouter, HTTPException, status, Depends, Header, Request, Response
from pydantic import BaseModel
import uuid
import base64
import hmac
import hashlib
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    verify_refresh_token,
    revoke_token_jti,
)
from app.core.database import get_db
from app.core.ids import normalize_uuid
from app.core.config import settings

router = APIRouter()

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _sign_user_id(user_id: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), user_id.encode("utf-8"), hashlib.sha256).digest()
    return _b64url(digest)


def _make_session_cookie(user_id: str, secret: str) -> str:
    sig = _sign_user_id(user_id, secret)
    return f"{user_id}.{sig}"


def _parse_session_cookie(value: str, secret: str) -> str | None:
    if not value or "." not in value:
        return None
    user_id, sig = value.rsplit(".", 1)
    if not user_id or not sig:
        return None
    expected = _sign_user_id(user_id, secret)
    if not hmac.compare_digest(sig, expected):
        return None
    return user_id


class TokenRequest(BaseModel):
    """Token 请求"""
    user_id: str = None  # 可选，不提供则自动生成


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user_id: str


@router.post("/token", response_model=TokenResponse)
async def get_token(
    http_request: Request,
    http_response: Response,
    request: TokenRequest = None,
    db: AsyncSession = Depends(get_db),
    token_issue_secret: str | None = Header(default=None, alias="X-Token-Issue-Secret"),
):
    """
    获取访问 Token
    
    MVP 阶段简化认证：
    - 提供 user_id 则使用该 ID
    - 不提供则自动生成新用户 ID
    - 自动确保用户存在于 users 表中
    """
    cookie_name = getattr(settings, "AUTH_SESSION_COOKIE_NAME", "affinity_aid")
    session_secret = getattr(settings, "AUTH_SESSION_SECRET", "") or ""

    allow_new_session = bool(settings.DEBUG)
    if not settings.DEBUG:
        if not settings.TOKEN_ISSUE_SECRET:
            host = None
            try:
                host = http_request.client.host if http_request and http_request.client else None
            except Exception:
                host = None
            if bool(getattr(settings, "ALLOW_LOCAL_TOKEN_ISSUE", False)) and host in {"127.0.0.1", "::1"}:
                allow_new_session = True
            else:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Token issuance disabled")
        else:
            if token_issue_secret != settings.TOKEN_ISSUE_SECRET:
                allow_new_session = False
            else:
                allow_new_session = True

    cookie_value = http_request.cookies.get(cookie_name) if hasattr(http_request, "cookies") else None
    user_id = None
    if cookie_value and session_secret:
        user_id = _parse_session_cookie(cookie_value, session_secret)

    if not user_id:
        if not allow_new_session:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        user_id = str(uuid.uuid4())

    if settings.DEBUG and settings.AUTH_ALLOW_CLIENT_USER_ID and request and request.user_id:
        user_id = normalize_uuid(request.user_id)
    
    # 确保用户存在于 users 表中（upsert）
    try:
        await db.execute(
            text("""
                INSERT INTO users (id, created_at)
                VALUES (:user_id, NOW())
                ON CONFLICT (id) DO NOTHING
            """),
            {"user_id": user_id}
        )
        await db.commit()
    except Exception as e:
        # 如果插入失败，继续（用户可能已存在）
        await db.rollback()
    
    token = create_access_token(data={"sub": user_id})
    refresh_token = create_refresh_token(user_id=user_id)

    if session_secret:
        http_response.set_cookie(
            key=cookie_name,
            value=_make_session_cookie(user_id, session_secret),
            httponly=True,
            secure=not settings.DEBUG,
            samesite="lax",
            max_age=int(getattr(settings, "AUTH_SESSION_COOKIE_MAX_AGE_DAYS", 90)) * 24 * 3600,
            path="/",
        )
    
    return TokenResponse(
        access_token=token,
        refresh_token=refresh_token,
        user_id=user_id
    )


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest):
    payload = await verify_refresh_token(request.refresh_token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    await revoke_token_jti(payload.get("jti"), payload.get("exp"))

    token = create_access_token(data={"sub": user_id})
    refresh_token = create_refresh_token(user_id=user_id)

    return TokenResponse(
        access_token=token,
        refresh_token=refresh_token,
        user_id=user_id,
    )


class LogoutRequest(BaseModel):
    refresh_token: str


@router.post("/logout")
async def logout(request: LogoutRequest):
    payload = await verify_refresh_token(request.refresh_token)
    await revoke_token_jti(payload.get("jti"), payload.get("exp"))
    return {"ok": True}


@router.get("/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """获取当前用户信息（需要认证）"""
    return {"user_id": current_user["user_id"]}
