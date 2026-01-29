"""混合检索服务 - Vector + Graph + Entity Facts"""
import math
import logging
import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid
from openai import AsyncOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class Memory:
    """记忆"""
    id: str
    content: str
    entity_id: str = ""  # 可选字段，Milvus 中不存在
    cosine_sim: float = 0.0
    edge_weight: float = 0.0
    valence: float = 0.0
    recency_score: float = 0.0
    final_score: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.now)
    score_breakdown: Optional[Dict[str, float]] = None


@dataclass
class RetrievalResult:
    """检索结果"""
    memories: List[Memory]
    query: str
    affinity_score: float
    retrieval_time_ms: float
    vector_candidates_count: int = 0
    graph_expanded_count: int = 0


class EmbeddingService:
    """
    向量编码服务 - 使用 SiliconFlow 云端 API
    
    Property 17: Embedding Cache Effectiveness
    - 使用 Redis 缓存 embedding 结果
    - 缓存 TTL: 5 分钟
    - 重复查询使用缓存，embedding_time < 10ms
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        if not hasattr(self, 'client'):
            self.client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_API_BASE
            )
            self.model_name = model_name
            self._redis = None
            self._cache_ttl = 300  # 5 minutes
            logger.info(f"Initialized Cloud Embedding service with model: {model_name}")
    
    def _get_redis(self):
        """懒加载 Redis 客户端"""
        if self._redis is None:
            try:
                from app.core.database import get_redis_client
                self._redis = get_redis_client()
            except Exception as e:
                logger.warning(f"Failed to get Redis client for embedding cache: {e}")
        return self._redis
    
    def _get_cache_key(self, text: str) -> str:
        """生成缓存键（基于文本哈希）"""
        import hashlib
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"embedding_cache:{self.model_name}:{text_hash}"
    
    async def encode(self, text: str, use_cache: bool = True) -> List[float]:
        """
        编码文本为向量 (异步云端调用，支持缓存)
        
        Args:
            text: 要编码的文本
            use_cache: 是否使用缓存
            
        Returns:
            向量列表
        """
        start_time = datetime.now()
        
        # 尝试从缓存获取
        if use_cache:
            cached = await self._get_cached_embedding(text)
            if cached is not None:
                elapsed = (datetime.now() - start_time).total_seconds() * 1000
                logger.debug(f"Embedding cache hit, time: {elapsed:.2f}ms")
                return cached
        
        # 调用 API
        try:
            response = await self.client.embeddings.create(
                input=text,
                model=self.model_name
            )
            embedding = response.data[0].embedding
            
            # 缓存结果
            if use_cache:
                await self._cache_embedding(text, embedding)
            
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            logger.debug(f"Embedding computed, time: {elapsed:.2f}ms")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Cloud embedding failed: {e}")
            # 返回零向量作为 fallback (1024维是 bge-m3 的输出维度)
            return [0.0] * 1024
    
    async def _get_cached_embedding(self, text: str) -> Optional[List[float]]:
        """从缓存获取 embedding"""
        redis = self._get_redis()
        if not redis:
            return None
        
        try:
            cache_key = self._get_cache_key(text)
            cached = await redis.get(cache_key)
            
            if cached:
                return json.loads(cached)
                
        except Exception as e:
            logger.warning(f"Failed to get cached embedding: {e}")
        
        return None
    
    async def _cache_embedding(self, text: str, embedding: List[float]) -> None:
        """缓存 embedding"""
        redis = self._get_redis()
        if not redis:
            return
        
        try:
            cache_key = self._get_cache_key(text)
            await redis.setex(cache_key, self._cache_ttl, json.dumps(embedding))
            
        except Exception as e:
            logger.warning(f"Failed to cache embedding: {e}")

    async def encode_batch(self, texts: List[str], use_cache: bool = True) -> List[List[float]]:
        """
        批量编码 (异步云端调用，支持缓存)
        
        Args:
            texts: 要编码的文本列表
            use_cache: 是否使用缓存
            
        Returns:
            向量列表的列表
        """
        if use_cache:
            # 检查缓存，分离已缓存和未缓存的文本
            results = [None] * len(texts)
            uncached_indices = []
            uncached_texts = []
            
            for i, text in enumerate(texts):
                cached = await self._get_cached_embedding(text)
                if cached is not None:
                    results[i] = cached
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(text)
            
            # 如果所有都已缓存，直接返回
            if not uncached_texts:
                return results
            
            # 批量编码未缓存的文本
            try:
                response = await self.client.embeddings.create(
                    input=uncached_texts,
                    model=self.model_name
                )
                
                for j, embedding_data in enumerate(response.data):
                    idx = uncached_indices[j]
                    embedding = embedding_data.embedding
                    results[idx] = embedding
                    
                    # 缓存结果
                    await self._cache_embedding(uncached_texts[j], embedding)
                
                return results
                
            except Exception as e:
                logger.error(f"Cloud batch embedding failed: {e}")
                # 填充零向量
                for idx in uncached_indices:
                    results[idx] = [0.0] * 1024
                return results
        
        # 不使用缓存，直接批量编码
        try:
            response = await self.client.embeddings.create(
                input=texts,
                model=self.model_name
            )
            return [d.embedding for d in response.data]
        except Exception as e:
            logger.error(f"Cloud batch embedding failed: {e}")
            return [[0.0] * 1024 for _ in texts]
    
    async def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        redis = self._get_redis()
        if not redis:
            return {"enabled": False}
        
        try:
            pattern = f"embedding_cache:{self.model_name}:*"
            keys = redis.keys(pattern)
            return {
                "enabled": True,
                "cached_embeddings": len(keys),
                "ttl_seconds": self._cache_ttl,
            }
        except Exception as e:
            logger.warning(f"Failed to get embedding cache stats: {e}")
            return {"enabled": True, "error": str(e)}
    
    async def clear_cache(self) -> int:
        """清除所有缓存的 embedding"""
        redis = self._get_redis()
        if not redis:
            return 0
        
        try:
            pattern = f"embedding_cache:{self.model_name}:*"
            keys = redis.keys(pattern)
            if keys:
                return redis.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Failed to clear embedding cache: {e}")
            return 0


class RetrievalService:
    """
    混合检索服务 - Vector + Graph
    
    Property 5: 检索结果包含完整分数分解
    
    四因子加权:
    - cosine_sim: 0.4 (语义相似度)
    - edge_weight: 0.3 (关系强度)
    - affinity_bonus: 0.2 (好感度加成)
    - recency_score: 0.1 (时间新鲜度)
    """
    
    # 权重配置
    COSINE_WEIGHT = 0.4
    EDGE_WEIGHT = 0.3
    AFFINITY_WEIGHT = 0.2
    RECENCY_WEIGHT = 0.1
    
    def __init__(self, milvus_client=None, graph_service=None, db_session=None):
        self.milvus = milvus_client
        self.graph = graph_service
        self.db = db_session
        self.embedding_service = EmbeddingService()
    
    async def hybrid_retrieve(
        self,
        user_id: str,
        query: str,
        affinity_score: float,
        top_k: int = 10
    ) -> RetrievalResult:
        """
        混合检索记忆
        
        Args:
            user_id: 用户 ID
            query: 查询文本
            affinity_score: 当前好感度（影响 re-rank）
            top_k: 返回数量
            
        Returns:
            RetrievalResult: 排序后的记忆列表
        """
        start_time = datetime.now()
        
        # Step 1: Vector Search (Milvus)
        vector_candidates = await self._vector_search(user_id, query, top_k=50)

        if self.db:
            try:
                entity_names = await self._extract_query_entities(query)
            except Exception:
                entity_names = []
            if entity_names:
                pg_candidates = await self._postgres_entity_search(
                    user_id=user_id,
                    entity_names=entity_names,
                    limit=30,
                )
                if pg_candidates:
                    seen = {m.id for m in vector_candidates}
                    for m in pg_candidates:
                        if m.id not in seen:
                            vector_candidates.append(m)
                            seen.add(m.id)
        
        # Step 2: Graph Expansion (Neo4j)
        graph_expanded = await self._graph_expand(vector_candidates, user_id)
        
        # Step 3: Re-rank（4 因子加权）
        ranked_memories = self._rerank(graph_expanded, affinity_score)
        
        # 取 top_k
        top_memories = ranked_memories[:top_k]
        
        retrieval_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return RetrievalResult(
            memories=top_memories,
            query=query,
            affinity_score=affinity_score,
            retrieval_time_ms=retrieval_time,
            vector_candidates_count=len(vector_candidates),
            graph_expanded_count=len(graph_expanded)
        )
    
    async def _vector_search(
        self,
        user_id: str,
        query: str,
        top_k: int = 50
    ) -> List[Memory]:
        """向量检索"""
        # 1. 编码查询文本
        query_embedding = await self.embedding_service.encode(query)
        
        if not self.milvus:
            logger.warning("Milvus client not initialized, returning empty results")
            return []
        
        try:
            # 2. 搜索相似向量
            search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
            results = self.milvus.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                expr=f'user_id == "{user_id}"',
                output_fields=["id", "content", "valence", "created_at"]
            )
            
            # 3. 转换为 Memory 对象
            memories = []
            for hits in results:
                for hit in hits:
                    try:
                        # pymilvus Hit 对象使用字典式访问 hit["field_name"]
                        # 或者通过 hit.entity.get("field_name")
                        content = hit.get("content") if hasattr(hit, 'get') else hit.entity.get("content")
                        valence = hit.get("valence") if hasattr(hit, 'get') else hit.entity.get("valence")
                        created_at_val = hit.get("created_at") if hasattr(hit, 'get') else hit.entity.get("created_at")
                        mem_id = hit.get("id") if hasattr(hit, 'get') else hit.entity.get("id")
                        
                        # 如果上面的方式都失败，尝试直接索引
                        if content is None:
                            content = hit["content"] if "content" in hit else ""
                        if valence is None:
                            valence = hit["valence"] if "valence" in hit else 0.0
                        if created_at_val is None:
                            created_at_val = hit["created_at"] if "created_at" in hit else None
                        if mem_id is None:
                            mem_id = hit["id"] if "id" in hit else str(hit.id)
                        
                        # created_at 在 Milvus 中存储为 INT64 时间戳
                        if isinstance(created_at_val, int):
                            created_at = datetime.fromtimestamp(created_at_val)
                        elif isinstance(created_at_val, datetime):
                            created_at = created_at_val
                        else:
                            created_at = datetime.now()
                        
                        # 获取相似度分数
                        score = hit.score if hasattr(hit, 'score') else (hit.distance if hasattr(hit, 'distance') else 0.0)
                        
                        memories.append(Memory(
                            id=mem_id or str(hit.id),
                            content=content or "",
                            cosine_sim=score,
                            valence=valence or 0.0,
                            created_at=created_at,
                            recency_score=self._calculate_recency(created_at)
                        ))
                    except Exception as e:
                        logger.warning(f"Failed to parse hit: {e}, hit type: {type(hit)}, hit dir: {dir(hit)[:10]}")
                        continue
            
            logger.info(f"Vector search returned {len(memories)} candidates")
            return memories
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    async def _graph_expand(
        self,
        candidates: List[Memory],
        user_id: str
    ) -> List[Memory]:
        """图扩展 - 获取关联实体的邻居记忆"""
        expanded = list(candidates)
        seen_ids = {m.id for m in candidates}
        
        if not self.graph:
            return expanded
        
        try:
            # 对每个候选记忆的实体，获取邻居
            for memory in candidates[:10]:  # 限制扩展数量
                if not memory.entity_id:
                    continue
                
                neighbors = await self.graph.get_neighbors(
                    memory.entity_id, 
                    max_depth=1,
                    min_weight=0.3
                )
                
                # 获取邻居实体关联的记忆
                for neighbor in neighbors[:5]:
                    neighbor_memories = await self._get_entity_memories(
                        neighbor.id, user_id
                    )
                    for nm in neighbor_memories:
                        if nm.id not in seen_ids:
                            # 设置边权重（从图谱获取）
                            nm.edge_weight = 0.5  # 默认邻居权重
                            expanded.append(nm)
                            seen_ids.add(nm.id)
            
            logger.info(f"Graph expansion: {len(candidates)} -> {len(expanded)}")
            
        except Exception as e:
            logger.error(f"Graph expansion failed: {e}")
        
        return expanded
    
    async def _get_entity_memories(
        self,
        entity_id: str,
        user_id: str,
        limit: int = 5
    ) -> List[Memory]:
        return []

    async def _postgres_entity_search(
        self,
        user_id: str,
        entity_names: List[str],
        limit: int = 30,
    ) -> List[Memory]:
        if not self.db:
            return []
        try:
            user_uuid = uuid.UUID(user_id)
        except Exception:
            return []

        names = [n.strip() for n in entity_names if n and n.strip()]
        if not names:
            return []

        from sqlalchemy import or_, select
        from app.models.memory import Memory as MemoryModel

        clauses = [MemoryModel.content.ilike(f"%{n}%") for n in names[:10]]
        stmt = (
            select(MemoryModel)
            .where(
                MemoryModel.user_id == user_uuid,
                MemoryModel.status == "committed",
                or_(*clauses),
            )
            .order_by(MemoryModel.created_at.desc())
            .limit(int(limit))
        )

        res = await self.db.execute(stmt)
        rows = list(res.scalars().all())
        out: List[Memory] = []
        for r in rows:
            created_at = r.created_at if isinstance(r.created_at, datetime) else datetime.now()
            out.append(
                Memory(
                    id=str(r.id),
                    content=r.content,
                    cosine_sim=0.0,
                    edge_weight=0.0,
                    valence=float(r.valence or 0.0),
                    created_at=created_at,
                    recency_score=self._calculate_recency(created_at),
                )
            )
        return out
    
    def _rerank(
        self,
        memories: List[Memory],
        affinity_score: float
    ) -> List[Memory]:
        """
        Re-rank（4 因子加权）
        
        Property 5: 检索结果包含完整分数分解
        """
        for memory in memories:
            memory.final_score = self.calculate_final_score(memory, affinity_score)
            memory.score_breakdown = self.decompose_score(memory, affinity_score)
        
        # 按 final_score 降序排序
        return sorted(memories, key=lambda m: m.final_score or 0, reverse=True)
    
    def calculate_final_score(
        self,
        memory: Memory,
        affinity_score: float
    ) -> float:
        """
        计算最终分数（四因子加权）
        
        score = cosine_sim * 0.4 + 
                edge_weight * 0.3 + 
                affinity_bonus * 0.2 + 
                recency_score * 0.1
        """
        # 好感度加成：只对正向情感记忆生效
        affinity_bonus = max(0, affinity_score) if memory.valence > 0 else 0
        
        return (
            memory.cosine_sim * self.COSINE_WEIGHT +
            memory.edge_weight * self.EDGE_WEIGHT +
            affinity_bonus * self.AFFINITY_WEIGHT +
            memory.recency_score * self.RECENCY_WEIGHT
        )
    
    def decompose_score(
        self,
        memory: Memory,
        affinity_score: float
    ) -> Dict[str, float]:
        """
        分解分数（用于可解释性）
        
        返回每个因子的贡献
        """
        affinity_bonus = max(0, affinity_score) if memory.valence > 0 else 0
        
        return {
            "cosine_contribution": memory.cosine_sim * self.COSINE_WEIGHT,
            "edge_contribution": memory.edge_weight * self.EDGE_WEIGHT,
            "affinity_contribution": affinity_bonus * self.AFFINITY_WEIGHT,
            "recency_contribution": memory.recency_score * self.RECENCY_WEIGHT,
            "total": self.calculate_final_score(memory, affinity_score)
        }
    
    def _calculate_recency(self, created_at: datetime) -> float:
        """
        计算时间新鲜度分数
        
        使用指数衰减：score = exp(-days / 30)
        30天内的记忆保持较高分数
        """
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        
        days = (datetime.now() - created_at).days
        return math.exp(-days / 30)
    
    def unified_rerank(
        self,
        vector_memories: List[Memory],
        graph_facts: List[Dict[str, Any]],
        affinity_score: float,
        top_k: int = 10
    ) -> tuple:
        """
        统一 Re-rank - 合并向量检索和图谱检索结果后重排序
        
        在并行检索完成后调用，将两种来源的结果统一排序
        
        优化（2026-01-19）：
        - 新增最新优先加权：最近7天的记忆额外加权 10-15%
        - 用于冲突记忆处理：优先使用最新的观点
        
        Args:
            vector_memories: 向量检索返回的 Memory 列表
            graph_facts: 图谱检索返回的事实列表
            affinity_score: 当前好感度分数
            top_k: 返回数量
            
        Returns:
            (ranked_memories, ranked_facts): 重排序后的结果
        """
        from datetime import datetime, timedelta
        
        # 1. 对向量记忆进行 Re-rank（新增最新优先加权）
        now = datetime.now()
        recency_window_days = 7  # 最近7天的记忆额外加权
        recency_boost = 0.15  # 加权 15%
        
        for memory in vector_memories:
            # 计算基础分数
            memory.final_score = self.calculate_final_score(memory, affinity_score)
            memory.score_breakdown = self.decompose_score(memory, affinity_score)
            
            # 新增：最新优先加权
            if hasattr(memory, 'created_at') and memory.created_at:
                days_ago = (now - memory.created_at).days
                
                if days_ago <= recency_window_days:
                    # 最近7天的记忆额外加权
                    # 线性衰减：7天前 = 15% boost，今天 = 15% boost
                    boost_factor = 1.0 + recency_boost
                    old_score = memory.final_score or 0
                    memory.final_score = old_score * boost_factor
                    
                    logger.debug(
                        f"Recency boost applied: memory from {days_ago} days ago, "
                        f"score {old_score:.3f} -> {memory.final_score:.3f}"
                    )
        
        ranked_memories = sorted(
            vector_memories, 
            key=lambda m: m.final_score or 0, 
            reverse=True
        )[:top_k]
        
        # 2. 对图谱事实进行排序（按 hop 和 weight）
        # 直接关系优先，权重高的优先
        ranked_facts = sorted(
            graph_facts,
            key=lambda f: (f.get("hop", 1), -f.get("weight", 0))
        )[:20]  # 限制图谱事实数量
        
        logger.info(
            f"Unified rerank: {len(vector_memories)} memories -> {len(ranked_memories)}, "
            f"{len(graph_facts)} facts -> {len(ranked_facts)}"
        )
        
        return ranked_memories, ranked_facts

    async def retrieve_entity_facts(
        self,
        user_id: str,
        query: str,
        neo4j_driver=None,
        max_hops: int = 3
    ) -> List[Dict[str, Any]]:
        """
        基于查询实体的图谱事实检索 (支持 3-hop 遍历)
        
        流程：
        1. 用 LLM 从 query 中提取实体名称
        2. 在 Neo4j 中查找这些实体
        3. 获取实体的 1-hop、2-hop 和 3-hop 关系
        4. 返回格式化的事实列表（区分直接/间接关系）
        
        Args:
            user_id: 用户 ID
            query: 查询文本
            neo4j_driver: Neo4j 驱动
            max_hops: 最大跳数 (默认 3)
        """
        logger.info(f"retrieve_entity_facts: query={query}, user={user_id}, max_hops={max_hops}")
        from datetime import datetime
        from app.services.temporal_normalizer import extract_temporal_constraints
        date_constraints = extract_temporal_constraints(query, anchor_dt=datetime.utcnow(), timezone="UTC")
        
        # Step 1: 从 query 中提取实体名称
        entity_names = await self._extract_query_entities(query)
        
        if not entity_names:
            logger.info(f"No entities extracted from query")
            return []
        
        logger.info(f"Extracted entities: {entity_names}")
        
        # Step 2 & 3: 查询 Neo4j 获取实体的所有关系
        driver = neo4j_driver or self.graph
        
        if not driver:
            logger.warning("No Neo4j driver available")
            return []
        
        facts = []
        
        try:
            # 如果 driver 是 GraphService 实例，获取其内部 driver
            if hasattr(driver, 'driver'):
                neo4j = driver.driver
            else:
                neo4j = driver
            
            if not neo4j:
                return []
            
            async with neo4j.session() as session:
                for entity_name in entity_names:
                    # 查找实体节点（模糊匹配名称）
                    find_entity_query = """
                    MATCH (e {user_id: $user_id})
                    WHERE e.name CONTAINS $entity_name OR $entity_name CONTAINS e.name
                    RETURN e.id AS entity_id, e.name AS entity_name, labels(e) AS labels
                    LIMIT 5
                    """
                    result = await session.run(
                        find_entity_query, 
                        user_id=user_id, 
                        entity_name=entity_name
                    )
                    
                    entity_ids = []
                    async for record in result:
                        entity_ids.append({
                            "id": record["entity_id"],
                            "name": record["entity_name"],
                            "labels": record["labels"]
                        })
                    
                    logger.info(f"Found {len(entity_ids)} entities for '{entity_name}'")
                    
                    if not entity_ids:
                        continue
                    
                    # 获取每个实体的关系
                    for entity_info in entity_ids:
                        entity_id = entity_info["id"]
                        entity_name_actual = entity_info["name"]
                        
                        # ========== 1-hop: 直接关系 ==========
                        # 出边
                        direct_out_query = """
                        MATCH (e {id: $entity_id, user_id: $user_id})-[r]->(target)
                        WHERE NOT target:User
                        RETURN e.name AS source_name, type(r) AS relation_type, 
                               target.name AS target_name, r.desc AS description,
                               coalesce(r.weight, 0.5) AS weight,
                               1 AS hop_distance
                        """
                        out_result = await session.run(
                            direct_out_query,
                            entity_id=entity_id,
                            user_id=user_id
                        )
                        
                        async for rec in out_result:
                            facts.append({
                                "entity": rec["source_name"],
                                "relation": rec["relation_type"],
                                "target": rec["target_name"],
                                "description": rec["description"],
                                "weight": rec["weight"],
                                "hop": 1,
                                "path_type": "direct"
                            })
                        
                        # 入边
                        direct_in_query = """
                        MATCH (source)-[r]->(e {id: $entity_id, user_id: $user_id})
                        WHERE NOT source:User
                        RETURN source.name AS source_name, type(r) AS relation_type,
                               e.name AS target_name, r.desc AS description,
                               coalesce(r.weight, 0.5) AS weight,
                               1 AS hop_distance
                        """
                        in_result = await session.run(
                            direct_in_query,
                            entity_id=entity_id,
                            user_id=user_id
                        )
                        
                        async for rec in in_result:
                            facts.append({
                                "entity": rec["source_name"],
                                "relation": rec["relation_type"],
                                "target": rec["target_name"],
                                "description": rec["description"],
                                "weight": rec["weight"],
                                "hop": 1,
                                "path_type": "direct"
                            })

                        user_to_entity_query = """
                        MATCH (u:User {id: $user_id})-[r]->(e {id: $entity_id, user_id: $user_id})
                        RETURN coalesce(u.name, '用户') AS source_name, type(r) AS relation_type,
                               e.name AS target_name, r.desc AS description,
                               coalesce(r.weight, 0.5) AS weight,
                               1 AS hop_distance
                        """
                        u_out = await session.run(
                            user_to_entity_query,
                            entity_id=entity_id,
                            user_id=user_id,
                        )
                        async for rec in u_out:
                            facts.append(
                                {
                                    "entity": rec["source_name"],
                                    "relation": rec["relation_type"],
                                    "target": rec["target_name"],
                                    "description": rec["description"],
                                    "weight": rec["weight"],
                                    "hop": 1,
                                    "path_type": "user",
                                }
                            )

                        entity_to_user_query = """
                        MATCH (e {id: $entity_id, user_id: $user_id})-[r]->(u:User {id: $user_id})
                        RETURN e.name AS source_name, type(r) AS relation_type,
                               coalesce(u.name, '用户') AS target_name, r.desc AS description,
                               coalesce(r.weight, 0.5) AS weight,
                               1 AS hop_distance
                        """
                        u_in = await session.run(
                            entity_to_user_query,
                            entity_id=entity_id,
                            user_id=user_id,
                        )
                        async for rec in u_in:
                            facts.append(
                                {
                                    "entity": rec["source_name"],
                                    "relation": rec["relation_type"],
                                    "target": rec["target_name"],
                                    "description": rec["description"],
                                    "weight": rec["weight"],
                                    "hop": 1,
                                    "path_type": "user",
                                }
                            )
                        
                        # ========== 2-hop: 间接关系 ==========
                        # 通过中间节点的路径: entity -> mid -> target
                        two_hop_query = """
                        MATCH (e {id: $entity_id, user_id: $user_id})-[r1]->(mid)-[r2]->(target)
                        WHERE NOT mid:User AND NOT target:User
                          AND mid.user_id = $user_id
                        RETURN e.name AS source_name, 
                               type(r1) AS rel1_type, mid.name AS mid_name,
                               type(r2) AS rel2_type, target.name AS target_name,
                               coalesce(r1.weight, 0.5) AS weight1,
                               coalesce(r2.weight, 0.5) AS weight2,
                               2 AS hop_distance
                        LIMIT 15
                        """
                        two_hop_result = await session.run(
                            two_hop_query,
                            entity_id=entity_id,
                            user_id=user_id
                        )
                        
                        async for rec in two_hop_result:
                            # 格式化 2-hop 路径为可读文本
                            path_desc = f"通过 {rec['mid_name']}"
                            facts.append({
                                "entity": rec["source_name"],
                                "relation": f"{rec['rel1_type']} -> {rec['mid_name']} -> {rec['rel2_type']}",
                                "target": rec["target_name"],
                                "description": path_desc,
                                "weight": rec["weight1"] * rec["weight2"],  # 路径权重相乘
                                "hop": 2,
                                "path_type": "indirect",
                                "via": rec["mid_name"],
                                "path": f"{rec['source_name']} -[{rec['rel1_type']}]-> {rec['mid_name']} -[{rec['rel2_type']}]-> {rec['target_name']}"
                            })
                        
                        # 反向 2-hop: target -> mid -> entity
                        two_hop_reverse_query = """
                        MATCH (source)-[r1]->(mid)-[r2]->(e {id: $entity_id, user_id: $user_id})
                        WHERE NOT source:User AND NOT mid:User
                          AND mid.user_id = $user_id
                        RETURN source.name AS source_name,
                               type(r1) AS rel1_type, mid.name AS mid_name,
                               type(r2) AS rel2_type, e.name AS target_name,
                               coalesce(r1.weight, 0.5) AS weight1,
                               coalesce(r2.weight, 0.5) AS weight2,
                               2 AS hop_distance
                        LIMIT 15
                        """
                        two_hop_rev_result = await session.run(
                            two_hop_reverse_query,
                            entity_id=entity_id,
                            user_id=user_id
                        )
                        
                        async for rec in two_hop_rev_result:
                            path_desc = f"通过 {rec['mid_name']}"
                            facts.append({
                                "entity": rec["source_name"],
                                "relation": f"{rec['rel1_type']} -> {rec['mid_name']} -> {rec['rel2_type']}",
                                "target": rec["target_name"],
                                "description": path_desc,
                                "weight": rec["weight1"] * rec["weight2"],
                                "hop": 2,
                                "path_type": "indirect",
                                "via": rec["mid_name"],
                                "path": f"{rec['source_name']} -[{rec['rel1_type']}]-> {rec['mid_name']} -[{rec['rel2_type']}]-> {rec['target_name']}"
                            })
                        
                        # ========== 3-hop: 三跳关系 ==========
                        # 路径: entity -> mid1 -> mid2 -> target
                        three_hop_query = """
                        MATCH (e {id: $entity_id, user_id: $user_id})-[r1]->(mid1)-[r2]->(mid2)-[r3]->(target)
                        WHERE NOT mid1:User AND NOT mid2:User AND NOT target:User
                          AND mid1.user_id = $user_id AND mid2.user_id = $user_id
                        RETURN e.name AS source_name,
                               type(r1) AS rel1_type, mid1.name AS mid1_name,
                               type(r2) AS rel2_type, mid2.name AS mid2_name,
                               type(r3) AS rel3_type, target.name AS target_name,
                               coalesce(r1.weight, 0.5) AS weight1,
                               coalesce(r2.weight, 0.5) AS weight2,
                               coalesce(r3.weight, 0.5) AS weight3,
                               3 AS hop_distance
                        LIMIT 10
                        """
                        three_hop_result = await session.run(
                            three_hop_query,
                            entity_id=entity_id,
                            user_id=user_id
                        )
                        
                        async for rec in three_hop_result:
                            path_desc = f"通过 {rec['mid1_name']} 和 {rec['mid2_name']}"
                            facts.append({
                                "entity": rec["source_name"],
                                "relation": f"{rec['rel1_type']} -> {rec['mid1_name']} -> {rec['rel2_type']} -> {rec['mid2_name']} -> {rec['rel3_type']}",
                                "target": rec["target_name"],
                                "description": path_desc,
                                "weight": rec["weight1"] * rec["weight2"] * rec["weight3"],
                                "hop": 3,
                                "path_type": "indirect",
                                "via": f"{rec['mid1_name']} -> {rec['mid2_name']}",
                                "path": f"{rec['source_name']} -[{rec['rel1_type']}]-> {rec['mid1_name']} -[{rec['rel2_type']}]-> {rec['mid2_name']} -[{rec['rel3_type']}]-> {rec['target_name']}"
                            })
                        
                        # 反向 3-hop: source -> mid1 -> mid2 -> entity
                        three_hop_reverse_query = """
                        MATCH (source)-[r1]->(mid1)-[r2]->(mid2)-[r3]->(e {id: $entity_id, user_id: $user_id})
                        WHERE NOT source:User AND NOT mid1:User AND NOT mid2:User
                          AND mid1.user_id = $user_id AND mid2.user_id = $user_id
                        RETURN source.name AS source_name,
                               type(r1) AS rel1_type, mid1.name AS mid1_name,
                               type(r2) AS rel2_type, mid2.name AS mid2_name,
                               type(r3) AS rel3_type, e.name AS target_name,
                               coalesce(r1.weight, 0.5) AS weight1,
                               coalesce(r2.weight, 0.5) AS weight2,
                               coalesce(r3.weight, 0.5) AS weight3,
                               3 AS hop_distance
                        LIMIT 10
                        """
                        three_hop_rev_result = await session.run(
                            three_hop_reverse_query,
                            entity_id=entity_id,
                            user_id=user_id
                        )
                        
                        async for rec in three_hop_rev_result:
                            path_desc = f"通过 {rec['mid1_name']} 和 {rec['mid2_name']}"
                            facts.append({
                                "entity": rec["source_name"],
                                "relation": f"{rec['rel1_type']} -> {rec['mid1_name']} -> {rec['rel2_type']} -> {rec['mid2_name']} -> {rec['rel3_type']}",
                                "target": rec["target_name"],
                                "description": path_desc,
                                "weight": rec["weight1"] * rec["weight2"] * rec["weight3"],
                                "hop": 3,
                                "path_type": "indirect",
                                "via": f"{rec['mid1_name']} -> {rec['mid2_name']}",
                                "path": f"{rec['source_name']} -[{rec['rel1_type']}]-> {rec['mid1_name']} -[{rec['rel2_type']}]-> {rec['mid2_name']} -[{rec['rel3_type']}]-> {rec['target_name']}"
                            })
            
            # 去重（基于 entity-relation-target）
            seen = set()
            unique_facts = []
            for fact in facts:
                key = (fact["entity"], fact["relation"], fact["target"])
                if key not in seen:
                    seen.add(key)
                    unique_facts.append(fact)
            
            # 如果没有找到事实，尝试语义扩展查询
            if not unique_facts and entity_names:
                logger.info(f"No direct facts found, trying semantic expansion for: {entity_names}")
                semantic_facts = await self._semantic_expand_query(
                    user_id, query, entity_names, neo4j
                )
                unique_facts.extend(semantic_facts)
            
            if date_constraints:
                event_facts = await self._retrieve_event_struct_facts(session, user_id, date_constraints)
                if event_facts:
                    unique_facts.extend(event_facts)

            # 按 hop 排序（直接关系优先）
            unique_facts.sort(key=lambda x: (x.get("hop", 1), -x.get("weight", 0)))
            
            logger.info(f"Retrieved {len(unique_facts)} facts (1-hop: {sum(1 for f in unique_facts if f.get('hop')==1)}, 2-hop: {sum(1 for f in unique_facts if f.get('hop')==2)}, 3-hop: {sum(1 for f in unique_facts if f.get('hop')==3)})")
            return unique_facts
            
        except Exception as e:
            logger.error(f"Entity facts retrieval failed: {e}", exc_info=True)
            return []

    async def _retrieve_event_struct_facts(
        self,
        session,
        user_id: str,
        constraints: List[Dict[str, Any]],
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        if not constraints:
            return []

        start = None
        end = None
        for c in constraints:
            if c.get("start") and c.get("end"):
                start = str(c["start"])
                end = str(c["end"])
                break

        if not start or not end:
            return []

        q = """
        MATCH (e:Event {user_id: $user_id})
        WHERE e.start_date >= $start_date AND e.start_date <= $end_date
        RETURN e.id AS id, e.name AS name,
               e.start_date AS start_date, e.end_date AS end_date,
               e.duration_seconds AS duration_seconds,
               e.cost_value AS cost_value, e.cost_unit AS cost_unit
        ORDER BY e.start_date DESC
        LIMIT $limit
        """
        res = await session.run(q, user_id=user_id, start_date=start, end_date=end, limit=int(limit))

        out: List[Dict[str, Any]] = []
        async for r in res:
            name = r.get("name") or r.get("id") or "event"
            sd = r.get("start_date")
            ed = r.get("end_date")
            if sd:
                out.append(
                    {
                        "entity": name,
                        "relation": "HAPPENED_AT",
                        "target": sd,
                        "description": "事件结构化字段",
                        "weight": 1.0,
                        "hop": 0,
                        "path_type": "event_struct",
                    }
                )
            if ed and ed != sd:
                out.append(
                    {
                        "entity": name,
                        "relation": "RELATED_TO",
                        "target": ed,
                        "description": "事件结构化字段",
                        "weight": 0.9,
                        "hop": 0,
                        "path_type": "event_struct",
                    }
                )
            dur = r.get("duration_seconds")
            if dur is not None:
                out.append(
                    {
                        "entity": name,
                        "relation": "LASTED",
                        "target": str(int(dur)),
                        "description": "事件结构化字段",
                        "weight": 0.95,
                        "hop": 0,
                        "path_type": "event_struct",
                    }
                )
            cv = r.get("cost_value")
            cu = r.get("cost_unit")
            if cv is not None and cu:
                out.append(
                    {
                        "entity": name,
                        "relation": "COST",
                        "target": f"{float(cv)} {cu}",
                        "description": "事件结构化字段",
                        "weight": 0.95,
                        "hop": 0,
                        "path_type": "event_struct",
                    }
                )

        return out
    
    async def _semantic_expand_query(
        self,
        user_id: str,
        query: str,
        semantic_concepts: List[str],
        neo4j_driver
    ) -> List[Dict[str, Any]]:
        """
        语义扩展查询 - 当直接实体匹配失败时，根据查询意图获取相关事实
        
        例如：
        - "谁住在海边" → 查询所有 LIVES_IN 关系，返回所有居住地信息
        - "谁喜欢运动" → 查询所有 LIKES 关系，返回所有爱好信息
        
        Args:
            user_id: 用户 ID
            query: 原始查询
            semantic_concepts: 语义概念列表（如 ["海边"]）
            neo4j_driver: Neo4j 驱动
        """
        facts = []
        
        # 根据查询意图确定要查询的关系类型
        relation_mapping = {
            "住": ["LIVES_IN", "LOCATED_IN", "FROM"],
            "来自": ["FROM", "LIVES_IN", "BORN_IN"],
            "喜欢": ["LIKES", "LOVES", "PREFERS"],
            "讨厌": ["DISLIKES", "HATES"],
            "工作": ["WORKS_AT", "EMPLOYED_BY"],
            "认识": ["KNOWS", "FRIEND_OF", "RELATED_TO"],
            "是": ["IS_A", "WORKS_AS", "RELATED_TO"],
            "时间": ["HAPPENED_AT", "RELATED_TO"],
            "哪天": ["HAPPENED_AT", "RELATED_TO"],
            "什么时候": ["HAPPENED_AT", "RELATED_TO"],
            "多久": ["LASTED", "RELATED_TO"],
            "多长": ["LASTED", "RELATED_TO"],
            "花费": ["COST", "RELATED_TO"],
            "花了": ["COST", "RELATED_TO"],
        }
        
        # 从查询中识别意图
        target_relations = []
        for keyword, relations in relation_mapping.items():
            if keyword in query:
                target_relations.extend(relations)
        
        # 如果没有识别到特定意图，查询所有关系
        if not target_relations:
            target_relations = ["LIVES_IN", "LIKES", "DISLIKES", "WORKS_AT", "FROM", "KNOWS"]
        
        target_relations = list(set(target_relations))
        logger.info(f"Semantic expansion: concepts={semantic_concepts}, relations={target_relations}")
        
        try:
            async with neo4j_driver.session() as session:
                # 查询所有匹配关系类型的事实
                for rel_type in target_relations:
                    # 查询所有该类型的关系
                    semantic_query = """
                    MATCH (source)-[r]->(target)
                    WHERE source.user_id = $user_id 
                      AND type(r) = $rel_type
                      AND NOT source:User AND NOT target:User
                    RETURN source.name AS source_name, 
                           type(r) AS relation_type,
                           target.name AS target_name,
                           r.desc AS description,
                           coalesce(r.weight, 0.5) AS weight
                    LIMIT 20
                    """
                    result = await session.run(
                        semantic_query,
                        user_id=user_id,
                        rel_type=rel_type
                    )
                    
                    async for rec in result:
                        facts.append({
                            "entity": rec["source_name"],
                            "relation": rec["relation_type"],
                            "target": rec["target_name"],
                            "description": rec["description"],
                            "weight": rec["weight"],
                            "hop": 1,
                            "path_type": "semantic_expansion",
                            "semantic_context": f"查询概念: {', '.join(semantic_concepts)}"
                        })
            
            logger.info(f"Semantic expansion found {len(facts)} facts")
            
        except Exception as e:
            logger.error(f"Semantic expansion failed: {e}", exc_info=True)
        
        return facts
    
    async def _extract_query_entities(self, query: str) -> List[str]:
        """
        用 LLM 从查询中提取实体名称，支持语义扩展
        
        Args:
            query: 用户查询文本
            
        Returns:
            实体名称列表
        """
        try:
            # 使用轻量级 prompt 提取实体，支持语义概念
            response = await self.embedding_service.client.chat.completions.create(
                model="deepseek-ai/DeepSeek-V3",
                messages=[
                    {
                        "role": "system",
                        "content": """你是一个实体识别器。从用户的问题中提取被询问的实体名称。

