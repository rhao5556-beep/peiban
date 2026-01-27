"""
内容推荐 API 端点

功能：
1. 用户偏好管理（获取/更新）
2. 获取今日推荐
3. 提交反馈（点击/喜欢/不喜欢）
"""
import logging
from datetime import datetime, time as time_type
from typing import List, Optional, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.database import get_neo4j_driver
from app.core.security import get_current_user
from app.services.content_recommendation_service import ContentRecommendationService

logger = logging.getLogger(__name__)

router = APIRouter()

def _parse_time_str(value: str) -> time_type:
    value = (value or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            dt = datetime.strptime(value, fmt)
            return time_type(dt.hour, dt.minute, dt.second)
        except ValueError:
            continue
    raise ValueError(f"Invalid time format: {value}")


# ==================== Pydantic 模型 ====================

class UserContentPreferenceResponse(BaseModel):
    """用户内容偏好响应"""
    content_recommendation_enabled: bool
    preferred_sources: List[str] = Field(default_factory=list)
    excluded_topics: List[str] = Field(default_factory=list)
    max_daily_recommendations: int = 1
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "08:00"
    last_recommendation_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UserContentPreferenceUpdate(BaseModel):
    """用户内容偏好更新"""
    content_recommendation_enabled: Optional[bool] = None
    preferred_sources: Optional[List[str]] = None
    excluded_topics: Optional[List[str]] = None
    max_daily_recommendations: Optional[int] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


class RecommendationResponse(BaseModel):
    """推荐内容响应"""
    id: str
    content_id: str
    title: str
    summary: Optional[str]
    url: str
    source: str
    tags: List[str]
    published_at: Optional[datetime]
    match_score: float
    rank_position: int
    recommended_at: datetime
    clicked_at: Optional[datetime] = None
    feedback: Optional[str] = None
    
    class Config:
        from_attributes = True


class FeedbackRequest(BaseModel):
    """反馈请求"""
    action: Literal["clicked", "liked", "disliked", "ignored"]


class SuccessResponse(BaseModel):
    """成功响应"""
    success: bool
    message: str


# ==================== API 端点 ====================

@router.get("/content/preference", response_model=UserContentPreferenceResponse)
async def get_content_preference(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户内容推荐偏好
    
    Returns:
        UserContentPreferenceResponse: 用户偏好设置
    """
    try:
        user_id = current_user["user_id"]
        result = await db.execute(
            text("""
                SELECT content_recommendation_enabled, preferred_sources,
                       excluded_topics, max_daily_recommendations,
                       quiet_hours_start, quiet_hours_end, last_recommendation_at
                FROM user_content_preference
                WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        )
        
        row = result.fetchone()
        
        if not row:
            # 如果不存在，创建默认偏好
            await db.execute(
                text("""
                    INSERT INTO user_content_preference (user_id)
                    VALUES (:user_id)
                """),
                {"user_id": user_id}
            )
            await db.commit()
            
            # 返回默认值
            return UserContentPreferenceResponse(
                content_recommendation_enabled=False,
                preferred_sources=[],
                excluded_topics=[],
                max_daily_recommendations=1,
                quiet_hours_start="22:00",
                quiet_hours_end="08:00",
                last_recommendation_at=None
            )
        
        return UserContentPreferenceResponse(
            content_recommendation_enabled=row[0],
            preferred_sources=row[1] or [],
            excluded_topics=row[2] or [],
            max_daily_recommendations=row[3],
            quiet_hours_start=str(row[4]) if row[4] else "22:00",
            quiet_hours_end=str(row[5]) if row[5] else "08:00",
            last_recommendation_at=row[6]
        )
        
    except Exception as e:
        logger.exception("Failed to get content preference")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get content preference"
        )


