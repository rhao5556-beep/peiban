import random
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meme import Meme
from app.models.meme_usage_history import MemeUsageHistory
from app.models.user_meme_preference import UserMemePreference
from app.services.meme_usage_history_service import MemeUsageHistoryService


class MemeInjectionService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def maybe_select_and_record(
        self,
        user_id: str,
        session_id: str,
        emotion_valence: Optional[float] = None,
        max_candidates: int = 20,
    ) -> Optional[dict]:
        try:
            user_uuid = UUID(user_id)
            session_uuid = UUID(session_id)
        except Exception:
            return None

        pref_result = await self.db.execute(
            select(UserMemePreference).where(UserMemePreference.user_id == user_uuid)
        )
        preference = pref_result.scalar_one_or_none()
        if preference and not preference.meme_enabled:
            return None

        now = datetime.utcnow()
        recent_usage_result = await self.db.execute(
            select(MemeUsageHistory.id).where(
                and_(
                    MemeUsageHistory.user_id == user_uuid,
                    MemeUsageHistory.conversation_id == session_uuid,
                    MemeUsageHistory.used_at >= now - timedelta(minutes=10),
                )
            ).limit(1)
        )
        if recent_usage_result.scalar_one_or_none() is not None:
            return None

        valence = float(emotion_valence) if emotion_valence is not None else 0.0
        p = 0.35
        if valence <= -0.2:
            p = 0.12
        elif valence >= 0.3:
            p = 0.45

        if random.random() > p:
            return None

        usage_history_service = MemeUsageHistoryService(self.db)
        recent_usage = await usage_history_service.get_recent_usage(user_uuid, hours=24)
        recently_used_meme_ids = {u.meme_id for u in recent_usage}

        result = await self.db.execute(
            select(Meme).where(
                and_(
                    Meme.status == "approved",
                    Meme.safety_status == "approved",
                    Meme.trend_level.in_(["hot", "peak"]),
                )
            ).order_by(Meme.trend_score.desc()).limit(max_candidates)
        )
        candidates = [m for m in result.scalars().all() if m.id not in recently_used_meme_ids]
        if not candidates:
            return None

        pick_pool = candidates[: min(10, len(candidates))]
        meme = random.choice(pick_pool)

        usage = await usage_history_service.record_usage(
            user_id=user_uuid,
            meme_id=meme.id,
            conversation_id=session_uuid,
        )

        return {
            "meme": {
                "id": str(meme.id),
                "image_url": meme.image_url,
                "text_description": meme.text_description,
                "source_platform": meme.source_platform,
                "category": meme.category,
                "trend_score": meme.trend_score,
                "trend_level": meme.trend_level,
                "usage_count": meme.usage_count,
            },
            "usage_id": str(usage.id),
        }

