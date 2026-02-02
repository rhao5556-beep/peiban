"""记忆-实体桥接模型"""
from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class MemoryEntity(Base):
    __tablename__ = "memory_entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False)

    entity_id = Column(String(128), nullable=False)
    entity_name = Column(Text, nullable=True)
    entity_type = Column(String(50), nullable=True)

    confidence = Column(Float, nullable=True, default=0.8)
    source = Column(String(50), nullable=True, default="llm")
    created_at = Column(DateTime, default=datetime.utcnow)

    memory = relationship("Memory")