规则：
1. 提取问题中明确提到的人名、地名、事物名
2. 返回 JSON 数组格式，如 ["二丫", "足球"]
3. 如果没有明确实体，返回空数组 []
4. 不要添加问题中没有的实体
5. 对于语义概念查询（如"海边"、"南方"），也提取这些概念词

示例：
- "二丫喜欢什么" → ["二丫"]
- "昊哥和二丫是什么关系" → ["昊哥", "二丫"]
- "谁住在海边" → ["海边"]
- "谁来自南方" → ["南方"]
- "今天天气怎么样" → []
- "你好" → []"""
                    },
                    {
                        "role": "user",
                        "content": f"问题：{query}\n\n请提取实体名称（JSON数组）："
                    }
                ],
                temperature=0.0,
                max_tokens=100
            )
            
            content = response.choices[0].message.content.strip()
            
            # 处理 markdown 代码块
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                content = "\n".join(lines)
            
            entities = json.loads(content)
            
            if isinstance(entities, list):
                return [str(e) for e in entities if e]
            return []
            
        except Exception as e:
            logger.warning(f"Entity extraction from query failed: {e}")
            # 简单回退：提取中文/英文实体模式
            import re
            # 匹配常见人名模式（2-4个汉字 + 可选的称呼后缀）
            patterns = [
                r'([二三四五六七八九十]丫)',  # 二丫、三丫等
                r'([\u4e00-\u9fa5]{1,2}[哥姐弟妹叔婶])',  # 昊哥、小妹等
                r'([\u4e00-\u9fa5]{2,4}(?=喜欢|讨厌|是|来自|住在|工作))',  # 名字+动词
                r'\b([A-Z][a-z]{1,20})\b',  # Caroline, Jon, Gina
            ]
            entities = []
            for pattern in patterns:
                matches = re.findall(pattern, query)
                entities.extend(matches)
            out = []
            seen = set()
            for x in entities:
                s = str(x).strip()
                if not s:
                    continue
                key = s.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(s)
            return out
