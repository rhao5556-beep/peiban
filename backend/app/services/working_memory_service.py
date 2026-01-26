"""工作记忆服务 - 管理会话内的临时状态和指代消解"""
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict
import redis.asyncio as redis

from app.core.database import get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class EntityMention:
    """实体提及"""
    id: str
    name: str
    entity_type: str  # person, place, thing, event
    mention_text: str  # 原始提及文本
    position: int = 0  # 在消息中的位置
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "EntityMention":
        return cls(**data)


@dataclass
class ReferenceResolution:
    """指代消解结果"""
    reference_text: str  # "他", "那个人"
    resolved_entity: Optional[EntityMention]
    confidence: float
    alternatives: List[EntityMention] = field(default_factory=list)
    
    @property
    def is_resolved(self) -> bool:
        return self.resolved_entity is not None and self.confidence > 0.5


class WorkingMemoryService:
    """
    工作记忆服务 - 管理会话内的临时状态
    
    存储结构 (Redis):
    - working_memory:{session_id}:entities -> Sorted Set (score = timestamp)
    - working_memory:{session_id}:last_topic -> String
    - working_memory:{session_id}:reference_map -> Hash (reference -> entity_id)
    
    TTL: 30 分钟 (1800 秒)
    """
    
    # 常见指代词映射
    REFERENCE_PATTERNS = {
        # 人称代词
        "他": "person",
        "她": "person",
        "它": "thing",
        "他们": "person",
        "她们": "person",
        # 指示代词
        "那个人": "person",
        "这个人": "person",
        "那个地方": "place",
        "这个地方": "place",
        "那件事": "event",
        "这件事": "event",
        # 回指
        "刚才说的": None,  # 任意类型
        "之前提到的": None,
        "上面说的": None,
    }
    
    def __init__(self, redis_client: redis.Redis = None, ttl: int = 1800):
        """
        初始化工作记忆服务
        
        Args:
            redis_client: Redis 客户端
            ttl: 过期时间 (秒)，默认 30 分钟
        """
        self._redis = redis_client
        self.ttl = ttl
    
    @property
    def redis(self) -> redis.Redis:
        """获取 Redis 客户端 (延迟初始化)"""
        if self._redis is None:
            self._redis = get_redis_client()
        return self._redis
    
    def _key(self, session_id: str, suffix: str) -> str:
        """生成 Redis key"""
        return f"working_memory:{session_id}:{suffix}"
    
    async def store_entity(
        self,
        session_id: str,
        entity: EntityMention
    ) -> None:
        """
        存储实体到工作记忆
        
        Args:
            session_id: 会话 ID
            entity: 实体提及
        """
        if not self.redis:
            logger.warning("Redis client not available")
            return
        
        key = self._key(session_id, "entities")
        
        # 使用 Sorted Set，score 为时间戳
        await self.redis.zadd(
            key,
            {json.dumps(entity.to_dict()): entity.timestamp}
        )
        
        # 设置 TTL
        await self.redis.expire(key, self.ttl)
        
        # 更新引用映射 (用于快速查找)
        ref_key = self._key(session_id, "reference_map")
        await self.redis.hset(ref_key, entity.name.lower(), entity.id)
        await self.redis.expire(ref_key, self.ttl)
        
        logger.debug(f"Stored entity '{entity.name}' in session {session_id[:8]}")
    
    async def store_entities_batch(
        self,
        session_id: str,
        entities: List[EntityMention]
    ) -> None:
        """批量存储实体"""
        for entity in entities:
            await self.store_entity(session_id, entity)
    
    async def resolve_reference(
        self,
        session_id: str,
        reference: str,
        context: List[str] = None
    ) -> ReferenceResolution:
        """
        解析指代词到具体实体
        
        Args:
            session_id: 会话 ID
            reference: 指代词 (如 "他", "那个人")
            context: 上下文消息列表 (可选)
            
        Returns:
            ReferenceResolution: 解析结果
        """
        if not self.redis:
            return ReferenceResolution(
                reference_text=reference,
                resolved_entity=None,
                confidence=0.0
            )
        
        # 确定期望的实体类型
        expected_type = self.REFERENCE_PATTERNS.get(reference)
        
        # 获取最近的实体
        recent_entities = await self.get_recent_entities(
            session_id,
            entity_type=expected_type,
            limit=10
        )
        
        if not recent_entities:
            return ReferenceResolution(
                reference_text=reference,
                resolved_entity=None,
                confidence=0.0
            )
        
        # 简单策略：选择最近提及的匹配类型的实体
        # TODO: 可以增加更复杂的上下文分析
        best_match = recent_entities[0]
        alternatives = recent_entities[1:5] if len(recent_entities) > 1 else []
        
        # 计算置信度
        confidence = self._calculate_resolution_confidence(
            reference, best_match, recent_entities, context
        )
        
        return ReferenceResolution(
            reference_text=reference,
            resolved_entity=best_match,
            confidence=confidence,
            alternatives=alternatives
        )
    
    def _calculate_resolution_confidence(
        self,
        reference: str,
        best_match: EntityMention,
        all_candidates: List[EntityMention],
        context: List[str] = None
    ) -> float:
        """
        计算指代消解的置信度
        
        考虑因素：
        - 候选实体数量 (越少越确定)
        - 时间新鲜度 (越近越可能)
        - 类型匹配度
        """
        base_confidence = 0.5
        
        # 只有一个候选时，置信度高
        if len(all_candidates) == 1:
            base_confidence = 0.9
        elif len(all_candidates) == 2:
            base_confidence = 0.7
        
        # 检查类型匹配
        expected_type = self.REFERENCE_PATTERNS.get(reference)
        if expected_type and best_match.entity_type == expected_type:
            base_confidence += 0.1
        
        # 时间新鲜度加成 (最近 5 分钟内提及)
        age_seconds = datetime.now().timestamp() - best_match.timestamp
        if age_seconds < 300:  # 5 分钟
            base_confidence += 0.1
        
        return min(1.0, base_confidence)
    
    async def get_recent_entities(
        self,
        session_id: str,
        entity_type: Optional[str] = None,
        limit: int = 10
    ) -> List[EntityMention]:
        """
        获取最近提及的实体
        
        Args:
            session_id: 会话 ID
            entity_type: 实体类型过滤 (可选)
            limit: 返回数量限制
            
        Returns:
            List[EntityMention]: 按时间倒序排列的实体列表
        """
        if not self.redis:
            return []
        
        key = self._key(session_id, "entities")
        
        # 获取所有实体 (按时间戳倒序)
        raw_entities = await self.redis.zrevrange(key, 0, -1)
        
        entities = []
        for raw in raw_entities:
            try:
                data = json.loads(raw)
                entity = EntityMention.from_dict(data)
                
                # 类型过滤
                if entity_type is None or entity.entity_type == entity_type:
                    entities.append(entity)
                    
                if len(entities) >= limit:
                    break
                    
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse entity: {e}")
                continue
        
        return entities
    
    async def get_entity_by_name(
        self,
        session_id: str,
        name: str
    ) -> Optional[EntityMention]:
        """
        按名称获取实体
        
        Args:
            session_id: 会话 ID
            name: 实体名称
            
        Returns:
            EntityMention or None
        """
        entities = await self.get_recent_entities(session_id, limit=50)
        
        name_lower = name.lower()
        for entity in entities:
            if entity.name.lower() == name_lower:
                return entity
        
        return None
    
    async def set_last_topic(
        self,
        session_id: str,
        topic: str
    ) -> None:
        """设置最后讨论的话题"""
        if not self.redis:
            return
        
        key = self._key(session_id, "last_topic")
        await self.redis.set(key, topic, ex=self.ttl)
    
    async def get_last_topic(
        self,
        session_id: str
    ) -> Optional[str]:
        """获取最后讨论的话题"""
        if not self.redis:
            return None
        
        key = self._key(session_id, "last_topic")
        return await self.redis.get(key)
    
    async def clear_session(self, session_id: str) -> None:
        """
        清除会话的工作记忆
        
        Args:
            session_id: 会话 ID
        """
        if not self.redis:
            return
        
        keys = [
            self._key(session_id, "entities"),
            self._key(session_id, "last_topic"),
            self._key(session_id, "reference_map")
        ]
        
        for key in keys:
            await self.redis.delete(key)
        
        logger.info(f"Cleared working memory for session {session_id[:8]}")
    
    async def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """获取会话工作记忆统计"""
        if not self.redis:
            return {"entity_count": 0, "has_topic": False}
        
        entities_key = self._key(session_id, "entities")
        topic_key = self._key(session_id, "last_topic")
        
        entity_count = await self.redis.zcard(entities_key)
        has_topic = await self.redis.exists(topic_key)
        
        return {
            "entity_count": entity_count,
            "has_topic": bool(has_topic)
        }
    
    def is_reference(self, text: str) -> bool:
        """判断文本是否是指代词"""
        return text in self.REFERENCE_PATTERNS
    
    def extract_references(self, message: str) -> List[str]:
        """从消息中提取指代词"""
        references = []
        for ref in self.REFERENCE_PATTERNS.keys():
            if ref in message:
                references.append(ref)
        return references

