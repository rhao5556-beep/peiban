"""
内容推荐服务 - 核心推荐逻辑

功能：
1. 用户兴趣提取（从 Neo4j 图谱）
2. 推荐算法（相似度 + 时效性 + 质量）
3. 多样性控制
4. 推荐生成与保存

设计原则：
- 只向 friend+ 状态用户推荐
- 默认关闭，需用户明确启用
- 每日限额控制
- 质量优于数量
"""
import logging
import math
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval_service import EmbeddingService
from app.services.affinity_service_v2 import AffinityServiceV2

logger = logging.getLogger(__name__)


# ==================== 数据类 ====================

@dataclass
class Interest:
    """用户兴趣"""
    name: str
    weight: float
    entity_type: str
    mention_count: int = 0
    
    def __repr__(self):
        return f"Interest(name={self.name}, weight={self.weight:.2f})"


@dataclass
class Content:
    """推荐内容"""
    id: str
    source: str
    title: str
    summary: Optional[str]
    content_url: str
    tags: List[str]
    embedding: List[float]
    published_at: datetime
    quality_score: float
    
    def __repr__(self):
        return f"Content(title={self.title[:30]}..., source={self.source})"


@dataclass
class RecommendedContent:
    """推荐结果"""
    content: Content
    match_score: float
    rank_position: int
    
    def __repr__(self):
        return f"Recommended(title={self.content.title[:30]}..., score={self.match_score:.3f})"


# ==================== 推荐服务 ====================

