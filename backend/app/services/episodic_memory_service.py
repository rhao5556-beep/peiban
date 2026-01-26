"""情景记忆服务 - 管理事件时间线"""
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

from app.core.database import get_neo4j_driver

logger = logging.getLogger(__name__)


@dataclass
class Episode:
    """情景记忆"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    event_type: str = ""  # birthday, meeting, trip, achievement, conversation
    description: str = ""
    participants: List[str] = field(default_factory=list)  # 参与者实体 ID
    location: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration: Optional[timedelta] = None
    emotional_valence: float = 0.0  # -1 to 1
    source_memory_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            "description": self.description,
            "participants": self.participants,
            "location": self.location,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "duration_seconds": self.duration.total_seconds() if self.duration else None,
            "emotional_valence": self.emotional_valence,
            "source_memory_ids": self.source_memory_ids,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Episode":
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        
        duration = data.get("duration_seconds")
        if duration:
            duration = timedelta(seconds=duration)
        
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            user_id=data.get("user_id", ""),
            event_type=data.get("event_type", ""),
            description=data.get("description", ""),
            participants=data.get("participants", []),
            location=data.get("location"),
            timestamp=timestamp or datetime.utcnow(),
            duration=duration,
            emotional_valence=data.get("emotional_valence", 0.0),
            source_memory_ids=data.get("source_memory_ids", []),
            metadata=data.get("metadata", {})
        )



class EpisodicMemoryService:
    """
    情景记忆服务 - 管理事件时间线
    
    存储在 Neo4j 中，支持：
    - 时间范围查询
    - 事件类型过滤
    - 与实体的关联 (INVOLVES 关系)
    """
    
    # 支持的事件类型
    EVENT_TYPES = [
        "birthday", "meeting", "trip", "achievement", 
        "conversation", "milestone", "celebration", "work"
    ]
    
    def __init__(self, neo4j_driver=None):
        self._driver = neo4j_driver
    
    @property
    def driver(self):
        """获取 Neo4j 驱动 (延迟初始化)"""
        if self._driver is None:
            self._driver = get_neo4j_driver()
        return self._driver
    
    async def store_episode(
        self,
        user_id: str,
        episode: Episode
    ) -> str:
        """
        存储情景记忆到 Neo4j
        
        创建 Episode 节点和 INVOLVES 关系
        
        Returns:
            episode_id: 存储的情景 ID
        """
        if not self.driver:
            logger.warning("Neo4j driver not available")
            return episode.id
        
        episode.user_id = user_id
        
        try:
            async with self.driver.session() as session:
                # 创建 Episode 节点
                await session.run(
                    """
                    MERGE (e:Episode {id: $id, user_id: $user_id})
                    SET e.event_type = $event_type,
                        e.description = $description,
                        e.location = $location,
                        e.timestamp = datetime($timestamp),
                        e.emotional_valence = $emotional_valence,
                        e.created_at = datetime()
                    """,
                    {
                        "id": episode.id,
                        "user_id": user_id,
                        "event_type": episode.event_type,
                        "description": episode.description,
                        "location": episode.location,
                        "timestamp": episode.timestamp.isoformat(),
                        "emotional_valence": episode.emotional_valence
                    }
                )
                
                # 创建与参与者的 INVOLVES 关系
                if episode.participants:
                    for participant_id in episode.participants:
                        await session.run(
                            """
                            MATCH (e:Episode {id: $episode_id, user_id: $user_id})
                            MATCH (p {id: $participant_id, user_id: $user_id})
                            MERGE (e)-[:INVOLVES]->(p)
                            """,
                            {
                                "episode_id": episode.id,
                                "user_id": user_id,
                                "participant_id": participant_id
                            }
                        )
                
                # 创建与地点的 LOCATED_AT 关系
                if episode.location:
                    await session.run(
                        """
                        MATCH (e:Episode {id: $episode_id, user_id: $user_id})
                        MERGE (l:Place {name: $location, user_id: $user_id})
                        MERGE (e)-[:LOCATED_AT]->(l)
                        """,
                        {
                            "episode_id": episode.id,
                            "user_id": user_id,
                            "location": episode.location
                        }
                    )
                
                logger.info(f"Stored episode {episode.id[:8]} for user {user_id[:8]}")
                return episode.id
                
        except Exception as e:
            logger.error(f"Failed to store episode: {e}")
            return episode.id
    
    async def query_by_time_range(
        self,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 50
    ) -> List[Episode]:
        """
        按时间范围查询情景记忆
        
        返回时间范围内的所有事件，按时间排序
        """
        if not self.driver:
            return []
        
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    """
                    MATCH (e:Episode {user_id: $user_id})
                    WHERE e.timestamp >= datetime($start_time) 
                      AND e.timestamp <= datetime($end_time)
                    OPTIONAL MATCH (e)-[:INVOLVES]->(p)
                    OPTIONAL MATCH (e)-[:LOCATED_AT]->(l:Place)
                    RETURN e.id AS id, e.event_type AS event_type,
                           e.description AS description, e.timestamp AS timestamp,
                           e.emotional_valence AS emotional_valence,
                           l.name AS location,
                           collect(DISTINCT p.id) AS participants
                    ORDER BY e.timestamp ASC
                    LIMIT $limit
                    """,
                    {
                        "user_id": user_id,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "limit": limit
                    }
                )
                
                episodes = []
                async for record in result:
                    episodes.append(Episode(
                        id=record["id"],
                        user_id=user_id,
                        event_type=record["event_type"] or "",
                        description=record["description"] or "",
                        timestamp=record["timestamp"].to_native() if record["timestamp"] else datetime.utcnow(),
                        emotional_valence=record["emotional_valence"] or 0.0,
                        location=record["location"],
                        participants=[p for p in record["participants"] if p]
                    ))
                
                logger.info(f"Found {len(episodes)} episodes in time range for user {user_id[:8]}")
                return episodes
                
        except Exception as e:
            logger.error(f"Failed to query episodes by time range: {e}")
            return []


    async def query_by_event_type(
        self,
        user_id: str,
        event_type: str,
        limit: int = 20
    ) -> List[Episode]:
        """
        按事件类型查询情景记忆
        """
        if not self.driver:
            return []
        
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    """
                    MATCH (e:Episode {user_id: $user_id, event_type: $event_type})
                    OPTIONAL MATCH (e)-[:INVOLVES]->(p)
                    OPTIONAL MATCH (e)-[:LOCATED_AT]->(l:Place)
                    RETURN e.id AS id, e.event_type AS event_type,
                           e.description AS description, e.timestamp AS timestamp,
                           e.emotional_valence AS emotional_valence,
                           l.name AS location,
                           collect(DISTINCT p.id) AS participants
                    ORDER BY e.timestamp DESC
                    LIMIT $limit
                    """,
                    {
                        "user_id": user_id,
                        "event_type": event_type,
                        "limit": limit
                    }
                )
                
                episodes = []
                async for record in result:
                    episodes.append(Episode(
                        id=record["id"],
                        user_id=user_id,
                        event_type=record["event_type"] or "",
                        description=record["description"] or "",
                        timestamp=record["timestamp"].to_native() if record["timestamp"] else datetime.utcnow(),
                        emotional_valence=record["emotional_valence"] or 0.0,
                        location=record["location"],
                        participants=[p for p in record["participants"] if p]
                    ))
                
                return episodes
                
        except Exception as e:
            logger.error(f"Failed to query episodes by type: {e}")
            return []
    
    async def link_to_entities(
        self,
        episode_id: str,
        user_id: str,
        entity_ids: List[str]
    ) -> int:
        """
        关联情景到知识图谱实体
        
        创建 INVOLVES 关系
        
        Returns:
            linked_count: 成功关联的数量
        """
        if not self.driver or not entity_ids:
            return 0
        
        linked_count = 0
        
        try:
            async with self.driver.session() as session:
                for entity_id in entity_ids:
                    result = await session.run(
                        """
                        MATCH (e:Episode {id: $episode_id, user_id: $user_id})
                        MATCH (entity {id: $entity_id, user_id: $user_id})
                        MERGE (e)-[r:INVOLVES]->(entity)
                        RETURN count(r) AS count
                        """,
                        {
                            "episode_id": episode_id,
                            "user_id": user_id,
                            "entity_id": entity_id
                        }
                    )
                    
                    record = await result.single()
                    if record and record["count"] > 0:
                        linked_count += 1
                
                logger.info(f"Linked episode {episode_id[:8]} to {linked_count} entities")
                return linked_count
                
        except Exception as e:
            logger.error(f"Failed to link episode to entities: {e}")
            return linked_count
    
    async def get_episode_by_id(
        self,
        user_id: str,
        episode_id: str
    ) -> Optional[Episode]:
        """获取单个情景记忆"""
        if not self.driver:
            return None
        
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    """
                    MATCH (e:Episode {id: $episode_id, user_id: $user_id})
                    OPTIONAL MATCH (e)-[:INVOLVES]->(p)
                    OPTIONAL MATCH (e)-[:LOCATED_AT]->(l:Place)
                    RETURN e.id AS id, e.event_type AS event_type,
                           e.description AS description, e.timestamp AS timestamp,
                           e.emotional_valence AS emotional_valence,
                           l.name AS location,
                           collect(DISTINCT p.id) AS participants
                    """,
                    {"episode_id": episode_id, "user_id": user_id}
                )
                
                record = await result.single()
                if not record:
                    return None
                
                return Episode(
                    id=record["id"],
                    user_id=user_id,
                    event_type=record["event_type"] or "",
                    description=record["description"] or "",
                    timestamp=record["timestamp"].to_native() if record["timestamp"] else datetime.utcnow(),
                    emotional_valence=record["emotional_valence"] or 0.0,
                    location=record["location"],
                    participants=[p for p in record["participants"] if p]
                )
                
        except Exception as e:
            logger.error(f"Failed to get episode: {e}")
            return None
    
    async def get_recent_episodes(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Episode]:
        """获取最近的情景记忆"""
        if not self.driver:
            return []
        
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    """
                    MATCH (e:Episode {user_id: $user_id})
                    OPTIONAL MATCH (e)-[:INVOLVES]->(p)
                    OPTIONAL MATCH (e)-[:LOCATED_AT]->(l:Place)
                    RETURN e.id AS id, e.event_type AS event_type,
                           e.description AS description, e.timestamp AS timestamp,
                           e.emotional_valence AS emotional_valence,
                           l.name AS location,
                           collect(DISTINCT p.id) AS participants
                    ORDER BY e.timestamp DESC
                    LIMIT $limit
                    """,
                    {"user_id": user_id, "limit": limit}
                )
                
                episodes = []
                async for record in result:
                    episodes.append(Episode(
                        id=record["id"],
                        user_id=user_id,
                        event_type=record["event_type"] or "",
                        description=record["description"] or "",
                        timestamp=record["timestamp"].to_native() if record["timestamp"] else datetime.utcnow(),
                        emotional_valence=record["emotional_valence"] or 0.0,
                        location=record["location"],
                        participants=[p for p in record["participants"] if p]
                    ))
                
                return episodes
                
        except Exception as e:
            logger.error(f"Failed to get recent episodes: {e}")
            return []
    
    async def delete_episode(
        self,
        user_id: str,
        episode_id: str
    ) -> bool:
        """删除情景记忆"""
        if not self.driver:
            return False
        
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    """
                    MATCH (e:Episode {id: $episode_id, user_id: $user_id})
                    DETACH DELETE e
                    RETURN count(*) AS deleted
                    """,
                    {"episode_id": episode_id, "user_id": user_id}
                )
                
                record = await result.single()
                return record and record["deleted"] > 0
                
        except Exception as e:
            logger.error(f"Failed to delete episode: {e}")
            return False

