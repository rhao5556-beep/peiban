"""上下文记忆服务 - 管理跨会话的主题连续性"""
import logging
import math
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import openai

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.retrieval_service import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass
class SessionSummary:
    """会话摘要"""
    session_id: str
    user_id: str
    main_topics: List[str]
    key_entities: List[str]
    unfinished_threads: List[str] = field(default_factory=list)
    emotional_arc: str = "neutral"  # positive, negative, neutral, mixed
    summary_text: str = ""
    importance_score: float = 0.5
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "main_topics": self.main_topics,
            "key_entities": self.key_entities,
            "unfinished_threads": self.unfinished_threads,
            "emotional_arc": self.emotional_arc,
            "summary_text": self.summary_text,
            "importance_score": self.importance_score,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


@dataclass
class ConversationTurn:
    """对话轮次"""
    role: str  # user, assistant
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)



class ContextMemoryService:
    """
    上下文记忆服务 - 管理跨会话的主题连续性
    
    功能：
    - 从会话中提取摘要
    - 存储上下文到 PostgreSQL
    - 检索相关的历史上下文
    - LRU 淘汰旧上下文
    """
    
    MAX_ENTRIES_PER_USER = 100
    
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.llm_client = openai.AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE
        )
    
    async def extract_session_summary(
        self,
        session_id: str,
        user_id: str,
        conversation_turns: List[ConversationTurn]
    ) -> SessionSummary:
        """
        从会话中提取摘要
        
        使用 LLM 分析对话内容，提取：
        - 主要话题
        - 关键实体
        - 未完成的话题线索
        - 情感走向
        """
        if len(conversation_turns) < 3:
            # 对话太短，返回简单摘要
            return SessionSummary(
                session_id=session_id,
                user_id=user_id,
                main_topics=["简短对话"],
                key_entities=[],
                summary_text="对话内容较少",
                importance_score=0.3
            )
        
        # 构建对话文本
        conversation_text = "\n".join([
            f"{'用户' if t.role == 'user' else 'AI'}: {t.content}"
            for t in conversation_turns[-20:]  # 最多取最近 20 轮
        ])
        
        # 使用 LLM 提取摘要
        try:
            response = await self.llm_client.chat.completions.create(
                model="Qwen/Qwen2.5-7B-Instruct",  # 使用较小模型节省成本
                messages=[
                    {
                        "role": "system",
                        "content": """你是一个对话分析助手。请分析以下对话，提取：
1. main_topics: 主要讨论的话题（列表，最多5个）
2. key_entities: 提到的关键人物、地点、事物（列表）
3. unfinished_threads: 未完成或可以继续的话题（列表）
4. emotional_arc: 对话的情感走向（positive/negative/neutral/mixed）
5. summary: 一句话总结

请以 JSON 格式返回，例如：
{"main_topics": ["工作", "旅行"], "key_entities": ["张三", "北京"], "unfinished_threads": ["下周的计划"], "emotional_arc": "positive", "summary": "用户分享了工作和旅行计划"}"""
                    },
                    {"role": "user", "content": conversation_text}
                ],
                max_tokens=500,
                temperature=0.3
            )
            
            # 解析 LLM 响应
            import json
            result_text = response.choices[0].message.content
            
            # 尝试提取 JSON
            try:
                # 查找 JSON 部分
                start = result_text.find('{')
                end = result_text.rfind('}') + 1
                if start >= 0 and end > start:
                    result = json.loads(result_text[start:end])
                else:
                    raise ValueError("No JSON found")
            except json.JSONDecodeError:
                # 如果解析失败，使用默认值
                result = {
                    "main_topics": ["对话"],
                    "key_entities": [],
                    "unfinished_threads": [],
                    "emotional_arc": "neutral",
                    "summary": "对话摘要提取失败"
                }
            
            # 计算重要性分数
            importance = self._calculate_importance(
                len(conversation_turns),
                len(result.get("key_entities", [])),
                result.get("emotional_arc", "neutral")
            )
            
            return SessionSummary(
                session_id=session_id,
                user_id=user_id,
                main_topics=result.get("main_topics", [])[:5],
                key_entities=result.get("key_entities", [])[:10],
                unfinished_threads=result.get("unfinished_threads", [])[:3],
                emotional_arc=result.get("emotional_arc", "neutral"),
                summary_text=result.get("summary", ""),
                importance_score=importance
            )
            
        except Exception as e:
            logger.error(f"Failed to extract session summary: {e}")
            return SessionSummary(
                session_id=session_id,
                user_id=user_id,
                main_topics=["对话"],
                key_entities=[],
                summary_text="摘要提取失败",
                importance_score=0.3
            )
    
    def _calculate_importance(
        self,
        turn_count: int,
        entity_count: int,
        emotional_arc: str
    ) -> float:
        """计算会话重要性分数"""
        base_score = 0.5
        
        # 对话长度加成
        if turn_count >= 10:
            base_score += 0.2
        elif turn_count >= 5:
            base_score += 0.1
        
        # 实体数量加成
        if entity_count >= 5:
            base_score += 0.15
        elif entity_count >= 2:
            base_score += 0.1
        
        # 情感强度加成
        if emotional_arc in ["positive", "negative"]:
            base_score += 0.1
        elif emotional_arc == "mixed":
            base_score += 0.05
        
        return min(1.0, base_score)


    async def store_context(
        self,
        user_id: str,
        session_id: str,
        summary: SessionSummary
    ) -> str:
        """
        存储会话上下文到 PostgreSQL
        
        Returns:
            context_id: 存储的上下文 ID
        """
        # 生成 Embedding
        embedding = await self.embedding_service.encode(summary.summary_text)
        
        async with AsyncSessionLocal() as db:
            try:
                # 插入上下文记忆
                result = await db.execute(
                    text("""
                        INSERT INTO context_memories 
                        (user_id, session_id, main_topics, key_entities, 
                         unfinished_threads, emotional_arc, summary_text, 
                         embedding, importance_score, created_at, last_accessed)
                        VALUES (:user_id, :session_id, :main_topics, :key_entities,
                                :unfinished_threads, :emotional_arc, :summary_text,
                                :embedding, :importance_score, NOW(), NOW())
                        RETURNING id
                    """),
                    {
                        "user_id": user_id,
                        "session_id": session_id,
                        "main_topics": summary.main_topics,
                        "key_entities": summary.key_entities,
                        "unfinished_threads": summary.unfinished_threads,
                        "emotional_arc": summary.emotional_arc,
                        "summary_text": summary.summary_text,
                        "embedding": str(embedding),  # pgvector 格式
                        "importance_score": summary.importance_score
                    }
                )
                
                row = result.fetchone()
                context_id = str(row[0]) if row else None
                
                await db.commit()
                
                # 检查是否需要淘汰
                await self.evict_old_contexts(user_id)
                
                logger.info(f"Stored context {context_id} for session {session_id[:8]}")
                return context_id
                
            except Exception as e:
                await db.rollback()
                logger.error(f"Failed to store context: {e}")
                raise
    
    async def retrieve_relevant_context(
        self,
        user_id: str,
        query: str,
        session_limit: int = 3
    ) -> List[SessionSummary]:
        """
        检索相关的历史上下文
        
        使用语义搜索找到与当前查询最相关的历史会话
        """
        # 生成查询 Embedding
        query_embedding = await self.embedding_service.encode(query)
        
        async with AsyncSessionLocal() as db:
            try:
                # 语义搜索 + 时间排序
                result = await db.execute(
                    text("""
                        SELECT id, session_id, main_topics, key_entities,
                               unfinished_threads, emotional_arc, summary_text,
                               importance_score, created_at,
                               1 - (embedding <=> :query_embedding::vector) as similarity
                        FROM context_memories
                        WHERE user_id = :user_id
                        ORDER BY similarity DESC, created_at DESC
                        LIMIT :limit
                    """),
                    {
                        "user_id": user_id,
                        "query_embedding": str(query_embedding),
                        "limit": session_limit
                    }
                )
                
                rows = result.fetchall()
                
                # 更新访问时间
                if rows:
                    context_ids = [str(row[0]) for row in rows]
                    await db.execute(
                        text("""
                            UPDATE context_memories 
                            SET last_accessed = NOW(), access_count = access_count + 1
                            WHERE id = ANY(:ids::uuid[])
                        """),
                        {"ids": context_ids}
                    )
                    await db.commit()
                
                # 转换为 SessionSummary
                summaries = []
                for row in rows:
                    summaries.append(SessionSummary(
                        session_id=str(row[1]),
                        user_id=user_id,
                        main_topics=row[2] or [],
                        key_entities=row[3] or [],
                        unfinished_threads=row[4] or [],
                        emotional_arc=row[5] or "neutral",
                        summary_text=row[6] or "",
                        importance_score=row[7] or 0.5,
                        created_at=row[8]
                    ))
                
                logger.info(f"Retrieved {len(summaries)} context summaries for user {user_id[:8]}")
                return summaries
                
            except Exception as e:
                logger.error(f"Failed to retrieve context: {e}")
                return []
    
    async def evict_old_contexts(
        self,
        user_id: str,
        max_entries: int = None
    ) -> int:
        """
        LRU 淘汰旧上下文
        
        保留 importance_score * recency_weight 最高的条目
        
        Returns:
            deleted_count: 删除的条目数
        """
        max_entries = max_entries or self.MAX_ENTRIES_PER_USER
        
        async with AsyncSessionLocal() as db:
            try:
                # 调用数据库函数执行淘汰
                result = await db.execute(
                    text("SELECT evict_old_context_memories(:user_id, :max_entries)"),
                    {"user_id": user_id, "max_entries": max_entries}
                )
                
                row = result.fetchone()
                deleted_count = row[0] if row else 0
                
                await db.commit()
                
                if deleted_count > 0:
                    logger.info(f"Evicted {deleted_count} old contexts for user {user_id[:8]}")
                
                return deleted_count
                
            except Exception as e:
                logger.warning(f"Failed to evict old contexts: {e}")
                return 0
    
    async def get_recent_contexts(
        self,
        user_id: str,
        limit: int = 5
    ) -> List[SessionSummary]:
        """获取最近的上下文（按时间排序）"""
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(
                    text("""
                        SELECT session_id, main_topics, key_entities,
                               unfinished_threads, emotional_arc, summary_text,
                               importance_score, created_at
                        FROM context_memories
                        WHERE user_id = :user_id
                        ORDER BY created_at DESC
                        LIMIT :limit
                    """),
                    {"user_id": user_id, "limit": limit}
                )
                
                rows = result.fetchall()
                
                return [
                    SessionSummary(
                        session_id=str(row[0]),
                        user_id=user_id,
                        main_topics=row[1] or [],
                        key_entities=row[2] or [],
                        unfinished_threads=row[3] or [],
                        emotional_arc=row[4] or "neutral",
                        summary_text=row[5] or "",
                        importance_score=row[6] or 0.5,
                        created_at=row[7]
                    )
                    for row in rows
                ]
                
            except Exception as e:
                logger.error(f"Failed to get recent contexts: {e}")
                return []
    
    async def get_context_count(self, user_id: str) -> int:
        """获取用户的上下文数量"""
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(
                    text("SELECT COUNT(*) FROM context_memories WHERE user_id = :user_id"),
                    {"user_id": user_id}
                )
                row = result.fetchone()
                return row[0] if row else 0
            except Exception as e:
                logger.error(f"Failed to get context count: {e}")
                return 0

