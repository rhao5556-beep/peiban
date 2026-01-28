"""Outbox 模型"""
from datetime import datetime, time
from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, JSON, Boolean, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class OutboxEvent(Base):
    """Outbox 事件表"""
    __tablename__ = "outbox_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(String(64), unique=True, nullable=False)
    memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=True)
    payload = Column(JSON, nullable=False)
    status = Column(String(20), default="pending")  # pending, processing, done, failed, dlq, pending_review
    retry_count = Column(Integer, default=0)
    idempotency_key = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    processing_started_at = Column(DateTime, nullable=True)
    milvus_written_at = Column(DateTime, nullable=True)
    neo4j_written_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # 关系
    memory = relationship("Memory", back_populates="outbox_events")


class IdempotencyKey(Base):
    """幂等键表"""
    __tablename__ = "idempotency_keys"
    
    key = Column(String(64), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    response = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class ProactiveMessage(Base):
    """主动消息表"""
    __tablename__ = "proactive_messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    trigger_type = Column(String(50), nullable=False)  # time, silence, decay, event, weather, emotion
    trigger_rule_id = Column(String(100), nullable=True)
    content = Column(Text, nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    user_response = Column(String(20), nullable=True)  # replied, ignored, disabled
    status = Column(String(20), default="pending")  # pending, sent, delivered, read, cancelled, ignored
    message_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserProactivePreference(Base):
    """用户主动消息偏好设置表"""
    __tablename__ = "user_proactive_preferences"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    proactive_enabled = Column(Boolean, default=True)
    morning_greeting = Column(Boolean, default=True)
    evening_greeting = Column(Boolean, default=False)
    silence_reminder = Column(Boolean, default=True)
    event_reminder = Column(Boolean, default=True)
    quiet_hours_start = Column(Time, default=time(22, 0))
    quiet_hours_end = Column(Time, default=time(8, 0))
    max_daily_messages = Column(Integer, default=2)
    preferred_greeting_time = Column(Time, nullable=True)
    timezone = Column(String(64), default="Asia/Shanghai")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
