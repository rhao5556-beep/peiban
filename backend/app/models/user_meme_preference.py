"""用户表情包偏好模型"""
from datetime import datetime
from sqlalchemy import Column, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.core.database import Base


class UserMemePreference(Base):
    """用户表情包偏好表"""
    __tablename__ = "user_meme_preferences"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    meme_enabled = Column(Boolean, default=True)  # 用户退出控制
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 索引
    __table_args__ = (
        Index('idx_user_meme_pref_enabled', 'meme_enabled', postgresql_where="meme_enabled = TRUE"),
    )
