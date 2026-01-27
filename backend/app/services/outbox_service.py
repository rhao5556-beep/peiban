"""Outbox 服务 - 事务管理器"""
import asyncio
import uuid
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class OutboxEvent:
    """Outbox 事件"""
    event_id: str
    memory_id: str
    payload: Dict[str, Any]
    status: str  # pending, processing, done, failed
    retry_count: int
    idempotency_key: Optional[str]
    created_at: datetime
    processed_at: Optional[datetime]
    error_message: Optional[str]


class TransactionManager:
    """
    事务管理器 - 确保 Memory + Outbox 本地事务原子性
    
    Property 12: Outbox 本地事务原子性
    
    对于任意记忆写入操作，memories 表的 Insert 和 outbox_events 表的 Insert
    必须在同一个本地数据库事务中提交。
    """
    
    def __init__(self, db_session: AsyncSession = None):
        self.db = db_session
    
    _memories_has_observed_at: Optional[bool] = None
    
    async def create_memory_with_outbox(
        self,
        user_id: str,
        content: str,
        embedding: List[float],
        valence: float,
        conversation_id: str,
        idempotency_key: str,
        observed_at: Optional[datetime] = None,
        entities: List[Dict] = None,
        edges: List[Dict] = None
    ) -> Tuple[str, str]:
        """
        在同一个事务中创建 Memory 和 Outbox 事件
        
        Property 12: Outbox 本地事务原子性
        
        Args:
            user_id: 用户 ID
            content: 记忆内容
            embedding: 向量嵌入
            valence: 情感正负向
            conversation_id: 对话 ID
            idempotency_key: 幂等键
            entities: 抽取的实体
            edges: 抽取的关系
            
        Returns:
            (memory_id, event_id): 创建的记录 ID
            
        Raises:
            Exception: 事务失败时回滚
        """
        memory_id = str(uuid.uuid4())
        event_id = str(uuid.uuid4())
        
        # 构建 Outbox payload
        payload = {
            "memory_id": memory_id,
            "user_id": user_id,
            "content": content,
            "embedding": embedding,
            "valence": valence,
            "conversation_id": conversation_id,
            "observed_at": observed_at.isoformat() if observed_at else None,
            "entities": entities or [],
            "edges": edges or []
        }
        
        if not self.db:
            logger.warning("No database session, returning mock IDs")
            return memory_id, event_id
        
        try:
            # 在同一个事务中执行两个 INSERT
            # 1. 写入 pending 状态的 memory
            # 将 embedding list 转换为 pgvector 格式的字符串
            embedding_str = str(embedding) if embedding else None
            has_observed_at = self.__class__._memories_has_observed_at
            if has_observed_at is None:
                has_observed_at = False
                try:
                    r = await self.db.execute(
                        text("""
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = 'memories' AND column_name = 'observed_at'
                            LIMIT 1
                        """)
                    )
                    has_observed_at = r.first() is not None
                except Exception:
                    has_observed_at = False
                self.__class__._memories_has_observed_at = has_observed_at
            
            if has_observed_at:
                await self.db.execute(
                    text("""
                        INSERT INTO memories (id, user_id, content, embedding, valence, status, conversation_id, created_at, observed_at)
                        VALUES (:id, :user_id, :content, :embedding, :valence, 'pending', :conversation_id, NOW(), COALESCE(:observed_at, NOW()))
                    """),
                    {
                        "id": memory_id,
                        "user_id": user_id,
                        "content": content,
                        "embedding": embedding_str,
                        "valence": valence,
                        "conversation_id": conversation_id,
                        "observed_at": observed_at
                    }
                )
            else:
                await self.db.execute(
                    text("""
                        INSERT INTO memories (id, user_id, content, embedding, valence, status, conversation_id, created_at)
                        VALUES (:id, :user_id, :content, :embedding, :valence, 'pending', :conversation_id, NOW())
                    """),
                    {
                        "id": memory_id,
                        "user_id": user_id,
                        "content": content,
                        "embedding": embedding_str,
                        "valence": valence,
                        "conversation_id": conversation_id
                    }
                )
            
            # 2. 写入 outbox 事件
            await self.db.execute(
                text("""
                    INSERT INTO outbox_events (id, event_id, memory_id, payload, status, idempotency_key, created_at)
                    VALUES (:id, :event_id, :memory_id, :payload, 'pending', :idempotency_key, NOW())
                """),
                {
                    "id": str(uuid.uuid4()),
                    "event_id": event_id,
                    "memory_id": memory_id,
                    "payload": json.dumps(payload),
                    "idempotency_key": idempotency_key
                }
            )
            
            # 提交事务
            await self.db.commit()
            logger.info(f"Created memory {memory_id} with outbox event {event_id}")
            
            return memory_id, event_id
            
        except Exception as e:
            # 回滚事务
            await self.db.rollback()
            logger.error(f"Transaction failed, rolled back: {e}")
            raise
    
    async def mark_event_processing(self, event_id: str) -> bool:
        """标记事件为处理中（原子操作，防止重复消费）"""
        if not self.db:
            return True
        
        result = await self.db.execute(
            text("""
                UPDATE outbox_events 
                SET status = 'processing'
                WHERE event_id = :event_id AND status = 'pending'
                RETURNING id
            """),
            {"event_id": event_id}
        )
        await self.db.commit()
        return result.rowcount > 0
    
    async def mark_event_done(self, event_id: str) -> bool:
        """标记事件为完成"""
        if not self.db:
            return True
        
        await self.db.execute(
            text("""
                UPDATE outbox_events 
                SET status = 'done', processed_at = NOW()
                WHERE event_id = :event_id
            """),
            {"event_id": event_id}
        )
        await self.db.commit()
        return True
    
    async def mark_event_failed(self, event_id: str, error_message: str) -> bool:
        """标记事件为失败"""
        if not self.db:
            return True
        
        await self.db.execute(
            text("""
                UPDATE outbox_events 
                SET status = 'failed', error_message = :error_message
                WHERE event_id = :event_id
            """),
            {"event_id": event_id, "error_message": error_message}
        )
        await self.db.commit()
        return True
    
    async def increment_retry(self, event_id: str) -> int:
        """增加重试次数"""
        if not self.db:
            return 0
        
        result = await self.db.execute(
            text("""
                UPDATE outbox_events 
                SET retry_count = retry_count + 1, status = 'pending'
                WHERE event_id = :event_id
                RETURNING retry_count
            """),
            {"event_id": event_id}
        )
        await self.db.commit()
        row = result.fetchone()
        return row[0] if row else 0
    
    async def commit_memory(self, memory_id: str) -> bool:
        """
        提交记忆状态
        
        约束: 严禁在 Worker 处理成功前 commit memory status 为 'committed'
        """
        if not self.db:
            return True
        
        await self.db.execute(
            text("""
                UPDATE memories 
                SET status = 'committed', committed_at = NOW()
                WHERE id = :id AND status = 'pending'
            """),
            {"id": memory_id}
        )
        await self.db.commit()
        return True
    
    async def get_pending_events(self, limit: int = 100) -> List[OutboxEvent]:
        """获取待处理的事件"""
        if not self.db:
            return []
        
        result = await self.db.execute(
            text("""
                SELECT event_id, memory_id, payload, status, retry_count, 
                       idempotency_key, created_at, processed_at, error_message
                FROM outbox_events 
                WHERE status = 'pending'
                ORDER BY created_at
                LIMIT :limit
            """),
            {"limit": limit}
        )
        
        events = []
        for row in result.fetchall():
            events.append(OutboxEvent(
                event_id=row[0],
                memory_id=row[1],
                payload=json.loads(row[2]) if isinstance(row[2], str) else row[2],
                status=row[3],
                retry_count=row[4],
                idempotency_key=row[5],
                created_at=row[6],
                processed_at=row[7],
                error_message=row[8]
            ))
        return events
    
    async def get_failed_events(self, max_retries: int = 5) -> List[OutboxEvent]:
        """获取失败但未超过重试次数的事件"""
        if not self.db:
            return []
        
        result = await self.db.execute(
            text("""
                SELECT event_id, memory_id, payload, status, retry_count,
                       idempotency_key, created_at, processed_at, error_message
                FROM outbox_events 
                WHERE status = 'failed' AND retry_count < :max_retries
                ORDER BY created_at
                LIMIT 50
            """),
            {"max_retries": max_retries}
        )
        
        events = []
        for row in result.fetchall():
            events.append(OutboxEvent(
                event_id=row[0],
                memory_id=row[1],
                payload=json.loads(row[2]) if isinstance(row[2], str) else row[2],
                status=row[3],
                retry_count=row[4],
                idempotency_key=row[5],
                created_at=row[6],
                processed_at=row[7],
                error_message=row[8]
            ))
        return events
    
    async def move_to_dlq(self, event_id: str, error_message: str) -> bool:
        """将事件移入死信队列"""
        if not self.db:
            return True
        
        await self.db.execute(
            text("""
                UPDATE outbox_events 
                SET status = 'dlq', error_message = :error_message
                WHERE event_id = :event_id
            """),
            {"event_id": event_id, "error_message": error_message}
        )
        await self.db.commit()
        logger.warning(f"Event {event_id} moved to DLQ: {error_message}")
        return True
    
    async def check_idempotency(self, idempotency_key: str) -> Optional[Dict]:
        """
        检查幂等键是否已存在
        
        Property 11: 并发写幂等性
        
        Returns:
            已存在的响应数据，或 None
        """
        if not self.db:
            return None
        
        result = await self.db.execute(
            text("""
                SELECT response FROM idempotency_keys 
                WHERE key = :key AND expires_at > NOW()
            """),
            {"key": idempotency_key}
        )
        row = result.fetchone()
        if row and row[0]:
            return json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return None
    
    async def save_idempotency_key(
        self,
        key: str,
        user_id: str,
        response: Dict
    ) -> bool:
        """保存幂等键（24小时有效期）"""
        if not self.db:
            return True
        
        await self.db.execute(
            text("""
                INSERT INTO idempotency_keys (key, user_id, response, created_at, expires_at)
                VALUES (:key, :user_id, :response, NOW(), NOW() + INTERVAL '24 hours')
                ON CONFLICT (key) DO NOTHING
            """),
            {
                "key": key,
                "user_id": user_id,
                "response": json.dumps(response)
            }
        )
        await self.db.commit()
        return True


