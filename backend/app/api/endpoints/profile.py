"""用户画像端点"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.core.database import get_db
from app.services.user_profile_service import (
    UserProfileService,
    ProfileUpdateSignals as ServiceSignals
)

router = APIRouter()


class PersonalityTraitsResponse(BaseModel):
    """性格特征响应"""
    introvert_extrovert: float
    optimist_pessimist: float
    analytical_emotional: float
    confidence: float


class CommunicationStyleResponse(BaseModel):
    """沟通风格响应"""
    avg_message_length: float
    emoji_frequency: float
    question_frequency: float
    response_speed_preference: str


class InterestResponse(BaseModel):
    """兴趣偏好响应"""
    name: str
    category: str
    sentiment: str
    weight: float


class UserProfileResponse(BaseModel):
    """用户画像响应"""
    user_id: str
    personality: PersonalityTraitsResponse
    interests: List[InterestResponse]
    communication_style: CommunicationStyleResponse
    active_hours: List[int]
    topic_preferences: Dict[str, float]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    staleness_days: int
    is_stale: bool


class ProfileUpdateRequest(BaseModel):
    """画像更新请求"""
    message_length: Optional[int] = None
    has_emoji: bool = False
    has_question: bool = False
    emotion_valence: float = 0.0
    topics_mentioned: List[str] = []
    hour_of_day: Optional[int] = None


@router.get("/{user_id}/profile", response_model=UserProfileResponse)
async def get_user_profile(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户画像
    
    返回用户的性格特征、兴趣偏好、沟通风格等聚合信息
    """
    # 验证权限（只能查看自己的画像）
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Cannot access other user's profile")
    
    try:
        profile_service = UserProfileService()
        profile = await profile_service.get_profile(user_id)
        
        return UserProfileResponse(
            user_id=profile.user_id,
            personality=PersonalityTraitsResponse(
                introvert_extrovert=profile.personality.introvert_extrovert,
                optimist_pessimist=profile.personality.optimist_pessimist,
                analytical_emotional=profile.personality.analytical_emotional,
                confidence=profile.personality.confidence
            ),
            interests=[
                InterestResponse(
                    name=i.name,
                    category=i.category,
                    sentiment=i.sentiment,
                    weight=i.weight
                )
                for i in profile.interests
            ],
            communication_style=CommunicationStyleResponse(
                avg_message_length=profile.communication_style.avg_message_length,
                emoji_frequency=profile.communication_style.emoji_frequency,
                question_frequency=profile.communication_style.question_frequency,
                response_speed_preference=profile.communication_style.response_speed_preference
            ),
            active_hours=profile.active_hours,
            topic_preferences=profile.topic_preferences,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            staleness_days=profile.staleness_days,
            is_stale=profile.is_stale
        )
        
    except Exception as e:
        import logging
        logging.error(f"Failed to get user profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/profile/update", response_model=UserProfileResponse)
async def update_user_profile(
    user_id: str,
    request: ProfileUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新用户画像（内部使用）
    
    通常由对话服务自动调用，此端点用于测试
    """
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Cannot update other user's profile")
    
    try:
        profile_service = UserProfileService()
        signals = ServiceSignals(
            message_length=request.message_length,
            has_emoji=request.has_emoji,
            has_question=request.has_question,
            emotion_valence=request.emotion_valence,
            topics_mentioned=request.topics_mentioned,
            hour_of_day=request.hour_of_day
        )
        
        profile = await profile_service.update_profile(user_id, signals)
        
        return UserProfileResponse(
            user_id=profile.user_id,
            personality=PersonalityTraitsResponse(
                introvert_extrovert=profile.personality.introvert_extrovert,
                optimist_pessimist=profile.personality.optimist_pessimist,
                analytical_emotional=profile.personality.analytical_emotional,
                confidence=profile.personality.confidence
            ),
            interests=[
                InterestResponse(
                    name=i.name,
                    category=i.category,
                    sentiment=i.sentiment,
                    weight=i.weight
                )
                for i in profile.interests
            ],
            communication_style=CommunicationStyleResponse(
                avg_message_length=profile.communication_style.avg_message_length,
                emoji_frequency=profile.communication_style.emoji_frequency,
                question_frequency=profile.communication_style.question_frequency,
                response_speed_preference=profile.communication_style.response_speed_preference
            ),
            active_hours=profile.active_hours,
            topic_preferences=profile.topic_preferences,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            staleness_days=profile.staleness_days,
            is_stale=profile.is_stale
        )
        
    except Exception as e:
        import logging
        logging.error(f"Failed to update user profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/interests", response_model=List[InterestResponse])
async def get_user_interests(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户兴趣偏好列表"""
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Cannot access other user's interests")
    
    try:
        profile_service = UserProfileService()
        interests = await profile_service.get_interests(user_id)
        
        return [
            InterestResponse(
                name=i.name,
                category=i.category,
                sentiment=i.sentiment,
                weight=i.weight
            )
            for i in interests
        ]
        
    except Exception as e:
        import logging
        logging.error(f"Failed to get user interests: {e}")
        raise HTTPException(status_code=500, detail=str(e))
