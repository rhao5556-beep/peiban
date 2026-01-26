"""表情包模型"""
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, Text, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class Meme(Base):
    """表情包内容池表"""
    __tablename__ = "memes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # 内容字段
    image_url = Column(Text, nullable=True)  # MVP阶段纯文本表情包可为空
    text_description = Column(Text, nullable=False)  # 必需：表情包文本描述
    source_platform = Column(String(50), nullable=False)  # 'weibo', 'douyin', 'bilibili'
    category = Column(String(50), nullable=True)  # 'humor', 'emotion', 'trending_phrase'
    
    # 去重与来源追踪
    content_hash = Column(String(64), nullable=False, unique=True)  # SHA256(text + normalized_url) 跨平台去重
    original_source_url = Column(Text, nullable=True)  # 原始来源URL（审计用）
    
    # 热度跟踪
    popularity_score = Column(Float, default=0.0)  # 平台初始热度
    trend_score = Column(Float, default=0.0)  # 计算的趋势分数 (0-100)
    trend_level = Column(String(20), default='emerging')  # 'emerging', 'rising', 'hot', 'peak', 'declining'
    
    # 安全合规
    safety_status = Column(String(20), default='pending')  # 'pending', 'approved', 'rejected', 'flagged'
    safety_check_details = Column(JSONB, nullable=True)  # 安全检查详细结果（审计用）
    
    # 生命周期跟踪
    status = Column(String(20), default='candidate')  # 'candidate', 'approved', 'rejected', 'archived'
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 使用统计
    usage_count = Column(Integer, default=0)
    
    # 关系
    usage_history = relationship("MemeUsageHistory", back_populates="meme", cascade="all, delete-orphan")
    
    # 约束
    __table_args__ = (
        CheckConstraint(
            "trend_level IN ('emerging', 'rising', 'hot', 'peak', 'declining')",
            name='trend_level_check'
        ),
        CheckConstraint(
            "safety_status IN ('pending', 'approved', 'rejected', 'flagged')",
            name='safety_status_check'
        ),
        CheckConstraint(
            "status IN ('candidate', 'approved', 'rejected', 'archived')",
            name='status_check'
        ),
        CheckConstraint(
            "trend_score >= 0 AND trend_score <= 100",
            name='trend_score_range'
        ),
        CheckConstraint(
            "popularity_score >= 0",
            name='popularity_score_range'
        ),
        # 查询优化索引
        Index('idx_meme_status_trend', 'status', 'trend_level'),
        Index('idx_meme_safety_status', 'safety_status'),
        Index('idx_meme_trend_score', 'trend_score', postgresql_ops={'trend_score': 'DESC'}),
        Index('idx_meme_content_hash', 'content_hash'),
        Index('idx_meme_source_platform', 'source_platform'),
        Index('idx_meme_first_seen_at', 'first_seen_at', postgresql_ops={'first_seen_at': 'DESC'}),
    )
