"""认证端点"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.core.database import get_db
from app.core.ids import normalize_uuid

router = APIRouter()


class TokenRequest(BaseModel):
    """Token 请求"""
    user_id: str = None  # 可选，不提供则自动生成


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    token_type: str = "bearer"
    user_id: str


@router.post("/token", response_model=TokenResponse)
async def get_token(request: TokenRequest = None, db: AsyncSession = Depends(get_db)):
    """
    获取访问 Token
    
    MVP 阶段简化认证：
    - 提供 user_id 则使用该 ID
    - 不提供则自动生成新用户 ID
    - 自动确保用户存在于 users 表中
    """
    user_id = normalize_uuid(request.user_id) if request and request.user_id else str(uuid.uuid4())
    
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
    
    return TokenResponse(
        access_token=token,
        user_id=user_id
    )


@router.get("/me")
async def get_current_user_info():
    """获取当前用户信息（需要认证）"""
    # 这里会被 security 依赖处理
    return {"message": "Authenticated"}
