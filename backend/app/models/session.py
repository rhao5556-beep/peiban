"""会话模型"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class Session(Base):
    """会话表"""
    __tablename__ = "sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    summary = Column(Text, nullable=True)
    turn_count = Column(Integer, default=0)
    
    # 关系
    user = relationship("User", back_populates="sessions")
    turns = relationship("ConversationTurn", back_populates="session", cascade="all, delete-orphan")


class ConversationTurn(Base):
    """对话轮次表"""
    __tablename__ = "conversation_turns"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(10), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    emotion_result = Column(JSON, nullable=True)
    affinity_at_turn = Column(String, nullable=True)  # Float stored as string
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    session = relationship("Session", back_populates="turns")
