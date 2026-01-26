"""记忆管理器 - 统一协调所有记忆层"""
import logging
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from app.services.working_memory_service import WorkingMemoryService, EntityMention
from app.services.context_memory_service import ContextMemoryService, SessionSummary
from app.services.episodic_memory_service import EpisodicMemoryService, Episode
from app.services.retrieval_service import RetrievalService, Memory
from app.services.user_profile_service import UserProfileService, UserProfile
from app.core.database import get_redis_client, get_neo4j_driver

logger = logging.getLogger(__name__)


@dataclass
class UnifiedContext:
    """统一上下文 - 合并所有记忆层的检索结果"""
    # 工作记忆（当前会话）
    recent_entities: List[EntityMention] = field(default_factory=list)
    resolved_references: Dict[str, str] = field(default_factory=dict)
    
    # 上下文记忆（跨会话）
    relevant_contexts: List[SessionSummary] = field(default_factory=list)
    
    # 情景记忆（事件时间线）
    relevant_episodes: List[Episode] = field(default_factory=list)
    
    # 长期记忆（向量 + 图谱）
    vector_memories: List[Memory] = field(default_factory=list)
    graph_facts: List[Dict[str, Any]] = field(default_factory=list)
    
    # 用户画像
    user_profile: Optional[UserProfile] = None
    
    # 元数据
    retrieval_time_ms: float = 0.0
    sources: Dict[str, int] = field(default_factory=dict)
    
    def to_prompt_context(self) -> str:
        """转换为 Prompt 上下文字符串"""
        sections = []
        
        # 工作记忆
        if self.recent_entities:
            entity_lines = [f"- {e.name} ({e.entity_type})" for e in self.recent_entities[:5]]
            sections.append(f"【当前会话实体】\n" + "\n".join(entity_lines))
        
        # 上下文记忆
        if self.relevant_contexts:
            context_lines = []
            for ctx in self.relevant_contexts[:3]:
                topics = ", ".join(ctx.main_topics[:3]) if ctx.main_topics else "无"
                context_lines.append(f"- 会话主题: {topics}")
                if ctx.unfinished_threads:
                    context_lines.append(f"  未完成话题: {', '.join(ctx.unfinished_threads[:2])}")
            sections.append(f"【历史上下文】\n" + "\n".join(context_lines))
        
        # 情景记忆
        if self.relevant_episodes:
            episode_lines = []
            for ep in self.relevant_episodes[:3]:
                date_str = ep.timestamp.strftime("%Y-%m-%d") if ep.timestamp else "未知"
                episode_lines.append(f"- [{date_str}] {ep.event_type}: {ep.description[:50]}")
            sections.append(f"【相关事件】\n" + "\n".join(episode_lines))
        
        # 长期记忆 - 图谱事实
        if self.graph_facts:
            direct_facts = [f for f in self.graph_facts if f.get("hop", 1) == 1]
            indirect_facts = [f for f in self.graph_facts if f.get("hop", 1) > 1]
            
            fact_lines = []
            if direct_facts:
                fact_lines.append("直接关系:")
                for f in direct_facts[:10]:
                    fact_lines.append(f"  - {f['entity']} {f['relation']} {f['target']}")
            if indirect_facts:
                fact_lines.append("间接关系:")
                for f in indirect_facts[:5]:
                    path = f.get("path", f"{f['entity']} -> {f['target']}")
                    fact_lines.append(f"  - [{f.get('hop', 2)}-hop] {path}")
            
            sections.append(f"【图谱知识】\n" + "\n".join(fact_lines))
        
        # 长期记忆 - 向量检索
        if self.vector_memories:
            memory_lines = [
                f"- {m.content[:80]}..." if len(m.content) > 80 else f"- {m.content}"
                for m in self.vector_memories[:5]
            ]
            sections.append(f"【相关记忆】\n" + "\n".join(memory_lines))
        
        # 用户画像摘要
        if self.user_profile:
            profile_lines = []
            if self.user_profile.personality.confidence > 0.3:
                p = self.user_profile.personality
                traits = []
                if p.optimist_pessimist > 0.3:
                    traits.append("乐观")
                elif p.optimist_pessimist < -0.3:
                    traits.append("悲观")
                if p.introvert_extrovert > 0.3:
                    traits.append("外向")
                elif p.introvert_extrovert < -0.3:
                    traits.append("内向")
                if traits:
                    profile_lines.append(f"性格: {', '.join(traits)}")
            
            if self.user_profile.interests:
                likes = [i.name for i in self.user_profile.interests if i.sentiment == "like"][:3]
                if likes:
                    profile_lines.append(f"喜好: {', '.join(likes)}")
            
            if profile_lines:
                sections.append(f"【用户画像】\n" + "\n".join(profile_lines))
        
        return "\n\n".join(sections) if sections else "（无相关上下文）"


