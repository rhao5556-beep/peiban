"""SSE 流式端点"""
import asyncio
import json
import logging
from typing import AsyncGenerator, Optional
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.security import get_current_user
from app.core.database import get_db, AsyncSessionLocal, get_redis_client, get_neo4j_driver
from app.services.conversation_service import ConversationService
from app.services.affinity_service import AffinityService
from app.services.retrieval_service import RetrievalService
from app.services.graph_service import GraphService
from app.services.outbox_service import TransactionManager, IdempotencyChecker
from app.services.meme_injection_service import MemeInjectionService

router = APIRouter()
logger = logging.getLogger(__name__)


class StreamMessageRequest(BaseModel):
    """流式消息请求"""
    message: str
    session_id: Optional[str] = None
    idempotency_key: Optional[str] = None


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
    idempotency_key: str
) -> AsyncGenerator[str, None]:
    """
    生成流式响应 - 使用真实的 ConversationService 和数据库
    
    Yields:
        SSE 格式的 JSON 数据
    """
    logger.info(f"=== SSE Stream Start: user={user_id}, message={message[:50]}")
    
    # 创建独立的数据库 session（因为 SSE 是长连接）
    async with AsyncSessionLocal() as db_session:
        try:
            try:
                await db_session.execute(
                    text("""
                        INSERT INTO sessions (id, user_id, started_at, turn_count)
                        VALUES (:id, :user_id, NOW(), 0)
                        ON CONFLICT (id) DO NOTHING
                    """),
                    {"id": session_id, "user_id": user_id},
                )
                await db_session.commit()
            except Exception:
                await db_session.rollback()

            # 1. 准备依赖服务
            redis_client = get_redis_client()
            neo4j_driver = get_neo4j_driver()
            
            affinity_service = AffinityService(db_session=db_session)
            graph_service = GraphService(neo4j_driver=neo4j_driver)
            transaction_manager = TransactionManager(db_session=db_session)
            idempotency_checker = IdempotencyChecker(redis_client=redis_client)
            # RetrievalService 需要 Milvus, GraphService, DB Session
            # 这里简化处理，假设 Milvus Client 在 RetrievalService 内部获取或者单例
            retrieval_service = RetrievalService(
                 milvus_client=None, # RetrievalService 内部如果有单例处理最好，或者这里需要获取
                 graph_service=graph_service, 
                 db_session=db_session
            )
            # 注意: RetrievalService 目前代码里 __init__ 需要 milvus_client
            # 我们需要在 RetrievalService 里最好能自动获取 connection，
            # 或者在这里 import get_milvus_collection 传入?
            # 查看 retrieval_service.py 发现 __init__ 接收 milvus_client.
            # 但我们为了快速修复，先让 RetrievalService 尝试自己获取或者传入 None (它会有 warning 降级)
            # 更好的做法是在 factory 里处理。
            
            # 补充：为了能让 Milvus 工作，我们需要传入 milvus connection
            from pymilvus import connections
            try:
                 # 尝试获取 default alias
                 # 注意：pymilvus 的 connection 是全局的，Collection() 使用 alias
                 # RetrievalService 里的 _vector_search 使用 self.milvus.search
                 # 这意味着 self.milvus 必须是一个 Collection 对象或者 connection 封装？
                 # 看 retrieval_service.py:170: results = self.milvus.search(...)
                 # 这说明 self.milvus 是一个 Collection 对象。
                 from app.core.database import get_milvus_collection, milvus_connected
                 milvus_collection = get_milvus_collection() if milvus_connected else None
                 retrieval_service.milvus = milvus_collection
            except Exception as e:
                 logger.warning(f"Failed to get milvus collection: {e}")

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
            
            yield json.dumps({
                "type": "start",
                "session_id": session_id
            })

            logger.info("Starting process_message_stream...")
            emotion_valence = None
            async for delta in conversation_service.process_message_stream(
                user_id=user_id,
                session_id=session_id,
                message=message,
                idempotency_key=idempotency_key
            ):
                if delta.type == "metadata" and delta.metadata:
                    emo = delta.metadata.get("emotion")
                    if isinstance(emo, dict) and "valence" in emo:
                        try:
                            emotion_valence = float(emo.get("valence"))
                        except Exception:
                            pass
                # 将 ConversationDelta 转换为 JSON
                logger.debug(f"Delta: type={delta.type}, content={delta.content[:20] if delta.content else None}")
                yield json.dumps({
                    "type": delta.type,
                    "content": delta.content,
                    "memory_id": delta.memory_id,
                    "metadata": delta.metadata
                })

            try:
                injector = MemeInjectionService(db_session=db_session)
                meme_payload = await injector.maybe_select_and_record(
                    user_id=user_id,
                    session_id=session_id,
                    emotion_valence=emotion_valence,
                )
                if meme_payload:
                    yield json.dumps({
                        "type": "meme",
                        "metadata": meme_payload
                    })
            except Exception as e:
                logger.warning(f"Meme injection skipped: {e}")
            
            logger.info("=== SSE Stream Complete")
            
        except Exception as e:
            logger.error(f"=== SSE Stream Error: {e}", exc_info=True)
            yield json.dumps({
                "type": "error",
                "content": str(e)
            })


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
    user_id = current_user["user_id"]
    session_id = request.session_id or str(uuid.uuid4())
    idempotency_key = request.idempotency_key or str(uuid.uuid4())
    
    return EventSourceResponse(
        generate_stream_response(user_id, request.message, session_id, idempotency_key),
        media_type="text/event-stream"
    )


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