@router.put("/content/preference", response_model=UserContentPreferenceResponse)
async def update_content_preference(
    preference: UserContentPreferenceUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新用户内容推荐偏好
    
    Args:
        preference: 偏好更新数据
        
    Returns:
        UserContentPreferenceResponse: 更新后的偏好设置
    """
    try:
        user_id = current_user["user_id"]
        await db.execute(
            text("""
                INSERT INTO user_content_preference (user_id)
                VALUES (:user_id)
                ON CONFLICT (user_id) DO NOTHING
            """),
            {"user_id": user_id}
        )
        # 构建更新语句
        updates = []
        params = {"user_id": user_id}
        
        if preference.content_recommendation_enabled is not None:
            updates.append("content_recommendation_enabled = :enabled")
            params["enabled"] = preference.content_recommendation_enabled
        
        if preference.preferred_sources is not None:
            updates.append("preferred_sources = :sources")
            params["sources"] = preference.preferred_sources
        
        if preference.excluded_topics is not None:
            updates.append("excluded_topics = :topics")
            params["topics"] = preference.excluded_topics
        
        if preference.max_daily_recommendations is not None:
            updates.append("max_daily_recommendations = :max_daily")
            params["max_daily"] = preference.max_daily_recommendations
        
        if preference.quiet_hours_start is not None:
            updates.append("quiet_hours_start = :start")
            params["start"] = _parse_time_str(preference.quiet_hours_start)
        
        if preference.quiet_hours_end is not None:
            updates.append("quiet_hours_end = :end")
            params["end"] = _parse_time_str(preference.quiet_hours_end)
        
        if updates:
            updates.append("updated_at = NOW()")
            
            query = f"""
                UPDATE user_content_preference
                SET {', '.join(updates)}
                WHERE user_id = :user_id
            """
            
            await db.execute(text(query), params)
            await db.commit()
        
        # 返回更新后的偏好
        return await get_content_preference(current_user, db)
        
    except Exception as e:
        logger.exception("Failed to update content preference")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update content preference"
        )


@router.get("/content/recommendations", response_model=List[RecommendationResponse])
async def get_recommendations(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取今日推荐内容
    
    Returns:
        List[RecommendationResponse]: 推荐列表
    """
    try:
        user_id = current_user["user_id"]
        result = await db.execute(
            text("""
                SELECT 
                    rh.id, rh.content_id, c.title, c.summary, c.content_url,
                    c.source, c.tags, c.published_at, rh.match_score,
                    rh.rank_position, rh.recommended_at, rh.clicked_at, rh.feedback
                FROM recommendation_history rh
                JOIN content_library c ON rh.content_id = c.id
                WHERE rh.user_id = :user_id
                  AND DATE(rh.recommended_at) = CURRENT_DATE
                ORDER BY rh.rank_position ASC
            """),
            {"user_id": user_id}
        )
        
        recommendations = []
        for row in result.fetchall():
            recommendations.append(RecommendationResponse(
                id=str(row[0]),
                content_id=str(row[1]),
                title=row[2],
                summary=row[3],
                url=row[4],
                source=row[5],
                tags=row[6] or [],
                published_at=row[7],
                match_score=row[8],
                rank_position=row[9],
                recommended_at=row[10],
                clicked_at=row[11],
                feedback=row[12]
            ))
        
        if not recommendations:
            preference = await get_content_preference(current_user, db)
            service = ContentRecommendationService(db=db, neo4j_driver=get_neo4j_driver())
            try:
                await service.generate_recommendations(
                    user_id=str(user_id),
                    top_k=preference.max_daily_recommendations or 1
                )
            except Exception:
                logger.exception("Failed to generate recommendations on-demand")
                return []

            result = await db.execute(
                text("""
                    SELECT 
                        rh.id, rh.content_id, c.title, c.summary, c.content_url,
                        c.source, c.tags, c.published_at, rh.match_score,
                        rh.rank_position, rh.recommended_at, rh.clicked_at, rh.feedback
                    FROM recommendation_history rh
                    JOIN content_library c ON rh.content_id = c.id
                    WHERE rh.user_id = :user_id
                      AND DATE(rh.recommended_at) = CURRENT_DATE
                    ORDER BY rh.rank_position ASC
                """),
                {"user_id": user_id}
            )

            for row in result.fetchall():
                recommendations.append(RecommendationResponse(
                    id=str(row[0]),
                    content_id=str(row[1]),
                    title=row[2],
                    summary=row[3],
                    url=row[4],
                    source=row[5],
                    tags=row[6] or [],
                    published_at=row[7],
                    match_score=row[8],
                    rank_position=row[9],
                    recommended_at=row[10],
                    clicked_at=row[11],
                    feedback=row[12]
                ))

        return recommendations
        
    except Exception as e:
        logger.exception("Failed to get recommendations")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get recommendations"
        )