class IdempotencyChecker:
    """
    幂等性检查器 - 使用 Redis + Lua 脚本
    
    Property 11: 并发写幂等性
    """
    
    # Redis Lua 脚本：原子性检查并设置
    CHECK_AND_SET_SCRIPT = """
    local key = KEYS[1]
    local value = ARGV[1]
    local ttl = ARGV[2]
    
    local existing = redis.call('GET', key)
    if existing then
        return existing  -- 返回已存在的值
    end
    
    redis.call('SET', key, value, 'EX', ttl)
    return nil  -- 新创建，返回 nil
    """

    _shared_script_sha: Optional[str] = None
    _shared_script_lock = asyncio.Lock()
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.ttl = 86400  # 24 hours
        self._script_sha = self.__class__._shared_script_sha
    
    async def _ensure_script(self):
        """确保 Lua 脚本已加载"""
        if not self.redis:
            return
        if self.__class__._shared_script_sha is not None:
            self._script_sha = self.__class__._shared_script_sha
            return
        async with self.__class__._shared_script_lock:
            if self.__class__._shared_script_sha is None:
                self.__class__._shared_script_sha = await asyncio.wait_for(
                    self.redis.script_load(self.CHECK_AND_SET_SCRIPT),
                    timeout=2.0,
                )
            self._script_sha = self.__class__._shared_script_sha
    
    async def check_and_acquire(
        self, 
        idempotency_key: str, 
        user_id: str,
        memory_id: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        检查并获取幂等锁
        
        Returns:
            (is_new, existing_memory_id): 
            - (True, None): 首次请求，已获取锁
            - (False, memory_id): 重复请求，返回已存在的 memory_id
        """
        if not self.redis:
            return True, None
        
        key = f"idempotency:{idempotency_key}"
        value = json.dumps({
            "user_id": user_id,
            "memory_id": memory_id,
            "timestamp": datetime.now().isoformat()
        })
        
        try:
            await self._ensure_script()
            
            # 执行 Lua 脚本
            result = await asyncio.wait_for(
                self.redis.evalsha(self._script_sha, 1, key, value, self.ttl),
                timeout=2.0,
            )
            
            if result is None:
                return True, None  # 新请求
            else:
                # 解析已存在的值
                existing = json.loads(result)
                return False, existing.get("memory_id")
                
        except Exception as e:
            logger.error(f"Redis idempotency check failed: {e}")
            # Fallback: 允许请求继续（依赖数据库唯一约束）
            return True, None
    
    async def set_memory_id(self, idempotency_key: str, memory_id: str) -> bool:
        """设置幂等键对应的 memory_id（在事务成功后调用）"""
        if not self.redis:
            return True
        
        key = f"idempotency:{idempotency_key}"
        
        try:
            existing = await asyncio.wait_for(self.redis.get(key), timeout=2.0)
            if existing:
                data = json.loads(existing)
                data["memory_id"] = memory_id
                await asyncio.wait_for(self.redis.set(key, json.dumps(data), ex=self.ttl), timeout=2.0)
            return True
        except Exception as e:
            logger.error(f"Failed to set memory_id: {e}")
            return False
    
    async def release(self, idempotency_key: str) -> bool:
        """释放幂等锁（用于回滚场景）"""
        if not self.redis:
            return True
        
        key = f"idempotency:{idempotency_key}"
        try:
            await asyncio.wait_for(self.redis.delete(key), timeout=2.0)
            return True
        except Exception as e:
            logger.error(f"Failed to release idempotency key: {e}")
            return False