@dataclass
class MemoryInput:
    """记忆输入"""
    content: str
    memory_type: str  # working, context, episodic, long_term
    entities: List[EntityMention] = field(default_factory=list)
    episode: Optional[Episode] = None
    session_summary: Optional[SessionSummary] = None
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryManager:
    """
    记忆管理器 - 统一协调所有记忆层
    
    Property 18: Memory Layer Consistency
    - 确保跨存储的数据一致性
    - 统一检索接口
    """
    
    def __init__(
        self,
        working_memory: WorkingMemoryService = None,
        context_memory: ContextMemoryService = None,
        episodic_memory: EpisodicMemoryService = None,
        long_term_memory: RetrievalService = None,
        user_profile: UserProfileService = None
    ):
        # 懒加载服务
        self._working_memory = working_memory
        self._context_memory = context_memory
        self._episodic_memory = episodic_memory
        self._long_term_memory = long_term_memory
        self._user_profile = user_profile
    
    @property
    def working_memory(self) -> WorkingMemoryService:
        if self._working_memory is None:
            redis_client = get_redis_client()
            self._working_memory = WorkingMemoryService(redis_client=redis_client)
        return self._working_memory
    
    @property
    def context_memory(self) -> ContextMemoryService:
        if self._context_memory is None:
            self._context_memory = ContextMemoryService()
        return self._context_memory
    
    @property
    def episodic_memory(self) -> EpisodicMemoryService:
        if self._episodic_memory is None:
            neo4j_driver = get_neo4j_driver()
            self._episodic_memory = EpisodicMemoryService(neo4j_driver=neo4j_driver)
        return self._episodic_memory
    
    @property
    def long_term_memory(self) -> RetrievalService:
        if self._long_term_memory is None:
            self._long_term_memory = RetrievalService()
        return self._long_term_memory
    
    @property
    def user_profile_service(self) -> UserProfileService:
        if self._user_profile is None:
            self._user_profile = UserProfileService()
        return self._user_profile
    
    async def retrieve_unified_context(
        self,
        user_id: str,
        session_id: str,
        query: str,
        affinity_score: float,
        include_profile: bool = True,
        graph_service=None
    ) -> UnifiedContext:
        """
        统一检索所有记忆层
        
        并行检索各层记忆，合并为统一上下文
        
        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            query: 查询文本
            affinity_score: 好感度分数
            include_profile: 是否包含用户画像
            graph_service: 图谱服务（用于事实检索）
            
        Returns:
            UnifiedContext: 统一上下文
        """
        start_time = datetime.now()
        context = UnifiedContext()
        
        # 创建并行任务
        tasks = []
        
        # 1. 工作记忆 - 获取最近实体
        tasks.append(self._get_working_memory_context(session_id))
        
        # 2. 上下文记忆 - 获取相关历史上下文
        tasks.append(self._get_context_memory(user_id, query))
        
        # 3. 情景记忆 - 获取相关事件
        tasks.append(self._get_episodic_memory(user_id, query))
        
        # 4. 长期记忆 - 向量检索
        tasks.append(self._get_vector_memories(user_id, query, affinity_score))
        
        # 5. 长期记忆 - 图谱事实
        if graph_service:
            tasks.append(self._get_graph_facts(user_id, query, graph_service))
        else:
            tasks.append(asyncio.coroutine(lambda: [])())
        
        # 6. 用户画像
        if include_profile:
            tasks.append(self._get_user_profile(user_id))
        else:
            tasks.append(asyncio.coroutine(lambda: None)())
        
        # 并行执行
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            if not isinstance(results[0], Exception):
                context.recent_entities = results[0] or []
                context.sources["working_memory"] = len(context.recent_entities)
            
            if not isinstance(results[1], Exception):
                context.relevant_contexts = results[1] or []
                context.sources["context_memory"] = len(context.relevant_contexts)
            
            if not isinstance(results[2], Exception):
                context.relevant_episodes = results[2] or []
                context.sources["episodic_memory"] = len(context.relevant_episodes)
            
            if not isinstance(results[3], Exception):
                context.vector_memories = results[3] or []
                context.sources["vector_memory"] = len(context.vector_memories)
            
            if not isinstance(results[4], Exception):
                context.graph_facts = results[4] or []
                context.sources["graph_facts"] = len(context.graph_facts)
            
            if not isinstance(results[5], Exception):
                context.user_profile = results[5]
                context.sources["user_profile"] = 1 if results[5] else 0
                
        except Exception as e:
            logger.error(f"Failed to retrieve unified context: {e}")
        
        context.retrieval_time_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.info(
            f"Unified context retrieved in {context.retrieval_time_ms:.2f}ms: "
            f"working={context.sources.get('working_memory', 0)}, "
            f"context={context.sources.get('context_memory', 0)}, "
            f"episodic={context.sources.get('episodic_memory', 0)}, "
            f"vector={context.sources.get('vector_memory', 0)}, "
            f"graph={context.sources.get('graph_facts', 0)}"
        )
        
        return context

    async def _get_working_memory_context(
        self,
        session_id: str
    ) -> List[EntityMention]:
        """获取工作记忆上下文"""
        try:
            return await self.working_memory.get_recent_entities(session_id, limit=10)
        except Exception as e:
            logger.warning(f"Failed to get working memory: {e}")
            return []
    
    async def _get_context_memory(
        self,
        user_id: str,
        query: str
    ) -> List[SessionSummary]:
        """获取上下文记忆"""
        try:
            return await self.context_memory.retrieve_relevant_context(
                user_id, query, session_limit=3
            )
        except Exception as e:
            logger.warning(f"Failed to get context memory: {e}")
            return []
    
    async def _get_episodic_memory(
        self,
        user_id: str,
        query: str
    ) -> List[Episode]:
        """获取情景记忆"""
        try:
            # 检测时间相关查询
            from datetime import timedelta
            
            # 简单的时间关键词检测
            time_keywords = {
                "昨天": timedelta(days=1),
                "前天": timedelta(days=2),
                "上周": timedelta(days=7),
                "上个月": timedelta(days=30),
                "去年": timedelta(days=365),
            }
            
            for keyword, delta in time_keywords.items():
                if keyword in query:
                    end_time = datetime.now()
                    start_time = end_time - delta
                    return await self.episodic_memory.query_by_time_range(
                        user_id, start_time, end_time
                    )
            
            # 默认返回最近的事件
            end_time = datetime.now()
            start_time = end_time - timedelta(days=30)
            episodes = await self.episodic_memory.query_by_time_range(
                user_id, start_time, end_time
            )
            return episodes[:5]  # 限制数量
            
        except Exception as e:
            logger.warning(f"Failed to get episodic memory: {e}")
            return []
    
    async def _get_vector_memories(
        self,
        user_id: str,
        query: str,
        affinity_score: float
    ) -> List[Memory]:
        """获取向量检索结果"""
        try:
            result = await self.long_term_memory.hybrid_retrieve(
                user_id, query, affinity_score, top_k=10
            )
            return result.memories
        except Exception as e:
            logger.warning(f"Failed to get vector memories: {e}")
            return []
    
    async def _get_graph_facts(
        self,
        user_id: str,
        query: str,
        graph_service
    ) -> List[Dict[str, Any]]:
        """获取图谱事实"""
        try:
            return await self.long_term_memory.retrieve_entity_facts(
                user_id, query, graph_service
            )
        except Exception as e:
            logger.warning(f"Failed to get graph facts: {e}")
            return []
    
    async def _get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """获取用户画像"""
        try:
            return await self.user_profile_service.get_profile(user_id)
        except Exception as e:
            logger.warning(f"Failed to get user profile: {e}")
            return None
    
    async def store_memory(
        self,
        user_id: str,
        session_id: str,
        memory: MemoryInput
    ) -> None:
        """
        存储记忆到适当的层
        
        根据 memory_type 路由到对应的存储
        """
        try:
            if memory.memory_type == "working":
                # 存储到工作记忆
                for entity in memory.entities:
                    await self.working_memory.store_entity(session_id, entity)
                    
            elif memory.memory_type == "context":
                # 存储到上下文记忆
                if memory.session_summary:
                    await self.context_memory.store_context(
                        user_id, session_id, memory.session_summary
                    )
                    
            elif memory.memory_type == "episodic":
                # 存储到情景记忆
                if memory.episode:
                    await self.episodic_memory.store_episode(user_id, memory.episode)
                    
            elif memory.memory_type == "long_term":
                # 长期记忆通过 Outbox 模式异步写入
                # 这里只记录日志，实际写入由 Celery worker 处理
                logger.info(f"Long-term memory will be stored via Outbox: {memory.content[:50]}")
                
            else:
                logger.warning(f"Unknown memory type: {memory.memory_type}")
                
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
    
    async def clear_session_memory(self, session_id: str) -> None:
        """清除会话的工作记忆"""
        try:
            await self.working_memory.clear_session(session_id)
            logger.info(f"Cleared working memory for session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to clear session memory: {e}")
    
    async def get_memory_stats(self, user_id: str, session_id: str) -> Dict[str, Any]:
        """获取记忆统计信息"""
        stats = {
            "user_id": user_id,
            "session_id": session_id,
            "layers": {}
        }
        
        try:
            # 工作记忆统计
            recent_entities = await self.working_memory.get_recent_entities(session_id)
            stats["layers"]["working_memory"] = {
                "entity_count": len(recent_entities)
            }
            
            # 上下文记忆统计（简化）
            stats["layers"]["context_memory"] = {
                "available": True
            }
            
            # 情景记忆统计（简化）
            stats["layers"]["episodic_memory"] = {
                "available": True
            }
            
            # 用户画像统计
            profile = await self.user_profile_service.get_profile(user_id)
            stats["layers"]["user_profile"] = {
                "exists": profile is not None,
                "staleness_days": profile.staleness_days if profile else None,
                "is_stale": profile.is_stale if profile else None
            }
            
        except Exception as e:
            logger.warning(f"Failed to get memory stats: {e}")
            stats["error"] = str(e)
        
        return stats
