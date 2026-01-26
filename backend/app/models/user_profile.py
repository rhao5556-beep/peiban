"""用户画像模型"""
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy import Column, String, DateTime, Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class UserProfile(Base):
    """用户画像表 - 聚合用户特征和偏好"""
    __tablename__ = "user_profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # 性格特征 (范围: -1 到 1)
    introvert_extrovert = Column(Float, default=0)  # -1: 内向, 1: 外向
    optimist_pessimist = Column(Float, default=0)   # -1: 悲观, 1: 乐观
    analytical_emotional = Column(Float, default=0)  # -1: 理性, 1: 感性
    personality_confidence = Column(Float, default=0)  # 置信度 0-1
    
    # 沟通风格
    avg_message_length = Column(Float, default=0)
    emoji_frequency = Column(Float, default=0)  # 0-1
    question_frequency = Column(Float, default=0)  # 0-1
    response_speed_preference = Column(String(20), default="moderate")  # fast, moderate, thoughtful
    
    # 活跃时间 (JSON array of hours 0-23)
    active_hours = Column(JSONB, default=[])
    
    # 话题偏好 (JSON object: topic -> score)
    topic_preferences = Column(JSONB, default={})
    
    # 兴趣标签 (从图谱 LIKES/DISLIKES 聚合)
    interests = Column(JSONB, default=[])
    
    # 统计数据
    total_messages = Column(Integer, default=0)
    total_sessions = Column(Integer, default=0)
    
    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user = relationship("User", back_populates="profile")
    
    def __repr__(self):
        return f"<UserProfile(user_id={self.user_id}, confidence={self.personality_confidence})>"
    
    @property
    def staleness_days(self) -> int:
        """计算数据过期天数"""
        if not self.updated_at:
            return 0
        delta = datetime.utcnow() - self.updated_at
        return delta.days
    
    @property
    def is_stale(self) -> bool:
        """判断数据是否过期 (超过30天未更新)"""
        return self.staleness_days > 30
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "personality": {
                "introvert_extrovert": self.introvert_extrovert,
                "optimist_pessimist": self.optimist_pessimist,
                "analytical_emotional": self.analytical_emotional,
                "confidence": self.personality_confidence
            },
            "communication_style": {
                "avg_message_length": self.avg_message_length,
                "emoji_frequency": self.emoji_frequency,
                "question_frequency": self.question_frequency,
                "response_speed_preference": self.response_speed_preference
            },
            "active_hours": self.active_hours,
            "topic_preferences": self.topic_preferences,
            "interests": self.interests,
            "stats": {
                "total_messages": self.total_messages,
                "total_sessions": self.total_sessions
            },
            "staleness_days": self.staleness_days,
            "is_stale": self.is_stale,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    def get_personality_summary(self) -> str:
        """获取性格摘要描述"""
        traits = []
        
        if self.introvert_extrovert > 0.3:
            traits.append("外向")
        elif self.introvert_extrovert < -0.3:
            traits.append("内向")
        
        if self.optimist_pessimist > 0.3:
            traits.append("乐观")
        elif self.optimist_pessimist < -0.3:
            traits.append("悲观")
        
        if self.analytical_emotional > 0.3:
            traits.append("感性")
        elif self.analytical_emotional < -0.3:
            traits.append("理性")
        
        if not traits:
            return "性格特征尚不明显"
        
        return "、".join(traits)