@router.post(
    "/content/recommendations/{recommendation_id}/feedback",
    response_model=SuccessResponse
)
async def submit_feedback(
    recommendation_id: str,
    feedback: FeedbackRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    提交推荐反馈
    
    Args:
        recommendation_id: 推荐记录 ID
        feedback: 反馈数据（clicked/liked/disliked/ignored）
        
    Returns:
        SuccessResponse: 成功响应
    """
    try:
        user_id = current_user["user_id"]
        # 验证推荐记录是否属于当前用户
        result = await db.execute(
            text("""
                SELECT id FROM recommendation_history
                WHERE id = :rec_id AND user_id = :user_id
            """),
            {"rec_id": recommendation_id, "user_id": user_id}
        )
        
        if not result.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recommendation not found"
            )
        
        # 更新反馈
        if feedback.action == "clicked":
            await db.execute(
                text("""
                    UPDATE recommendation_history
                    SET clicked_at = NOW(), delivered_at = NOW()
                    WHERE id = :rec_id
                """),
                {"rec_id": recommendation_id}
            )
        else:
            await db.execute(
                text("""
                    UPDATE recommendation_history
                    SET feedback = :feedback, feedback_at = NOW()
                    WHERE id = :rec_id
                """),
                {"rec_id": recommendation_id, "feedback": feedback.action}
            )
        
        await db.commit()
        
        # 更新 Prometheus 指标
        try:
            from prometheus_client import Counter
            
            if feedback.action == "clicked":
                recommendation_clicks = Counter(
                    'recommendation_clicks_total',
                    'Total number of recommendation clicks',
                    ['source']
                )
                # 获取来源
                source_result = await db.execute(
                    text("""
                        SELECT c.source FROM recommendation_history rh
                        JOIN content_library c ON rh.content_id = c.id
                        WHERE rh.id = :rec_id
                    """),
                    {"rec_id": recommendation_id}
                )
                source_row = source_result.fetchone()
                if source_row:
                    recommendation_clicks.labels(source=source_row[0]).inc()
            
            elif feedback.action == "liked":
                recommendation_likes = Counter(
                    'recommendation_likes_total',
                    'Total number of recommendation likes',
                    ['source']
                )
                source_result = await db.execute(
                    text("""
                        SELECT c.source FROM recommendation_history rh
                        JOIN content_library c ON rh.content_id = c.id
                        WHERE rh.id = :rec_id
                    """),
                    {"rec_id": recommendation_id}
                )
                source_row = source_result.fetchone()
                if source_row:
                    recommendation_likes.labels(source=source_row[0]).inc()
            
            elif feedback.action == "disliked":
                recommendation_dislikes = Counter(
                    'recommendation_dislikes_total',
                    'Total number of recommendation dislikes',
                    ['source']
                )
                source_result = await db.execute(
                    text("""
                        SELECT c.source FROM recommendation_history rh
                        JOIN content_library c ON rh.content_id = c.id
                        WHERE rh.id = :rec_id
                    """),
                    {"rec_id": recommendation_id}
                )
                source_row = source_result.fetchone()
                if source_row:
                    recommendation_dislikes.labels(source=source_row[0]).inc()
        except Exception as e:
            logger.warning(f"Failed to update metrics: {e}")
        
        return SuccessResponse(
            success=True,
            message=f"Feedback '{feedback.action}' recorded successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to submit feedback")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit feedback"
        )
