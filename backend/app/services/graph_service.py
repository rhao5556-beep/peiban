"""图谱服务 - Neo4j 操作"""
import math
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    """实体"""
    id: str
    user_id: str
    name: str
    type: str  # person, place, preference, event
    mention_count: int = 1
    first_mentioned_at: datetime = field(default_factory=datetime.now)
    last_mentioned_at: datetime = field(default_factory=datetime.now)
    provenance: List[str] = field(default_factory=list)


@dataclass
class Edge:
    """关系边"""
    id: str
    source_id: str
    target_id: str
    relation_type: str  # family, friend, like, concern
    weight: float = 1.0
    decay_rate: float = 0.03
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    provenance: List[str] = field(default_factory=list)
    current_weight: Optional[float] = None  # 动态计算的当前权重


@dataclass
class GraphUpdateResult:
    """图谱更新结果"""
    created_nodes: List[str] = field(default_factory=list)
    updated_nodes: List[str] = field(default_factory=list)
    created_edges: List[str] = field(default_factory=list)
    updated_edges: List[str] = field(default_factory=list)


class GraphService:
    """
    记忆图谱服务 - 管理 Neo4j 中的实体和关系
    
    权重规则：
    | 权重范围 | 关系类型 | 衰减速度 | 示例 |
    |---------|---------|---------|------|
    | 0.9-1.0 | 核心关系 | 很慢（0.05/月） | 父母、配偶、最好的朋友 |
    | 0.7-0.9 | 重要关系 | 慢（0.1/月） | 担心的事、重要决定 |
    | 0.5-0.7 | 一般关系 | 中速（0.2/月） | 普通朋友、兴趣爱好 |
    | 0.3-0.5 | 弱关系 | 快（0.5/月） | 见过一次的人 |
    | 0.1-0.3 | 临时关系 | 很快（1.0/月） | 闲聊的话题 |
    | < 0.1 | 准备归档 | 直接归档 | 可以不在热存储 |
    
    Property 1: 图谱数据往返一致性
    Property 2: 边权重衰减公式正确性
    """
    
    def __init__(self, neo4j_driver=None):
        self.driver = neo4j_driver
        self.default_decay_rate = 0.2 / 30  # 默认：一般关系，每月衰减0.2
        self.read_timeout_s = 5.0
        self.write_timeout_s = max(10.0, float(settings.LLM_REQUEST_TIMEOUT_S))
    
    async def merge_subgraph(
        self,
        user_id: str,
        nodes: List[Dict],
        edges: List[Dict],
        conversation_id: str
    ) -> GraphUpdateResult:
        """
        合并子图到用户图谱（幂等操作）
        
        Args:
            user_id: 用户 ID
            nodes: 节点列表 [{"id": str, "name": str, "type": str}, ...]
            edges: 边列表 [{"source_id": str, "target_id": str, "relation_type": str}, ...]
            conversation_id: 对话 ID（用于溯源）
            
        Returns:
            GraphUpdateResult: 创建/更新的节点和边列表
        """
        result = GraphUpdateResult()
        
        if not self.driver:
            logger.warning("Neo4j driver not initialized, skipping graph write")
            return result
        
        async with self.driver.session() as session:
            # 1. 合并节点
            for node in nodes:
                node_id = node.get("id") or str(uuid.uuid4())
                created = await session.execute_write(
                    self._merge_entity_tx,
                    entity_id=node_id,
                    user_id=user_id,
                    name=node["name"],
                    entity_type=node.get("type", "entity"),
                    conversation_id=conversation_id
                )
                if created:
                    result.created_nodes.append(node_id)
                else:
                    result.updated_nodes.append(node_id)
            
            # 2. 合并边
            for edge in edges:
                edge_id = edge.get("id") or str(uuid.uuid4())
                created = await session.execute_write(
                    self._merge_edge_tx,
                    edge_id=edge_id,
                    source_id=edge["source_id"],
                    target_id=edge["target_id"],
                    relation_type=edge.get("relation_type", "RELATES_TO"),
                    decay_rate=edge.get("decay_rate", self.default_decay_rate),
                    conversation_id=conversation_id
                )
                if created:
                    result.created_edges.append(edge_id)
                else:
                    result.updated_edges.append(edge_id)
        
        logger.info(f"Graph merge completed: {len(result.created_nodes)} new nodes, "
                   f"{len(result.created_edges)} new edges")
        return result
    
    @staticmethod
    async def _merge_entity_tx(tx, entity_id: str, user_id: str, name: str, 
                               entity_type: str, conversation_id: str) -> bool:
        """合并实体节点的事务函数"""
        query = """
        MERGE (e:Entity {id: $entity_id, user_id: $user_id})
        ON CREATE SET 
            e.name = $name,
            e.type = $entity_type,
            e.mention_count = 1,
            e.first_mentioned_at = datetime(),
            e.last_mentioned_at = datetime(),
            e.provenance = [$conversation_id],
            e.created = true
        ON MATCH SET
            e.mention_count = e.mention_count + 1,
            e.last_mentioned_at = datetime(),
            e.provenance = e.provenance + $conversation_id,
            e.created = false
        RETURN e.created AS created
        """
        result = await tx.run(
            query,
            entity_id=entity_id,
            user_id=user_id,
            name=name,
            entity_type=entity_type,
            conversation_id=conversation_id,
            timeout=10.0,
        )
        record = await result.single()
        return record["created"] if record else False
    
    @staticmethod
    async def _merge_edge_tx(tx, edge_id: str, source_id: str, target_id: str,
                            relation_type: str, decay_rate: float, 
                            conversation_id: str) -> bool:
        """合并关系边的事务函数"""
        query = """
        MATCH (e1:Entity {id: $source_id})
        MATCH (e2:Entity {id: $target_id})
        MERGE (e1)-[r:RELATES_TO {id: $edge_id}]->(e2)
        ON CREATE SET
            r.relation_type = $relation_type,
            r.weight = 1.0,
            r.decay_rate = $decay_rate,
            r.created_at = datetime(),
            r.updated_at = datetime(),
            r.provenance = [$conversation_id],
            r.created = true
        ON MATCH SET
            r.weight = 1.0,
            r.updated_at = datetime(),
            r.provenance = r.provenance + $conversation_id,
            r.created = false
        RETURN r.created AS created
        """
        result = await tx.run(
            query,
            edge_id=edge_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            decay_rate=decay_rate,
            conversation_id=conversation_id,
            timeout=10.0,
        )
        record = await result.single()
        return record["created"] if record else False
    
    async def get_neighbors(
        self,
        entity_id: str,
        max_depth: int = 1,
        min_weight: float = 0.1
    ) -> List[Entity]:
        """
        获取实体的邻居节点（带权重衰减计算）
        
        Args:
            entity_id: 实体 ID
            max_depth: 最大深度
            min_weight: 最小权重阈值
            
        Returns:
            邻居实体列表
        """
        if not self.driver:
            return []
        
        async with self.driver.session() as session:
            query = f"""
            MATCH (e:Entity {{id: $entity_id}})-[r:RELATES_TO*1..{max_depth}]-(neighbor:Entity)
            WITH neighbor, r,
                 reduce(w = 1.0, rel IN r | 
                    w * rel.weight * exp(-rel.decay_rate * 
                        duration.inDays(rel.updated_at, datetime()).days)) AS current_weight
            WHERE current_weight > $min_weight
            RETURN DISTINCT neighbor, current_weight
            ORDER BY current_weight DESC
            LIMIT 50
            """
            result = await session.run(
                query,
                entity_id=entity_id,
                min_weight=min_weight,
                timeout=self.read_timeout_s,
            )
            
            entities = []
            async for record in result:
                node = record["neighbor"]
                entities.append(Entity(
                    id=node["id"],
                    user_id=node["user_id"],
                    name=node["name"],
                    type=node.get("type", "entity"),
                    mention_count=node.get("mention_count", 1),
                    first_mentioned_at=node.get("first_mentioned_at", datetime.now()),
                    last_mentioned_at=node.get("last_mentioned_at", datetime.now()),
                    provenance=node.get("provenance", [])
                ))
            return entities
    
    async def get_user_graph(self, user_id: str) -> Dict[str, Any]:
        """获取用户完整图谱（支持 LLM 生成的多种关系类型）
        
        注意：实体节点使用动态标签（Person, Location 等），不是 Entity
        """
        if not self.driver:
            return {"nodes": [], "edges": []}
        
        async with self.driver.session() as session:
            # 获取所有实体节点（使用 user_id 属性匹配，排除 User 节点）
            nodes_query = """
            MATCH (e {user_id: $user_id})
            WHERE NOT e:User
            RETURN e
            """
            nodes_result = await session.run(nodes_query, user_id=user_id, timeout=self.read_timeout_s)
            nodes = []
            async for record in nodes_result:
                nodes.append(self._node_to_dict(record["e"]))
            
            # 添加用户节点作为图谱中心
            user_node = {
                "id": user_id,
                "name": "我",
                "type": "user",
                "mention_count": 1
            }
            nodes.insert(0, user_node)
            
            # 获取 User -> Entity 的所有关系（支持多种关系类型）
            user_edges_query = """
            MATCH (u:User {id: $user_id})-[r]->(e {user_id: $user_id})
            WHERE NOT e:User
            RETURN u.id AS source_id, e.id AS target_id, r, type(r) AS rel_type,
                   CASE WHEN r.updated_at IS NOT NULL 
                        THEN r.weight * exp(-coalesce(r.decay_rate, 0.03) * 
                             duration.inDays(r.updated_at, datetime()).days)
                        ELSE coalesce(r.weight, 0.5) END AS current_weight
            """
            edges_result = await session.run(user_edges_query, user_id=user_id, timeout=self.read_timeout_s)
            edges = []
            async for record in edges_result:
                edge_dict = self._edge_to_dict(record["r"], record["current_weight"])
                edge_dict["source_id"] = record["source_id"]
                edge_dict["target_id"] = record["target_id"]
                # 使用实际的关系类型
                edge_dict["relation_type"] = record["rel_type"]
                edges.append(edge_dict)
            
            # 获取 Entity -> Entity 的所有关系（网状结构的关键）
            # 注意：只检查源节点的 user_id，因为目标节点可能是共享实体
            entity_edges_query = """
            MATCH (e1 {user_id: $user_id})-[r]->(e2)
            WHERE NOT e1:User AND NOT e2:User
            RETURN e1.id AS source_id, e2.id AS target_id, r, type(r) AS rel_type,
                   CASE WHEN r.updated_at IS NOT NULL 
                        THEN r.weight * exp(-coalesce(r.decay_rate, 0.03) * 
                             duration.inDays(r.updated_at, datetime()).days)
                        ELSE coalesce(r.weight, 0.5) END AS current_weight
            """
            entity_edges_result = await session.run(entity_edges_query, user_id=user_id, timeout=self.read_timeout_s)
            async for record in entity_edges_result:
                edge_dict = self._edge_to_dict(record["r"], record["current_weight"])
                edge_dict["source_id"] = record["source_id"]
                edge_dict["target_id"] = record["target_id"]
                # 使用实际的关系类型
                edge_dict["relation_type"] = record["rel_type"]
                edges.append(edge_dict)
            
            return {"nodes": nodes, "edges": edges}
    
    def _node_to_dict(self, node) -> Dict:
        """将 Neo4j 节点转换为字典"""
        return {
            "id": node["id"],
            "name": node["name"],
            "type": node.get("type", "entity"),
            "mention_count": node.get("mention_count", 1)
        }
    
    def _edge_to_dict(self, edge, current_weight: float = None) -> Dict:
        """将 Neo4j 边转换为字典"""
        return {
            "id": edge["id"],
            "relation_type": edge.get("relation_type", "RELATES_TO"),
            "weight": edge.get("weight", 1.0),
            "current_weight": current_weight,
            "decay_rate": edge.get("decay_rate", self.default_decay_rate)
        }
    
    def calculate_current_weight(
        self,
        stored_weight: float,
        decay_rate: float,
        updated_at: datetime
    ) -> float:
        """
        读取时动态计算当前权重（Lazy Read）
        
        Property 2: 边权重衰减公式正确性
        公式: weight_new = weight_old × exp(-decay_rate × days)
        """
        days = (datetime.now() - updated_at).days
        return stored_weight * math.exp(-decay_rate * days)
    
    async def refresh_edge(
        self,
        edge_id: str,
        conversation_id: str
    ) -> Optional[Edge]:
        """
        刷新边权重（提及时调用）
        
        重置权重为 1.0，更新 updated_at
        """
        if not self.driver:
            return None
        
        async with self.driver.session() as session:
            query = """
            MATCH ()-[r:RELATES_TO {id: $edge_id}]->()
            SET r.weight = 1.0,
                r.updated_at = datetime(),
                r.provenance = r.provenance + $conversation_id
            RETURN r, startNode(r) AS source, endNode(r) AS target
            """
            result = await session.run(
                query,
                edge_id=edge_id,
                conversation_id=conversation_id,
                timeout=self.read_timeout_s,
            )
            record = await result.single()
            
            if not record:
                return None
            
            r = record["r"]
            return Edge(
                id=r["id"],
                source_id=record["source"]["id"],
                target_id=record["target"]["id"],
                relation_type=r.get("relation_type", "RELATES_TO"),
                weight=1.0,
                decay_rate=r.get("decay_rate", self.default_decay_rate),
                created_at=r.get("created_at", datetime.now()),
                updated_at=datetime.now(),
                provenance=r.get("provenance", [])
            )
    
    async def get_decayed_important_edges(
        self,
        user_id: str,
        threshold: float = 0.5
    ) -> List[Edge]:
        """
        获取权重衰减到阈值以下的重要关系边
        
        用于触发主动关怀（Day 30 场景）
        """
        if not self.driver:
            return []
        
        async with self.driver.session() as session:
            query = """
            MATCH (e1:Entity {user_id: $user_id})-[r:RELATES_TO]->(e2:Entity)
            WITH e1, r, e2,
                 r.weight * exp(-r.decay_rate * 
                    duration.inDays(r.updated_at, datetime()).days) AS current_weight
            WHERE current_weight < $threshold AND current_weight > 0.1
            RETURN r, e1.id AS source_id, e2.id AS target_id, current_weight
            ORDER BY current_weight ASC
            LIMIT 20
            """
            result = await session.run(query, user_id=user_id, threshold=threshold, timeout=self.read_timeout_s)
            
            edges = []
            async for record in result:
                r = record["r"]
                edges.append(Edge(
                    id=r["id"],
                    source_id=record["source_id"],
                    target_id=record["target_id"],
                    relation_type=r.get("relation_type", "RELATES_TO"),
                    weight=r.get("weight", 1.0),
                    decay_rate=r.get("decay_rate", self.default_decay_rate),
                    created_at=r.get("created_at", datetime.now()),
                    updated_at=r.get("updated_at", datetime.now()),
                    provenance=r.get("provenance", []),
                    current_weight=record["current_weight"]
                ))
            return edges
    
    async def apply_time_decay(self, user_id: str) -> int:
        """
        应用时间衰减（批量更新）
        
        由 Celery Beat 夜间调用
        注意：实际权重通过 Lazy Read 计算，此方法用于清理过期边
        
        Returns:
            删除的过期边数量
        """
        if not self.driver:
            return 0
        
        async with self.driver.session() as session:
            # 删除权重衰减到 0.01 以下的边
            query = """
            MATCH (e1:Entity {user_id: $user_id})-[r:RELATES_TO]->(e2:Entity)
            WITH r,
                 r.weight * exp(-r.decay_rate * 
                    duration.inDays(r.updated_at, datetime()).days) AS current_weight
            WHERE current_weight < 0.01
            DELETE r
            RETURN count(r) AS deleted_count
            """
            result = await session.run(query, user_id=user_id, timeout=self.read_timeout_s)
            record = await result.single()
            return record["deleted_count"] if record else 0


