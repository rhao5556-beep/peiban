"""响应缓存模型"""
from datetime import datetime, timedelta
from sqlalchemy import Column, String, DateTime, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.core.database import Base


class ResponseCache(Base):
    """响应缓存表 - 缓存常见问候语的回复"""
    __tablename__ = "response_cache"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_pattern = Column(String(100), nullable=False)
    affinity_state = Column(String(20), nullable=False)
    response = Column(Text, nullable=False)
    hit_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    
    def __repr__(self):
        return f"<ResponseCache(pattern='{self.message_pattern}', state='{self.affinity_state}')>"
    
    @property
    def is_expired(self) -> bool:
        """判断缓存是否过期"""
        return datetime.utcnow() > self.expires_at
    
    def increment_hit(self):
        """增加命中计数"""
        self.hit_count += 1
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": str(self.id),
            "message_pattern": self.message_pattern,
            "affinity_state": self.affinity_state,
            "response": self.response,
            "hit_count": self.hit_count,
            "is_expired": self.is_expired,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }
    
    @classmethod
    def create_with_ttl(
        cls,
        message_pattern: str,
        affinity_state: str,
        response: str,
        ttl_seconds: int = 300
    ) -> "ResponseCache":
        """创建带 TTL 的缓存条目"""
        return cls(
            message_pattern=message_pattern,
            affinity_state=affinity_state,
            response=response,
            expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds)
        )

