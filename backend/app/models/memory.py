"""记忆模型"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Float, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import uuid

from app.core.database import Base


class Memory(Base):
    """记忆表"""
    __tablename__ = "memories"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1024), nullable=True)  # pgvector
    valence = Column(Float, nullable=True)  # 情感正负向 [-1, 1]
    status = Column(String(20), default="pending")  # pending, committed, deleted
    conversation_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    committed_at = Column(DateTime, nullable=True)
    meta = Column("metadata", JSON, nullable=False, default=dict)
    
    # 关系
    user = relationship("User", back_populates="memories")
    outbox_events = relationship("OutboxEvent", back_populates="memory", cascade="all, delete-orphan")


class IdMapping(Base):
    """ID 映射表 - 三方数据一致性"""
    __tablename__ = "id_mapping"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    postgres_id = Column(UUID(as_uuid=True), nullable=False)
    neo4j_id = Column(String(100), nullable=True)
    milvus_id = Column(String, nullable=True)  # BIGINT stored as string
    entity_type = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DeletionAudit(Base):
    """删除审计表"""
    __tablename__ = "deletion_audit"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    deletion_type = Column(String(50), nullable=False)
    affected_records = Column(JSON, nullable=False)
    requested_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    audit_hash = Column(String(128), nullable=False)
    signature = Column(Text, nullable=True)
    status = Column(String(20), default="pending")  # pending, completed, failed
