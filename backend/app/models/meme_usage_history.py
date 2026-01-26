"""表情包使用历史模型"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class MemeUsageHistory(Base):
    """表情包使用历史表"""
    __tablename__ = "meme_usage_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    meme_id = Column(UUID(as_uuid=True), ForeignKey("memes.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    
    used_at = Column(DateTime, default=datetime.utcnow)
    user_reaction = Column(String(20), nullable=True)  # 'liked', 'ignored', 'disliked'
    
    # 关系
    meme = relationship("Meme", back_populates="usage_history")
    
    # 约束
    __table_args__ = (
        CheckConstraint(
            "user_reaction IN ('liked', 'ignored', 'disliked')",
            name='user_reaction_check'
        ),
        # 查询优化索引
        Index('idx_usage_user_time', 'user_id', 'used_at', postgresql_ops={'used_at': 'DESC'}),
        Index('idx_usage_meme', 'meme_id'),
        Index('idx_usage_conversation', 'conversation_id'),
        Index('idx_usage_reaction', 'user_reaction'),
    )