# Cypher 查询模板
CYPHER_TEMPLATES = {
    "merge_entity": """
        MERGE (e:Entity {id: $entity_id, user_id: $user_id})
        ON CREATE SET 
            e.name = $name,
            e.type = $type,
            e.mention_count = 1,
            e.first_mentioned_at = datetime(),
            e.last_mentioned_at = datetime(),
            e.provenance = [$conversation_id]
        ON MATCH SET
            e.mention_count = e.mention_count + 1,
            e.last_mentioned_at = datetime(),
            e.provenance = e.provenance + $conversation_id
        RETURN e
    """,
    
    "merge_edge": """
        MATCH (e1:Entity {id: $source_id})
        MATCH (e2:Entity {id: $target_id})
        MERGE (e1)-[r:RELATES_TO {id: $edge_id}]->(e2)
        ON CREATE SET
            r.relation_type = $relation_type,
            r.weight = 1.0,
            r.decay_rate = $decay_rate,
            r.created_at = datetime(),
            r.updated_at = datetime(),
            r.provenance = [$conversation_id]
        ON MATCH SET
            r.weight = 1.0,
            r.updated_at = datetime(),
            r.provenance = r.provenance + $conversation_id
        RETURN r
    """,
    
    "get_neighbors": """
        MATCH (e:Entity {id: $entity_id})-[r:RELATES_TO*1..{max_depth}]-(neighbor:Entity)
        WITH neighbor, r,
             r.weight * exp(-r.decay_rate * duration.inDays(r.updated_at, datetime()).days) AS current_weight
        WHERE current_weight > 0.1
        RETURN neighbor, current_weight
        ORDER BY current_weight DESC
        LIMIT 50
    """,
    
    "get_user_graph": """
        MATCH (u:User {id: $user_id})-[:OWNS]->(e:Entity)
        OPTIONAL MATCH (e)-[r:RELATES_TO]-(e2:Entity)
        RETURN e, r, e2
    """
}
