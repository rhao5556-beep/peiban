"""SSE 流式端点"""
import asyncio
import json
import logging
from typing import AsyncGenerator, Optional, Literal, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.security import get_current_user
from app.core.database import get_db, AsyncSessionLocal, get_redis_client, get_neo4j_driver, get_milvus_collection
from app.core.ids import normalize_uuid
from app.services.conversation_service import ConversationService
from app.services.affinity_service import AffinityService
from app.services.retrieval_service import RetrievalService
from app.services.graph_service import GraphService
from app.services.outbox_service import TransactionManager, IdempotencyChecker

router = APIRouter()
logger = logging.getLogger(__name__)


class StreamMessageRequest(BaseModel):
    """流式消息请求"""
    message: str
    session_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    mode: Literal["graph_only", "hybrid"] = "hybrid"
    eval_mode: bool = False
    eval_task_type: Optional[str] = None
    eval_evidence_ids: Optional[List[int]] = None
    observed_at: Optional[datetime] = None
    memorize_only: bool = False


class ConversationDelta(BaseModel):
    """流式输出的增量数据"""
    type: str  # 'text', 'memory_pending', 'memory_committed', 'done', 'error'
    content: Optional[str] = None
    memory_id: Optional[str] = None
    metadata: Optional[dict] = None


async def generate_stream_response(
    user_id: str,
    message: str,
    session_id: str,
    idempotency_key: str,
    mode: str = "hybrid",
    eval_mode: bool = False,
    eval_task_type: Optional[str] = None,
    eval_evidence_ids: Optional[List[int]] = None,
    observed_at: Optional[datetime] = None,
    memorize_only: bool = False
) -> AsyncGenerator[str, None]:
    """
    生成流式响应 - 使用真实的 ConversationService 和数据库
    
    Yields:
        SSE 格式的 JSON 数据
    """
    logger.info(f"=== SSE Stream Start: user={user_id}, message={message[:50]}")

    yield json.dumps({
        "type": "start",
        "session_id": session_id
    })
    
    # 创建独立的数据库 session（因为 SSE 是长连接）
    db_session = None
    try:
        async with AsyncSessionLocal() as session:
            try:
                await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=1.0)
                db_session = session
            except Exception:
                db_session = None

            # 1. 准备依赖服务
            redis_client = get_redis_client()
            neo4j_driver = get_neo4j_driver()
            
            affinity_service = AffinityService()
            graph_service = GraphService(neo4j_driver=neo4j_driver)
            transaction_manager = TransactionManager(db_session=db_session)
            idempotency_checker = IdempotencyChecker(redis_client=redis_client)
            milvus_collection = None
            try:
                milvus_collection = get_milvus_collection()
            except Exception:
                milvus_collection = None
            retrieval_service = RetrievalService(
                 milvus_client=milvus_collection,
                 graph_service=graph_service, 
                 db_session=db_session
            )
            # 注意: RetrievalService 目前代码里 __init__ 需要 milvus_client
            # 我们需要在 RetrievalService 里最好能自动获取 connection，
            # 或者在这里 import get_milvus_collection 传入?
            # 查看 retrieval_service.py 发现 __init__ 接收 milvus_client.
            # 但我们为了快速修复，先让 RetrievalService 尝试自己获取或者传入 None (它会有 warning 降级)
            # 更好的做法是在 factory 里处理。
            
            # 初始化 ConversationService
            logger.info("Initializing ConversationService with injected dependencies...")
            conversation_service = ConversationService(
                affinity_service=affinity_service,
                retrieval_service=retrieval_service,
                graph_service=graph_service,
                transaction_manager=transaction_manager,
                idempotency_checker=idempotency_checker
            )
            logger.info("ConversationService initialized successfully")
            
            logger.info("Starting process_message_stream...")
            async for delta in conversation_service.process_message_stream(
                user_id=user_id,
                session_id=session_id,
                message=message,
                idempotency_key=idempotency_key,
                mode=mode or "hybrid",
                eval_mode=eval_mode,
                eval_task_type=eval_task_type,
                eval_evidence_ids=eval_evidence_ids,
                observed_at=observed_at,
                memorize_only=bool(memorize_only)
            ):
                # 将 ConversationDelta 转换为 JSON
                logger.debug(f"Delta: type={delta.type}, content={delta.content[:20] if delta.content else None}")
                yield json.dumps({
                    "type": delta.type,
                    "content": delta.content,
                    "memory_id": delta.memory_id,
                    "metadata": delta.metadata
                })
            
            logger.info("=== SSE Stream Complete")
    except Exception as e:
        logger.error(f"=== SSE Stream Error: {e}", exc_info=True)
        yield json.dumps({
            "type": "error",
            "content": str(e)
        })
        yield json.dumps({"type": "done"})


@router.post("/message")
async def stream_message(
    request: StreamMessageRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    流式发送消息（SSE 模式）
    
    返回 Server-Sent Events 流：
    - type: text - 文本片段
    - type: memory_pending - 记忆写入中
    - type: memory_committed - 记忆已提交
    - type: done - 完成
    - type: error - 错误
    """
    try:
        user_id = normalize_uuid(current_user["user_id"])
        session_id = normalize_uuid(request.session_id) if request.session_id else str(uuid.uuid4())
        idempotency_key = request.idempotency_key or str(uuid.uuid4())
        
        return EventSourceResponse(
            generate_stream_response(
                user_id,
                request.message,
                session_id,
                idempotency_key,
                mode=request.mode,
                eval_mode=bool(request.eval_mode),
                eval_task_type=request.eval_task_type,
                eval_evidence_ids=request.eval_evidence_ids,
                observed_at=request.observed_at,
                memorize_only=bool(request.memorize_only)
            ),
            media_type="text/event-stream"
        )
    except Exception as e:
        async def error_generator():
            yield json.dumps({"type": "error", "content": str(e)})
        return EventSourceResponse(error_generator(), media_type="text/event-stream")


@router.get("/test")
async def test_sse():
    """测试 SSE 连接"""
    async def event_generator():
        for i in range(5):
            yield json.dumps({"count": i, "message": f"Test event {i}"})
            await asyncio.sleep(1)
        yield json.dumps({"type": "done"})
    
    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream"
    )
