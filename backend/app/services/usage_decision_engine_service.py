"""
使用决策引擎服务
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
import uuid

from app.core.config import settings
from app.core.database import get_redis_client
from app.models.meme import Meme
from app.models.meme_usage_history import MemeUsageHistory
from app.models.user_meme_preference import UserMemePreference
from app.models.session import Session
from app.services.meme_usage_history_service import MemeUsageHistoryService
from app.services.tenor_service import TenorService

logger = logging.getLogger(__name__)


class UsageDecisionEngineService:
    """使用决策引擎服务 - 最小实现"""
    
    def __init__(
        self,
        db_session: Optional[AsyncSession] = None,
        content_pool_manager=None,
        usage_history_service=None
    ):
        self.db = db_session
        self.content_pool_manager = content_pool_manager
        self.usage_history_service = usage_history_service

    async def pick_meme_for_chat(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        ai_reply: str,
        emotion: Optional[dict] = None
    ) -> Optional[dict]:
        if not self.db:
            return None

        user_uuid = uuid.UUID(user_id)
        session_uuid = uuid.UUID(session_id)

        try:
            pref_result = await self.db.execute(
                select(UserMemePreference).where(UserMemePreference.user_id == user_uuid)
            )
            preference = pref_result.scalar_one_or_none()
            if preference and not preference.meme_enabled:
                return None
        except Exception:
            pass

        combined = f"{user_message}\n{ai_reply}".lower()
        keywords = ["无语", "笑死", "破防", "救命", "离谱", "懂的都懂", "我真的会谢", "太真实了", "蚌埠住了"]
        picked_kw = next((k for k in keywords if k in combined), None)

        category = "trending_phrase"
        valence = 0.0
        if isinstance(emotion, dict):
            try:
                valence = float(emotion.get("valence", 0.0))
            except Exception:
                valence = 0.0
        if valence < -0.2:
            category = "emotion"
        elif valence > 0.2:
            category = "humor"

        recent_cutoff = datetime.utcnow() - timedelta(hours=6)
        recent_subq = select(MemeUsageHistory.meme_id).where(
            and_(
                MemeUsageHistory.user_id == user_uuid,
                MemeUsageHistory.used_at >= recent_cutoff
            )
        )

        query = select(Meme).where(
            and_(
                Meme.status == "approved",
                Meme.safety_status == "approved",
                ~Meme.id.in_(recent_subq)
            )
        )

        if picked_kw:
            query = query.where(Meme.text_description.ilike(f"%{picked_kw}%"))
        else:
            query = query.where(Meme.category == category)

        query = query.order_by(desc(Meme.trend_score), desc(Meme.first_seen_at)).limit(20)

        result = await self.db.execute(query)
        memes = result.scalars().all()
        if (not memes) and picked_kw:
            query2 = select(Meme).where(
                and_(
                    Meme.status == "approved",
                    Meme.safety_status == "approved",
                    ~Meme.id.in_(recent_subq),
                    Meme.category == category
                )
            ).order_by(desc(Meme.trend_score), desc(Meme.first_seen_at)).limit(20)
            result2 = await self.db.execute(query2)
            memes = result2.scalars().all()
        if not memes:
            query3 = select(Meme).where(
                and_(
                    Meme.status == "approved",
                    Meme.safety_status == "approved",
                    ~Meme.id.in_(recent_subq)
                )
            ).order_by(desc(Meme.trend_score), desc(Meme.first_seen_at)).limit(20)
            result3 = await self.db.execute(query3)
            memes = result3.scalars().all()
        if not memes:
            return None

        meme = memes[0]

        if (not meme.image_url) and settings.MEME_GIF_FETCH_ENABLED:
            redis_client = None
            try:
                redis_client = get_redis_client()
            except Exception:
                redis_client = None
            tenor = TenorService(redis_client=redis_client)
            try:
                url = await tenor.search_first_gif_url(meme.text_description)
                if url:
                    meme.image_url = url
                    await self.db.commit()
            finally:
                await tenor.close()

        usage_service = self.usage_history_service or MemeUsageHistoryService(self.db)
        usage_id = None
        try:
            session_row = (
                await self.db.execute(select(Session).where(Session.id == session_uuid))
            ).scalar_one_or_none()
            if session_row is None:
                self.db.add(Session(id=session_uuid, user_id=user_uuid))
                await self.db.commit()

            usage = await usage_service.record_usage(
                user_id=user_uuid,
                meme_id=meme.id,
                conversation_id=session_uuid
            )
            usage_id = str(usage.id)
        except Exception as e:
            logger.warning(f"Failed to record meme usage: {e}")
            usage_id = str(uuid.uuid4())

        if self.content_pool_manager:
            try:
                await self.content_pool_manager.increment_usage_count(meme.id)
            except Exception:
                pass

        return {
            "meme_id": str(meme.id),
            "usage_id": usage_id,
            "description": meme.text_description,
            "image_url": meme.image_url
        }