class ContentRecommendationService:
    """
    内容推荐服务
    
    核心流程：
    1. 检查用户资格（好感度、偏好、限额）
    2. 提取用户兴趣（Neo4j）
    3. 获取候选内容（PostgreSQL）
    4. 计算推荐分数
    5. 应用多样性控制
    6. 保存推荐记录
    """
    
    # 算法参数
    SIMILARITY_VECTOR_WEIGHT = 0.7  # 向量相似度权重
    SIMILARITY_KEYWORD_WEIGHT = 0.3  # 关键词匹配权重
    
    SCORE_SIMILARITY_WEIGHT = 0.5   # 相似度权重 50%
    SCORE_RECENCY_WEIGHT = 0.3      # 时效性权重 30%
    SCORE_QUALITY_WEIGHT = 0.2      # 质量权重 20%
    
    RECENCY_DECAY_RATE = 0.05       # 时效性衰减率（半衰期约14小时）
    
    def __init__(self, db: AsyncSession, neo4j_driver=None):
        self.db = db
        self.neo4j = neo4j_driver
        self.embedding_service = EmbeddingService()
        self.affinity_service = AffinityServiceV2()
    
    # ==================== 主入口 ====================
    
    async def generate_recommendations(
        self,
        user_id: str,
        top_k: int = 3
    ) -> List[RecommendedContent]:
        """
        为用户生成推荐
        
        Args:
            user_id: 用户 ID
            top_k: 返回数量
            
        Returns:
            List[RecommendedContent]: 推荐列表
        """
        logger.info(f"Generating recommendations for user {user_id}")
        
        # 1. 检查用户偏好
        preference = await self._get_user_preference(user_id)
        if not preference or not preference.get("content_recommendation_enabled"):
            logger.info(f"User {user_id} has not enabled recommendations")
            return []
        
        # 2. 检查好感度门槛（friend+）
        affinity = await self.affinity_service.get_current_affinity(user_id)
        if affinity.state not in ["friend", "close_friend"]:
            logger.info(f"User {user_id} affinity state {affinity.state} below threshold")
            return []
        
        # 3. 检查每日限额
        if await self._exceeded_daily_limit(user_id, preference):
            logger.info(f"User {user_id} exceeded daily recommendation limit")
            return []
        
        # 4. 提取用户兴趣
        interests = await self.extract_user_interests(user_id)
        if not interests:
            logger.info(f"User {user_id} has no interests, using defaults")
            interests = self._get_default_interests()
        
        logger.info(f"User {user_id} interests: {[i.name for i in interests[:5]]}")
        
        # 5. 获取候选内容（最近24小时）
        candidates = await self._get_candidate_contents(
            since=datetime.now() - timedelta(hours=24),
            sources=preference.get("preferred_sources")
        )
        
        if not candidates:
            logger.warning(f"No candidate contents available for user {user_id}")
            return []
        
        logger.info(f"Found {len(candidates)} candidate contents")
        
        # 6. 计算推荐分数
        scored_contents = []
        history = await self._get_recommendation_history(user_id, days=30)
        
        for content in candidates:
            score = await self._calculate_recommendation_score(
                content, interests, history
            )
            scored_contents.append((content, score))
        
        # 7. 应用多样性控制
        recommendations = self._ensure_diversity(scored_contents, top_k)
        
        logger.info(f"Generated {len(recommendations)} recommendations for user {user_id}")
        
        # 8. 保存推荐记录
        await self._save_recommendations(user_id, recommendations)
        
        return recommendations
    
    # ==================== 用户兴趣提取 ====================
    
    async def extract_user_interests(
        self,
        user_id: str,
        min_weight: float = 0.5,
        days: int = 30,
        min_count: int = 3,
        max_count: int = 10
    ) -> List[Interest]:
        """
        从 Neo4j 提取用户兴趣
        
        Args:
            user_id: 用户 ID
            min_weight: 最小权重阈值
            days: 时间范围（天）
            min_count: 最少返回数量
            max_count: 最多返回数量
            
        Returns:
            List[Interest]: 兴趣列表（3-10个）
        """
        if not self.neo4j:
            logger.warning("Neo4j driver not available, using default interests")
            return self._get_default_interests()
        
        try:
            async with self.neo4j.session() as session:
                # 查询用户兴趣（使用 updated_at 字段，与现有图谱一致）
                query = """
                MATCH (u:User {id: $user_id})-[r:LIKES|RELATED_TO|WORKS_AT|STUDIES_AT]->(e:Entity)
                WHERE r.weight > $min_weight 
                  AND r.updated_at > datetime() - duration({days: $days})
                RETURN e.name AS interest, 
                       r.weight AS weight,
                       coalesce(r.mention_count, 0) AS mention_count,
                       labels(e) AS entity_type
                ORDER BY r.weight DESC, mention_count DESC
                LIMIT $max_count
                """
                
                result = await session.run(
                    query,
                    user_id=user_id,
                    min_weight=min_weight,
                    days=days,
                    max_count=max_count
                )
                
                interests = []
                async for record in result:
                    interests.append(Interest(
                        name=record["interest"],
                        weight=record["weight"],
                        entity_type=record["entity_type"][0] if record["entity_type"] else "Entity",
                        mention_count=record["mention_count"]
                    ))
                
                # 确保返回 3-10 个兴趣
                if len(interests) < min_count:
                    logger.info(f"User {user_id} has only {len(interests)} interests, adding defaults")
                    defaults = self._get_default_interests()
                    interests.extend(defaults[:min_count - len(interests)])
                
                return interests[:max_count]
                
        except Exception as e:
            logger.error(f"Failed to extract user interests: {e}")
            return self._get_default_interests()
    
    def _get_default_interests(self) -> List[Interest]:
        """
        获取默认兴趣（当用户无兴趣时）
        
        Returns:
            List[Interest]: 默认兴趣列表
        """
        return [
            Interest(name="科技", weight=0.7, entity_type="Topic"),
            Interest(name="生活", weight=0.6, entity_type="Topic"),
            Interest(name="新闻", weight=0.5, entity_type="Topic"),
        ]
    
    # ==================== 推荐算法 ====================
    
    async def _calculate_recommendation_score(
        self,
        content: Content,
        user_interests: List[Interest],
        history: List[Dict]
    ) -> float:
        """
        计算推荐分数
        
        分数 = 相似度 × 50% + 时效性 × 30% + 质量 × 20% - 重复惩罚
        
        Args:
            content: 内容
            user_interests: 用户兴趣
            history: 推荐历史
            
        Returns:
            float: 推荐分数 (0-1)
        """
        # 1. 相似度分数 (0-1)
        similarity = await self._calculate_similarity(content, user_interests)
        
        # 2. 时效性衰减 (0-1)
        if content.published_at:
            hours_since_publish = (datetime.now() - content.published_at).total_seconds() / 3600
            recency = math.exp(-self.RECENCY_DECAY_RATE * hours_since_publish)
        else:
            recency = 0.5  # 无发布时间，给中等分数
        
        # 3. 质量分数 (0-1)
        quality = content.quality_score
        
        # 4. 重复惩罚
        recent_content_ids = {h["content_id"] for h in history[-30:]}
        repeat_penalty = 0.3 if content.id in recent_content_ids else 1.0
        
        # 综合分数
        score = (
            self.SCORE_SIMILARITY_WEIGHT * similarity +
            self.SCORE_RECENCY_WEIGHT * recency +
            self.SCORE_QUALITY_WEIGHT * quality
        ) * repeat_penalty
        
        return max(0.0, min(1.0, score))  # 限制在 [0, 1]
    
    async def _calculate_similarity(
        self,
        content: Content,
        user_interests: List[Interest]
    ) -> float:
        """
        计算相似度
        
        混合相似度 = 向量相似度 × 70% + 关键词匹配 × 30%
        
        Args:
            content: 内容
            user_interests: 用户兴趣
            
        Returns:
            float: 相似度分数 (0-1)
        """
        # 1. 向量相似度
        if content.embedding and user_interests:
            # 计算用户兴趣的平均嵌入（加权）
            interest_texts = [i.name for i in user_interests]
            interest_weights = [i.weight for i in user_interests]
            
            # 为每个兴趣生成嵌入
            interest_embeddings = []
            for text in interest_texts:
                emb = await self.embedding_service.encode(text)
                interest_embeddings.append(emb)
            
            # 加权平均
            weighted_embedding = np.average(
                interest_embeddings,
                weights=interest_weights,
                axis=0
            )
            
            # 余弦相似度
            content_vec = np.array(content.embedding)
            interest_vec = np.array(weighted_embedding)
            
            dot_product = np.dot(content_vec, interest_vec)
            norm_product = np.linalg.norm(content_vec) * np.linalg.norm(interest_vec)
            
            vector_sim = dot_product / norm_product if norm_product > 0 else 0.0
            vector_sim = max(0.0, min(1.0, vector_sim))  # 限制在 [0, 1]
        else:
            vector_sim = 0.0
        
        # 2. 关键词匹配
        content_keywords = set(content.tags)
        interest_keywords = set([i.name for i in user_interests])
        
        if content_keywords and interest_keywords:
            keyword_overlap = len(content_keywords & interest_keywords)
            keyword_sim = min(keyword_overlap / 3.0, 1.0)  # 最多3个匹配即满分
        else:
            keyword_sim = 0.0
        
        # 混合
        similarity = (
            self.SIMILARITY_VECTOR_WEIGHT * vector_sim +
            self.SIMILARITY_KEYWORD_WEIGHT * keyword_sim
        )
        
        return similarity
    
    def _ensure_diversity(
        self,
        candidates: List[Tuple[Content, float]],
        top_k: int = 3
    ) -> List[RecommendedContent]:
        """
        确保推荐结果的多样性
        
        规则：
        - 同一来源最多 1 条
        - 同一话题最多 2 条
        
        Args:
            candidates: 候选内容及分数列表
            top_k: 返回数量
            
        Returns:
            List[RecommendedContent]: 多样化的推荐列表
        """
        selected = []
        source_count = {}
        topic_count = {}
        
        # 按分数降序排序
        sorted_candidates = sorted(candidates, key=lambda x: x[1], reverse=True)
        
        for content, score in sorted_candidates:
            # 检查来源多样性
            if source_count.get(content.source, 0) >= 1:
                continue
            
            # 检查话题多样性
            main_topic = content.tags[0] if content.tags else "general"
            if topic_count.get(main_topic, 0) >= 2:
                continue
            
            # 添加到结果
            selected.append(RecommendedContent(
                content=content,
                match_score=score,
                rank_position=len(selected) + 1
            ))
            
            # 更新计数
            source_count[content.source] = source_count.get(content.source, 0) + 1
            topic_count[main_topic] = topic_count.get(main_topic, 0) + 1
            
            if len(selected) >= top_k:
                break
        
        return selected
    
    # ==================== 数据库操作 ====================
    
    async def _get_user_preference(self, user_id: str) -> Optional[Dict]:
        """获取用户偏好"""
        try:
            result = await self.db.execute(
                text("""
                    SELECT content_recommendation_enabled, preferred_sources,
                           max_daily_recommendations, quiet_hours_start, quiet_hours_end
                    FROM user_content_preference
                    WHERE user_id = :user_id
                """),
                {"user_id": user_id}
            )
            
            row = result.fetchone()
            if row:
                return {
                    "content_recommendation_enabled": row[0],
                    "preferred_sources": row[1],
                    "max_daily_recommendations": row[2],
                    "quiet_hours_start": row[3],
                    "quiet_hours_end": row[4],
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user preference: {e}")
            return None
    
    async def _exceeded_daily_limit(
        self,
        user_id: str,
        preference: Dict
    ) -> bool:
        """检查是否超过每日限额"""
        try:
            max_daily = preference.get("max_daily_recommendations", 1)
            
            result = await self.db.execute(
                text("""
                    SELECT COUNT(*) FROM recommendation_history
                    WHERE user_id = :user_id
                      AND DATE(recommended_at) = CURRENT_DATE
                """),
                {"user_id": user_id}
            )
            
            count = result.scalar_one()
            return count >= max_daily
            
        except Exception as e:
            logger.error(f"Failed to check daily limit: {e}")
            return True  # 出错时保守处理
    
    async def _get_candidate_contents(
        self,
        since: datetime,
        sources: Optional[List[str]] = None
    ) -> List[Content]:
        """获取候选内容"""
        try:
            # 构建查询
            query = """
                SELECT id, source, title, summary, content_url, tags,
                       embedding, published_at, quality_score
                FROM content_library
                WHERE fetched_at > :since
                  AND is_active = TRUE
            """
            
            params = {"since": since}
            
            if sources:
                query += " AND source = ANY(:sources)"
                params["sources"] = sources
            
            query += " ORDER BY quality_score DESC, published_at DESC LIMIT 100"
            
            result = await self.db.execute(text(query), params)
            
            contents = []
            for row in result.fetchall():
                contents.append(Content(
                    id=str(row[0]),
                    source=row[1],
                    title=row[2],
                    summary=row[3],
                    content_url=row[4],
                    tags=row[5] or [],
                    embedding=row[6] or [],
                    published_at=row[7],
                    quality_score=row[8]
                ))
            
            return contents
            
        except Exception as e:
            logger.error(f"Failed to get candidate contents: {e}")
            return []
    
    async def _get_recommendation_history(
        self,
        user_id: str,
        days: int = 30
    ) -> List[Dict]:
        """获取推荐历史"""
        try:
            result = await self.db.execute(
                text("""
                    SELECT content_id, recommended_at
                    FROM recommendation_history
                    WHERE user_id = :user_id
                      AND recommended_at > NOW() - INTERVAL :days DAY
                    ORDER BY recommended_at DESC
                """),
                {"user_id": user_id, "days": f"{days} days"}
            )
            
            history = []
            for row in result.fetchall():
                history.append({
                    "content_id": str(row[0]),
                    "recommended_at": row[1]
                })
            
            return history
            
        except Exception as e:
            logger.error(f"Failed to get recommendation history: {e}")
            return []
    
    async def _save_recommendations(
        self,
        user_id: str,
        recommendations: List[RecommendedContent]
    ) -> bool:
        """保存推荐记录"""
        try:
            for rec in recommendations:
                await self.db.execute(
                    text("""
                        INSERT INTO recommendation_history (
                            user_id, content_id, match_score, rank_position
                        ) VALUES (
                            :user_id, :content_id, :match_score, :rank_position
                        )
                    """),
                    {
                        "user_id": user_id,
                        "content_id": rec.content.id,
                        "match_score": rec.match_score,
                        "rank_position": rec.rank_position
                    }
                )
            
            await self.db.commit()
            logger.info(f"Saved {len(recommendations)} recommendations for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save recommendations: {e}")
            await self.db.rollback()
            return False
