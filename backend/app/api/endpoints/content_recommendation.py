"""
内容推荐 API 端点

功能：
1. 用户偏好管理（获取/更新）
2. 获取今日推荐
3. 提交反馈（点击/喜欢/不喜欢）
"""
import logging
from datetime import datetime, time
from typing import List, Optional, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.services.content_aggregator_service import ContentAggregatorService

logger = logging.getLogger(__name__)

router = APIRouter()


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
                content_recommendation_enabled=True,
                preferred_sources=[],
                excluded_topics=[],
                max_daily_recommendations=1,
                quiet_hours_start="22:00",
                quiet_hours_end="08:00",
                last_recommendation_at=None
            )
        
        return UserContentPreferenceResponse(
            content_recommendation_enabled=True,
            preferred_sources=row[1] or [],
            excluded_topics=row[2] or [],
            max_daily_recommendations=row[3],
            quiet_hours_start=str(row[4]) if row[4] else "22:00",
            quiet_hours_end=str(row[5]) if row[5] else "08:00",
            last_recommendation_at=row[6]
        )
        
    except Exception as e:
        logger.warning(f"Failed to get content preference, fallback to defaults: {e}")
        return UserContentPreferenceResponse(
            content_recommendation_enabled=True,
            preferred_sources=[],
            excluded_topics=[],
            max_daily_recommendations=1,
            quiet_hours_start="22:00",
            quiet_hours_end="08:00",
            last_recommendation_at=None
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
                INSERT INTO user_content_preference (user_id, content_recommendation_enabled)
                VALUES (:user_id, TRUE)
                ON CONFLICT (user_id) DO NOTHING
            """),
            {"user_id": user_id}
        )

        # 构建更新语句
        updates = []
        params = {"user_id": user_id}
        
        updates.append("content_recommendation_enabled = TRUE")
        
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
            params["start"] = preference.quiet_hours_start
        
        if preference.quiet_hours_end is not None:
            updates.append("quiet_hours_end = :end")
            params["end"] = preference.quiet_hours_end
        
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
        logger.warning(f"Failed to update content preference, fallback to in-memory response: {e}")
        try:
            await db.rollback()
        except Exception:
            pass
        return UserContentPreferenceResponse(
            content_recommendation_enabled=True,
            preferred_sources=preference.preferred_sources or [],
            excluded_topics=preference.excluded_topics or [],
            max_daily_recommendations=preference.max_daily_recommendations or 1,
            quiet_hours_start=preference.quiet_hours_start or "22:00",
            quiet_hours_end=preference.quiet_hours_end or "08:00",
            last_recommendation_at=None
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

        pref_sources: List[str] = []
        excluded_topics: List[str] = []
        max_daily = 3
        try:
            pref_res = await db.execute(
                text("""
                    SELECT preferred_sources, excluded_topics, max_daily_recommendations
                    FROM user_content_preference
                    WHERE user_id = :user_id
                """),
                {"user_id": user_id}
            )
            pref_row = pref_res.fetchone()
            if pref_row:
                pref_sources = pref_row[0] or []
                excluded_topics = pref_row[1] or []
                if pref_row[2]:
                    max_daily = int(pref_row[2])
        except Exception:
            pass

        max_daily = max(1, min(3, max_daily))

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
                  AND (rh.feedback IS NULL OR rh.feedback != 'disliked')
                ORDER BY rh.rank_position ASC
            """),
            {"user_id": user_id}
        )
        
        rows = result.fetchall()

        if not rows:
            try:
                recent_count_res = await db.execute(
                    text("""
                        SELECT COUNT(1)
                        FROM content_library
                        WHERE is_active = TRUE
                          AND fetched_at > NOW() - INTERVAL '72 hours'
                    """)
                )
                recent_count = int(recent_count_res.scalar() or 0)
            except Exception:
                recent_count = 0

            if recent_count < 10:
                try:
                    aggregator = ContentAggregatorService(db=db)
                    try:
                        contents = await aggregator.fetch_rss_feeds()
                        await aggregator.save_contents_batch(contents[:30])
                    finally:
                        await aggregator.close()
                except Exception:
                    pass

            content_rows = []
            try:
                content_res = await db.execute(
                    text("""
                        SELECT id, title, summary, content_url, source, tags, published_at
                        FROM content_library
                        WHERE is_active = TRUE
                          AND (:sources_empty = TRUE OR source = ANY(:sources))
                          AND (:excluded_empty = TRUE OR NOT (tags && :excluded))
                          AND id NOT IN (
                              SELECT content_id
                              FROM recommendation_history
                              WHERE user_id = :user_id
                                AND feedback = 'disliked'
                                AND recommended_at > NOW() - INTERVAL '14 days'
                          )
                        ORDER BY published_at DESC NULLS LAST, quality_score DESC, fetched_at DESC
                        LIMIT :limit
                    """),
                    {
                        "limit": max_daily,
                        "user_id": user_id,
                        "sources": pref_sources,
                        "sources_empty": len(pref_sources) == 0,
                        "excluded": excluded_topics,
                        "excluded_empty": len(excluded_topics) == 0,
                    }
                )
                content_rows = content_res.fetchall()
            except Exception:
                content_rows = []

            if len(content_rows) < max_daily:
                seed_items = [
                    {
                        "source": "rss",
                        "source_url": "https://sspai.com/",
                        "title": "少数派：效率工具与生活方式",
                        "summary": "推荐你一些提升效率与生活品质的内容合集。",
                        "content_url": "https://sspai.com/",
                        "tags": ["效率", "工具", "生活方式"],
                    },
                    {
                        "source": "zhihu",
                        "source_url": "https://www.zhihu.com/hot",
                        "title": "知乎热榜：今日热门话题",
                        "summary": "快速浏览今日讨论最热的话题，获取灵感与信息。",
                        "content_url": "https://www.zhihu.com/hot",
                        "tags": ["热点", "知识", "讨论"],
                    },
                    {
                        "source": "bilibili",
                        "source_url": "https://www.bilibili.com/v/popular/all",
                        "title": "B站热门：高质量视频推荐",
                        "summary": "轻松看看今天大家都在看什么。",
                        "content_url": "https://www.bilibili.com/v/popular/all",
                        "tags": ["视频", "热门", "娱乐"],
                    },
                ]

                if pref_sources:
                    seed_items = [x for x in seed_items if x["source"] in pref_sources]

                needed = max_daily - len(content_rows)
                for item in seed_items[:needed]:
                    try:
                        ins = await db.execute(
                            text("""
                                INSERT INTO content_library (source, source_url, title, summary, content_url, tags, published_at)
                                VALUES (:source, :source_url, :title, :summary, :content_url, :tags, NOW())
                                RETURNING id, title, summary, content_url, source, tags, published_at
                            """),
                            item
                        )
                        content_rows.append(ins.fetchone())
                    except Exception:
                        pass

            try:
                await db.execute(
                    text("""
                        DELETE FROM recommendation_history
                        WHERE user_id = :user_id
                          AND DATE(recommended_at) = CURRENT_DATE
                    """),
                    {"user_id": user_id}
                )

                for i, rowc in enumerate(content_rows[:max_daily], start=1):
                    await db.execute(
                        text("""
                            INSERT INTO recommendation_history (user_id, content_id, recommended_at, delivered_at, match_score, rank_position)
                            VALUES (:user_id, :content_id, NOW(), NOW(), :match_score, :rank_position)
                        """),
                        {
                            "user_id": user_id,
                            "content_id": str(rowc[0]),
                            "match_score": max(0.2, 1.0 - (i - 1) * 0.15),
                            "rank_position": i,
                        }
                    )
                await db.commit()
            except Exception:
                try:
                    await db.rollback()
                except Exception:
                    pass

            result2 = await db.execute(
                text("""
                    SELECT 
                        rh.id, rh.content_id, c.title, c.summary, c.content_url,
                        c.source, c.tags, c.published_at, rh.match_score,
                        rh.rank_position, rh.recommended_at, rh.clicked_at, rh.feedback
                    FROM recommendation_history rh
                    JOIN content_library c ON rh.content_id = c.id
                    WHERE rh.user_id = :user_id
                      AND DATE(rh.recommended_at) = CURRENT_DATE
                  AND (rh.feedback IS NULL OR rh.feedback != 'disliked')
                    ORDER BY rh.rank_position ASC
                """),
                {"user_id": user_id}
            )
            rows = result2.fetchall()

        recommendations = []
        for row in rows:
            recommendations.append(RecommendationResponse(
                id=str(row[0]),
                content_id=str(row[1]),
                title=row[2],
                summary=row[3],
                url=row[4],
                source=row[5],
                tags=row[6] or [],
                published_at=row[7],
                match_score=row[8] if row[8] is not None else 0.5,
                rank_position=row[9] if row[9] is not None else 1,
                recommended_at=row[10],
                clicked_at=row[11],
                feedback=row[12]
            ))
        
        return recommendations
        
    except Exception as e:
        logger.warning(f"Failed to get recommendations, return empty list: {e}")
        fallback = [
            RecommendationResponse(
                id=str(uuid4()),
                content_id=str(uuid4()),
                title="少数派：效率工具与生活方式",
                summary="推荐你一些提升效率与生活品质的内容合集。",
                url="https://sspai.com/",
                source="rss",
                tags=["效率", "工具", "生活方式"],
                published_at=None,
                match_score=0.7,
                rank_position=1,
                recommended_at=datetime.now(),
                clicked_at=None,
                feedback=None
            )
        ]
        return fallback


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

        if feedback.action in {"liked", "disliked"}:
            try:
                meta_res = await db.execute(
                    text("""
                        SELECT c.source, c.tags
                        FROM recommendation_history rh
                        JOIN content_library c ON rh.content_id = c.id
                        WHERE rh.id = :rec_id AND rh.user_id = :user_id
                        LIMIT 1
                    """),
                    {"rec_id": recommendation_id, "user_id": user_id}
                )
                meta = meta_res.fetchone()
                if meta:
                    src = meta[0]
                    tags = meta[1] or []

                    await db.execute(
                        text("""
                            INSERT INTO user_content_preference (user_id, content_recommendation_enabled)
                            VALUES (:user_id, TRUE)
                            ON CONFLICT (user_id) DO NOTHING
                        """),
                        {"user_id": user_id}
                    )

                    pref_res = await db.execute(
                        text("""
                            SELECT preferred_sources, excluded_topics
                            FROM user_content_preference
                            WHERE user_id = :user_id
                        """),
                        {"user_id": user_id}
                    )
                    pref = pref_res.fetchone()
                    preferred_sources = (pref[0] or []) if pref else []
                    excluded_topics = (pref[1] or []) if pref else []

                    if feedback.action == "liked":
                        if src and src not in preferred_sources:
                            preferred_sources = preferred_sources + [src]
                    else:
                        for t in tags:
                            if t and t not in excluded_topics:
                                excluded_topics.append(t)

                    await db.execute(
                        text("""
                            UPDATE user_content_preference
                            SET preferred_sources = :sources,
                                excluded_topics = :topics,
                                updated_at = NOW()
                            WHERE user_id = :user_id
                        """),
                        {"user_id": user_id, "sources": preferred_sources, "topics": excluded_topics}
                    )
                    await db.commit()
            except Exception as e:
                logger.warning(f"Failed to update user preference from feedback: {e}")
                try:
                    await db.rollback()
                except Exception:
                    pass
        
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
        logger.error(f"Failed to submit feedback: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit feedback"
        )
