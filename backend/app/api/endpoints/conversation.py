"""对话端点"""
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime
import uuid
import logging
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.core.database import get_db, get_neo4j_driver, get_milvus_collection
from app.core.ids import normalize_uuid
from app.models.session import Session, ConversationTurn
from app.services.conversation_service import ConversationService, ConversationMode
from app.services.affinity_service import AffinityService
from app.services.retrieval_service import RetrievalService
from app.services.graph_service import GraphService
from app.services.outbox_service import TransactionManager

logger = logging.getLogger(__name__)
router = APIRouter()


class MessageRequest(BaseModel):
    """消息请求"""
    message: str
    session_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    mode: Literal["graph_only", "hybrid"] = "hybrid"  # 对话模式
    eval_mode: bool = False
    memorize_only: bool = False


class MessageResponse(BaseModel):
    """消息响应"""
    reply: str
    session_id: str
    turn_id: str
    emotion: dict
    affinity: dict
    memories_used: list
    tone_type: str
    response_time_ms: float
    memory_status: str = "pending"  # pending, committed
    mode: str = "hybrid"  # graph_only 或 hybrid
    context_source: Optional[dict] = None  # 上下文来源追踪
    error_code: Optional[str] = None
    trace_id: Optional[str] = None
    error_type: Optional[str] = None


class SessionResponse(BaseModel):
    """会话响应"""
    session_id: str
    user_id: str
    started_at: datetime
    turn_count: int


@router.post("/message", response_model=MessageResponse)
async def send_message(
    request: MessageRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    发送消息（同步模式）
    
    Fast Path: 情感分析 + 检索 + 生成
    Slow Path: 异步写入记忆（通过 Outbox）
    """
    user_id = normalize_uuid(current_user["user_id"])
    session_id = normalize_uuid(request.session_id) if request.session_id else str(uuid.uuid4())
    
    try:
        session_uuid = uuid.UUID(session_id)
        user_uuid = uuid.UUID(user_id)
        await db.execute(
            text(
                """
                INSERT INTO users (id, created_at)
                VALUES (:user_id, NOW())
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"user_id": user_id},
        )
        await db.commit()
        session_row = (
            await db.execute(select(Session).where(Session.id == session_uuid))
        ).scalar_one_or_none()
        if session_row is None:
            db.add(Session(id=session_uuid, user_id=user_uuid))
            await db.commit()

        # 初始化服务
        neo4j_driver = get_neo4j_driver()
        milvus_collection = get_milvus_collection()
        
        graph_service = GraphService(neo4j_driver=neo4j_driver)
        retrieval_service = RetrievalService(
            milvus_client=milvus_collection,
            graph_service=graph_service,
            db_session=db,
        )
        affinity_service = AffinityService()
        
        conversation_service = ConversationService(
            affinity_service=affinity_service,
            retrieval_service=retrieval_service,
            graph_service=graph_service,
            transaction_manager=TransactionManager(db_session=db),
        )
        
        # 调用对话服务（传递 mode 参数实现物理隔离）
        response = await conversation_service.process_message(
            user_id=user_id,
            message=request.message,
            session_id=session_id,
            mode=request.mode,  # graph_only 或 hybrid
            eval_mode=bool(request.eval_mode),
            memorize_only=bool(request.memorize_only),
            idempotency_key=request.idempotency_key,
        )
        
        return MessageResponse(
            reply=response.reply,
            session_id=response.session_id,
            turn_id=response.turn_id,
            emotion=response.emotion,
            affinity=response.affinity,
            memories_used=response.memories_used,
            tone_type=response.tone_type,
            response_time_ms=response.response_time_ms,
            memory_status="pending",
            mode=response.mode,
            context_source=response.context_source
        )
        
    except Exception as e:
        trace_id = str(uuid.uuid4())
        logger.error(
            f"Conversation processing failed trace_id={trace_id}: {e}",
            exc_info=True,
        )
        if request.eval_mode:
            return JSONResponse(
                status_code=500,
                content={
                    "error_code": "CONVERSATION_FAILED",
                    "trace_id": trace_id,
                    "error_type": e.__class__.__name__,
                    "message": "conversation_failed",
                },
                headers={"X-Trace-Id": trace_id},
            )
        return MessageResponse(
            reply="抱歉，处理消息时出现了问题。请稍后再试。",
            session_id=session_id,
            turn_id=str(uuid.uuid4()),
            emotion={"primary_emotion": "neutral", "valence": 0.0, "confidence": 0.5},
            affinity={"score": 0.5, "state": "acquaintance", "delta": 0.0},
            memories_used=[],
            tone_type="friendly",
            response_time_ms=0,
            memory_status="error",
            error_code="CONVERSATION_FAILED",
            trace_id=trace_id,
            error_type=e.__class__.__name__,
        )


@router.post("/session", response_model=SessionResponse)
async def create_session(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建新会话"""
    user_id = normalize_uuid(current_user["user_id"])
    session_id = str(uuid.uuid4())
    db.add(Session(id=uuid.UUID(session_id), user_id=uuid.UUID(user_id)))
    await db.commit()
    
    return SessionResponse(
        session_id=session_id,
        user_id=user_id,
        started_at=datetime.now(),
        turn_count=0
    )


@router.delete("/session/{session_id}")
async def end_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """结束会话"""
    user_id = normalize_uuid(current_user["user_id"])
    session_uuid = uuid.UUID(normalize_uuid(session_id))
    session_row = (
        await db.execute(
            select(Session).where(Session.id == session_uuid, Session.user_id == uuid.UUID(user_id))
        )
    ).scalar_one_or_none()
    if session_row:
        session_row.ended_at = datetime.utcnow()
        await db.commit()
    return {
        "session_id": session_id,
        "status": "ended",
        "summary": "会话已结束"
    }


@router.get("/history")
async def get_history(
    limit: int = 50,
    session_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取对话历史"""
    user_id = normalize_uuid(current_user["user_id"])
    user_uuid = uuid.UUID(user_id)

    stmt = select(ConversationTurn).where(ConversationTurn.user_id == user_uuid)
    if session_id:
        stmt = stmt.where(ConversationTurn.session_id == uuid.UUID(normalize_uuid(session_id)))
    stmt = stmt.order_by(ConversationTurn.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    rows.reverse()
    return {
        "user_id": user_id,
        "turns": [
            {
                "id": str(t.id),
                "session_id": str(t.session_id),
                "role": t.role,
                "content": t.content,
                "created_at": t.created_at.isoformat(),
            }
            for t in rows
        ],
        "total": len(rows),
    }
