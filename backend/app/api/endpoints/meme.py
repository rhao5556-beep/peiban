"""表情包 API 端点"""
import logging
import time
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.meme import Meme
from app.models.user_meme_preference import UserMemePreference
from app.api.schemas.meme import (
    MemeResponse,
    TrendingMemesResponse,
    MemeFeedbackRequest,
    MemeStatsResponse
)
from app.services.meme_usage_history_service import MemeUsageHistoryService
from app.services.content_pool_manager_service import ContentPoolManagerService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/trending", response_model=TrendingMemesResponse)
async def get_trending_memes(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取热门表情包列表
    
    查询条件：
    - status = "approved"
    - safety_status = "approved"
    - trend_level in ["hot", "peak"]
    - 检查用户选择退出偏好
    
    Args:
        limit: 返回数量限制（默认20，最大100）
        current_user: 当前用户
        db: 数据库会话
    
    Returns:
        TrendingMemesResponse: 热门表情包列表
    """
    try:
        # 1. 检查用户选择退出偏好
        pref_result = await db.execute(
            select(UserMemePreference).where(
                UserMemePreference.user_id == current_user["user_id"]
            )
        )
        preference = pref_result.scalar_one_or_none()
        
        # 如果用户选择退出，返回空列表
        if preference and not preference.meme_enabled:
            logger.info(f"User {current_user['user_id']} has opted out of memes")
            return TrendingMemesResponse(memes=[], total=0)
        
        # 2. 查询热门表情包
        query = select(Meme).where(
            and_(
                Meme.status == "approved",
                Meme.safety_status == "approved",
                Meme.trend_level.in_(["hot", "peak"])
            )
        ).order_by(Meme.trend_score.desc()).limit(limit)
        
        result = await db.execute(query)
        memes = result.scalars().all()
        
        # 3. 转换为响应模型
        meme_responses = [
            MemeResponse(
                id=meme.id,
                image_url=meme.image_url,
                text_description=meme.text_description,
                source_platform=meme.source_platform,
                category=meme.category,
                trend_score=meme.trend_score,
                trend_level=meme.trend_level,
                usage_count=meme.usage_count
            )
            for meme in memes
        ]
        
        logger.info(
            f"Retrieved {len(meme_responses)} trending memes for user {current_user['user_id']}"
        )
        
        return TrendingMemesResponse(
            memes=meme_responses,
            total=len(meme_responses)
        )
        
    except Exception as e:
        logger.error(f"Failed to get trending memes: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve trending memes"
        )


@router.post("/feedback", status_code=status.HTTP_200_OK)
async def submit_meme_feedback(
    feedback: MemeFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    提交表情包反馈
    
    Args:
        feedback: 反馈请求（包含 usage_id 和 reaction）
        current_user: 当前用户
        db: 数据库会话
    
    Returns:
        成功响应
    """
    try:
        # 验证反应类型
        valid_reactions = ["liked", "ignored", "disliked"]
        if feedback.reaction not in valid_reactions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid reaction. Must be one of: {valid_reactions}"
            )
        
        user_id = UUID(str(current_user["user_id"]))

        try:
            from app.core.database import get_redis_client
            redis = get_redis_client()
            key = f"meme:feedback:{user_id}:{int(time.time() // 60)}"
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 120)
            if count > 30:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many feedback requests"
                )
        except HTTPException:
            raise
        except Exception:
            pass

        # 初始化服务
        usage_history_service = MemeUsageHistoryService(db)
        
        # 记录反馈
        success = await usage_history_service.record_feedback(
            usage_id=feedback.usage_id,
            user_id=user_id,
            reaction=feedback.reaction
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usage record not found"
            )
        
        logger.info(f"Recorded meme feedback: user_id_prefix={str(user_id)[:8]}, reaction={feedback.reaction}")
        
        return {
            "success": True,
            "message": "Feedback recorded successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record meme feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record feedback"
        )


@router.get("/stats", response_model=MemeStatsResponse)
async def get_meme_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取表情包系统统计信息
    
    Args:
        current_user: 当前用户
        db: 数据库会话
    
    Returns:
        MemeStatsResponse: 统计信息
    """
    try:
        # 初始化服务
        pool_manager = ContentPoolManagerService(db)
        usage_history_service = MemeUsageHistoryService(db)
        
        # 1. 获取内容池统计
        pool_stats = await pool_manager.get_statistics()
        
        # 2. 计算接受率
        acceptance_rate = await usage_history_service.calculate_acceptance_rate()
        
        # 3. 构建响应
        stats = MemeStatsResponse(
            total_memes=pool_stats.get("total_memes", 0),
            approved_memes=pool_stats.get("approved_memes", 0),
            trending_memes=(
                pool_stats.get("hot_memes", 0) + 
                pool_stats.get("peak_memes", 0)
            ),
            acceptance_rate=acceptance_rate,
            avg_trend_score=pool_stats.get("avg_trend_score", 0.0)
        )
        
        logger.info(f"Retrieved meme stats for user {current_user['user_id']}")
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get meme stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics"
        )


@router.get("/preferences", response_model=dict)
async def get_meme_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户表情包偏好设置
    
    Args:
        current_user: 当前用户
        db: 数据库会话
    
    Returns:
        用户偏好设置
    """
    try:
        # 查询用户偏好
        result = await db.execute(
            select(UserMemePreference).where(
                UserMemePreference.user_id == current_user["user_id"]
            )
        )
        preference = result.scalar_one_or_none()
        
        # 如果不存在，创建默认偏好
        if not preference:
            preference = UserMemePreference(
                user_id=current_user["user_id"],
                meme_enabled=True
            )
            db.add(preference)
            await db.commit()
            await db.refresh(preference)
        
        return {
            "user_id": str(preference.user_id),
            "meme_enabled": preference.meme_enabled,
            "created_at": preference.created_at.isoformat(),
            "updated_at": preference.updated_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get meme preferences: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve preferences"
        )


@router.put("/preferences", response_model=dict)
async def update_meme_preferences(
    meme_enabled: bool,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新用户表情包偏好设置
    
    Args:
        meme_enabled: 是否启用表情包
        current_user: 当前用户
        db: 数据库会话
    
    Returns:
        更新后的偏好设置
    """
    try:
        # 查询用户偏好
        result = await db.execute(
            select(UserMemePreference).where(
                UserMemePreference.user_id == current_user["user_id"]
            )
        )
        preference = result.scalar_one_or_none()
        
        # 如果不存在，创建新偏好
        if not preference:
            preference = UserMemePreference(
                user_id=current_user["user_id"],
                meme_enabled=meme_enabled
            )
            db.add(preference)
        else:
            # 更新现有偏好
            preference.meme_enabled = meme_enabled
        
        await db.commit()
        await db.refresh(preference)
        
        logger.info(
            f"Updated meme preferences for user {current_user['user_id']}: "
            f"meme_enabled={meme_enabled}"
        )
        
        return {
            "user_id": str(preference.user_id),
            "meme_enabled": preference.meme_enabled,
            "created_at": preference.created_at.isoformat(),
            "updated_at": preference.updated_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to update meme preferences: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update preferences"
        )
