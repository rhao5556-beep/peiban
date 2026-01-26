"""上下文记忆模型"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import Column, String, DateTime, Text, Float, ForeignKey, Integer, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import uuid

from app.core.database import Base


class ContextMemory(Base):
    """上下文记忆表 - 存储跨会话的主题连续性"""
    __tablename__ = "context_memories"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(UUID(as_uuid=True), nullable=False)
    
    # 摘要内容
    main_topics = Column(ARRAY(Text), nullable=False, default=[])
    key_entities = Column(ARRAY(Text), nullable=False, default=[])
    unfinished_threads = Column(ARRAY(Text), default=[])
    emotional_arc = Column(String(20), default="neutral")
    summary_text = Column(Text, nullable=False)
    
    # 向量嵌入 (用于语义检索)
    embedding = Column(Vector(1024), nullable=True)  # bge-m3 输出维度
    
    # 重要性和访问统计
    importance_score = Column(Float, default=0.5)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime, default=datetime.utcnow)
    access_count = Column(Integer, default=0)
    
    # 关系
    user = relationship("User", back_populates="context_memories")
    
    def __repr__(self):
        return f"<ContextMemory(id={self.id}, user_id={self.user_id}, topics={self.main_topics[:2]})>"
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "session_id": str(self.session_id),
            "main_topics": self.main_topics,
            "key_entities": self.key_entities,
            "unfinished_threads": self.unfinished_threads,
            "emotional_arc": self.emotional_arc,
            "summary_text": self.summary_text,
            "importance_score": self.importance_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "access_count": self.access_count
        }
    
    def update_access(self):
        """更新访问时间和计数"""
        self.last_accessed = datetime.utcnow()
        self.access_count += 1

