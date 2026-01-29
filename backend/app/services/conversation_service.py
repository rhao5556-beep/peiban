"""对话服务 - 协调整个对话流程"""
import uuid
import logging
from typing import AsyncIterator, Optional, List
from dataclasses import dataclass
from datetime import datetime
import openai

from app.services.affinity_service import AffinityService, AffinitySignals
from app.services.retrieval_service import RetrievalService, EmbeddingService
from app.services.graph_service import GraphService
from app.services.outbox_service import TransactionManager, IdempotencyChecker
from app.services.working_memory_service import WorkingMemoryService, EntityMention
from app.services.response_cache_service import ResponseCacheService
from app.core.config import settings
from app.core.database import get_neo4j_driver, get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class ConversationDelta:
    """流式输出的增量数据"""
    type: str  # 'text', 'memory_pending', 'memory_committed', 'done', 'error', 'metadata'
    content: Optional[str] = None
    memory_id: Optional[str] = None
    metadata: Optional[dict] = None


@dataclass
class ConversationResponse:
    """对话响应"""
    reply: str
    session_id: str
    turn_id: str
    emotion: dict
    affinity: dict
    memories_used: List[str]
    tone_type: str
    response_time_ms: float
    mode: str = "hybrid"  # graph_only 或 hybrid
    context_source: dict = None  # 上下文来源追踪


class ConversationMode:
    """
    对话模式枚举
    
    架构决策：短期记忆不能参与多跳推理能力的评测
    两者必须在代码层面物理隔离
    """
    GRAPH_ONLY = "graph_only"  # 纯图谱推理，用于能力评测
    HYBRID = "hybrid"          # 图谱 + 短期记忆，用于 Chat 体验


class EmotionAnalyzer:
    """情感分析器"""
    
    def __init__(self, model_name: str = "uer/roberta-base-finetuned-chinanews-chinese"):
        self._model = None
        self._tokenizer = None
        self.model_name = model_name
    
    def _load_model(self):
        """延迟加载模型"""
        if self._model is None:
            try:
                from transformers import AutoModelForSequenceClassification, AutoTokenizer
                self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
                logger.info(f"Loaded emotion model: {self.model_name}")
            except Exception as e:
                logger.warning(f"Failed to load emotion model: {e}")
    
    def analyze(self, text: str) -> dict:
        """分析文本情感"""
        # 简化版：基于关键词的情感分析
        positive_words = ["开心", "高兴", "喜欢", "爱", "棒", "好", "谢谢", "感谢", "哈哈"]
        negative_words = ["难过", "伤心", "讨厌", "烦", "累", "不好", "生气", "失望"]
        
        text_lower = text.lower()
        
        positive_count = sum(1 for w in positive_words if w in text_lower)
        negative_count = sum(1 for w in negative_words if w in text_lower)
        
        if positive_count > negative_count:
            valence = min(0.8, 0.3 + positive_count * 0.1)
            primary_emotion = "happy"
        elif negative_count > positive_count:
            valence = max(-0.8, -0.3 - negative_count * 0.1)
            primary_emotion = "sad"
        else:
            valence = 0.0
            primary_emotion = "neutral"
        
        return {
            "primary_emotion": primary_emotion,
            "valence": valence,
            "confidence": 0.7,
            "emotions": {
                "positive": positive_count,
                "negative": negative_count
            }
        }


class TierRouter:
    """
    意图路由器 - 决定使用哪个 LLM Tier
    
    Property 14: Tier Routing Correctness
    - 简单查询路由到 Tier 3
    - 好感度影响路由决策
    """
    
    # Tier 配置 - 使用硅基流动模型
    TIERS = {
        1: {"model": "deepseek-ai/DeepSeek-V3", "max_tokens": 1000, "cost": "high"},
        2: {"model": "Qwen/Qwen2.5-14B-Instruct", "max_tokens": 500, "cost": "medium"},
        3: {"model": "Qwen/Qwen2.5-7B-Instruct", "max_tokens": 200, "cost": "low"}  # 免费额度
    }
    
    # 简单意图 -> Tier 3
    SIMPLE_INTENTS = ["greeting", "farewell", "thanks", "acknowledgment"]
    
    # 复杂意图 -> Tier 1
    COMPLEX_INTENTS = ["emotional_support", "advice", "deep_conversation"]
    
    # 简单问候模式
    SIMPLE_PATTERNS = [
        "你好", "早上好", "晚上好", "晚安", "谢谢", "好的", "嗯",
        "hi", "hello", "hey", "拜拜", "再见", "ok"
    ]
    
    # 低亲密度状态（优先使用 Tier 3）
    LOW_AFFINITY_STATES = ["stranger", "acquaintance"]
    
    # 高亲密度状态（可以使用 Tier 1）
    HIGH_AFFINITY_STATES = ["close_friend", "best_friend"]
    
    def route(
        self,
        message: str,
        emotion: dict,
        affinity_state: str,
        affinity_score: float = 0.5
    ) -> int:
        """
        决定使用哪个 Tier
        
        Property 14 规则：
        1. 简单查询（< 20 chars，匹配问候模式）-> Tier 3
        2. stranger/acquaintance 状态，除非高情感强度，否则不用 Tier 1
        3. 高情感强度（valence > 0.6）-> Tier 1
        4. 亲密关系 + 长消息 -> Tier 1
        
        Args:
            message: 用户消息
            emotion: 情感分析结果
            affinity_state: 好感度状态
            affinity_score: 好感度分数（0-1）
            
        Returns:
            tier: 1, 2, or 3
        """
        message_len = len(message.strip())
        emotion_valence = abs(emotion.get("valence", 0))
        
        # 规则 1: 简单问候 -> Tier 3
        is_simple = self._is_simple_message(message)
        if is_simple and message_len < 20:
            logger.debug(f"TierRouter: simple message -> Tier 3")
            return 3
        
        # 规则 2: 低亲密度状态的路由限制
        if affinity_state in self.LOW_AFFINITY_STATES:
            # 除非高情感强度，否则不用 Tier 1
            if emotion_valence > 0.6:
                logger.debug(f"TierRouter: low affinity but high emotion -> Tier 1")
                return 1
            # 低亲密度默认用 Tier 2 或 Tier 3
            if message_len < 30:
                logger.debug(f"TierRouter: low affinity, short message -> Tier 3")
                return 3
            logger.debug(f"TierRouter: low affinity -> Tier 2")
            return 2
        
        # 规则 3: 高情感强度 -> Tier 1
        if emotion_valence > 0.6:
            logger.debug(f"TierRouter: high emotion -> Tier 1")
            return 1
        
        # 规则 4: 亲密关系 + 长消息 -> Tier 1
        if affinity_state in self.HIGH_AFFINITY_STATES and message_len > 50:
            logger.debug(f"TierRouter: high affinity + long message -> Tier 1")
            return 1
        
        # 规则 5: 中等亲密度 + 中等消息 -> Tier 2
        if affinity_state == "friend" or message_len > 30:
            logger.debug(f"TierRouter: friend or medium message -> Tier 2")
            return 2
        
        # 默认 -> Tier 2
        logger.debug(f"TierRouter: default -> Tier 2")
        return 2
    
    def _is_simple_message(self, message: str) -> bool:
        """判断是否为简单消息"""
        message_lower = message.strip().lower()
        
        # 检查是否匹配简单模式
        for pattern in self.SIMPLE_PATTERNS:
            if pattern in message_lower:
                return True
        
        return False
    
    def get_routing_explanation(
        self,
        message: str,
        emotion: dict,
        affinity_state: str
    ) -> dict:
        """
        获取路由决策的解释（用于调试）
        """
        tier = self.route(message, emotion, affinity_state)
        
        return {
            "tier": tier,
            "tier_config": self.TIERS[tier],
            "factors": {
                "message_length": len(message),
                "is_simple": self._is_simple_message(message),
                "emotion_valence": emotion.get("valence", 0),
                "affinity_state": affinity_state,
                "is_low_affinity": affinity_state in self.LOW_AFFINITY_STATES,
                "is_high_affinity": affinity_state in self.HIGH_AFFINITY_STATES,
            }
        }


class ConversationService:
    """
    对话服务 - 协调对话流程，支持流式输出
    
    Fast Path: 情感分析 + 检索 + 流式生成 (< 500ms)
    Slow Path: 实体抽取 + 图谱写入 + 向量写入 (异步)
    """
    
    def __init__(
        self,
        affinity_service: AffinityService = None,
        retrieval_service: RetrievalService = None,
        graph_service: GraphService = None,
        transaction_manager: TransactionManager = None,
        idempotency_checker: IdempotencyChecker = None,
        working_memory_service: WorkingMemoryService = None,
        response_cache_service: ResponseCacheService = None
    ):
        self.affinity_service = affinity_service or AffinityService()
        self.retrieval_service = retrieval_service or RetrievalService()
        
        # 初始化 GraphService 时传入 Neo4j driver
        if graph_service:
            self.graph_service = graph_service
        else:
            neo4j_driver = get_neo4j_driver()
            self.graph_service = GraphService(neo4j_driver=neo4j_driver)
        
        self.transaction_manager = transaction_manager or TransactionManager()
        self.idempotency_checker = idempotency_checker or IdempotencyChecker()
        
        # 初始化工作记忆服务
        if working_memory_service:
            self.working_memory_service = working_memory_service
        else:
            redis_client = get_redis_client()
            self.working_memory_service = WorkingMemoryService(redis_client=redis_client)
        
        # 初始化响应缓存服务
        if response_cache_service:
            self.response_cache_service = response_cache_service
        else:
            redis_client = get_redis_client()
            self.response_cache_service = ResponseCacheService(redis_client=redis_client)
        
        self.emotion_analyzer = EmotionAnalyzer()
        self.tier_router = TierRouter()
        self.embedding_service = EmbeddingService()
        
        # 初始化 OpenAI 兼容客户端 (硅基流动)
        self.llm_client = openai.AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE
        )
    
    async def process_message_stream(
        self,
        user_id: str,
        session_id: str,
        message: str,
        idempotency_key: str
    ) -> AsyncIterator[ConversationDelta]:
        """
        流式处理用户消息（SSE/WebSocket）
        
        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            message: 用户消息内容
            idempotency_key: 幂等键（24h 有效期）
            
        Yields:
            ConversationDelta: 增量输出（文本片段、记忆状态等）
        """
        start_time = datetime.now()
        
        # 1. 检查幂等键，防止重复处理
        is_new, existing_memory_id = await self.idempotency_checker.check_and_acquire(
            idempotency_key, user_id
        )
        
        if not is_new:
            yield ConversationDelta(
                type="error",
                content="Duplicate request",
                memory_id=existing_memory_id
            )
            return
        
        try:
            # 2. Fast Path: 情感分析
            emotion = self.emotion_analyzer.analyze(message)
            yield ConversationDelta(
                type="metadata",
                metadata={"emotion": emotion, "phase": "emotion_analyzed"}
            )
            
            # 3. 获取好感度
            affinity = await self.affinity_service.get_affinity(user_id)
            
            # 4. 决定 Tier
            tier = self.tier_router.route(message, emotion, affinity.state, affinity.new_score)
            yield ConversationDelta(
                type="metadata",
                metadata={"tier": tier, "affinity_state": affinity.state}
            )
            
            # 5. 混合检索
            retrieval_result = await self.retrieval_service.hybrid_retrieve(
                user_id, message, affinity.new_score
            )
            
            # 5.5 图谱事实检索（基于查询实体）
            entity_facts = await self.retrieval_service.retrieve_entity_facts(
                user_id, message, self.graph_service
            )
            yield ConversationDelta(
                type="metadata",
                metadata={"entity_facts_count": len(entity_facts), "phase": "facts_retrieved"}
            )
            
            # 6. 流式生成回复
            full_reply = ""
            async for chunk in self._generate_stream(
                message, retrieval_result.memories, affinity, emotion, tier, entity_facts
            ):
                full_reply += chunk
                yield ConversationDelta(type="text", content=chunk)
            
            # 7. Slow Path: 异步写入记忆（通过 Outbox）
            embedding = await self.embedding_service.encode(message)
            memory_id, event_id = await self.transaction_manager.create_memory_with_outbox(
                user_id=user_id,
                content=message,
                embedding=embedding,
                valence=emotion.get("valence", 0),
                conversation_id=session_id,
                idempotency_key=idempotency_key
            )
            
            # 更新幂等键中的 memory_id
            await self.idempotency_checker.set_memory_id(idempotency_key, memory_id)
            
            yield ConversationDelta(
                type="memory_pending",
                memory_id=memory_id,
                metadata={
                    "event_id": event_id,
                    "message": "记忆将在后台写入，下次对话生效"
                }
            )
            
            # 8. 更新好感度
            signals = AffinitySignals(
                user_initiated=True,
                emotion_valence=emotion.get("valence", 0)
            )
            new_affinity = await self.affinity_service.update_affinity(user_id, signals)
            
            # 9. 完成
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            yield ConversationDelta(
                type="done",
                metadata={
                    "response_time_ms": response_time,
                    "memories_used": len(retrieval_result.memories),
                    "new_affinity_score": new_affinity.new_score,
                    "new_affinity_state": new_affinity.state
                }
            )
            
        except Exception as e:
            logger.error(f"Conversation processing failed: {e}")
            # 释放幂等锁
            await self.idempotency_checker.release(idempotency_key)
            yield ConversationDelta(
                type="error",
                content=str(e)
            )
    
    async def process_message(
        self,
        user_id: str,
        message: str,
        session_id: str,
        mode: str = ConversationMode.HYBRID,
        eval_mode: bool = False,
        memorize_only: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> ConversationResponse:
        """
        处理用户消息
        
        Args:
            user_id: 用户 ID
            message: 用户消息
            session_id: 会话 ID
            mode: 对话模式
                - "graph_only": 纯图谱推理，用于能力评测（不注入 history）
                - "hybrid": 图谱 + 短期记忆，用于 Chat 体验
        
        架构决策：
        - mode="graph_only" 时，conversation_history = None（物理隔离）
        - 这是防御式设计，不是只靠 Prompt 约束
        """
        start_time = datetime.now()

        if bool(memorize_only):
            emotion = self.emotion_analyzer.analyze(message)
            embedding = await self.embedding_service.encode(message)
            anchor_dt = None
            try:
                redis = get_redis_client()
                if redis:
                    key = f"locomo_anchor:{user_id}:{session_id}"
                    if str(message).startswith("[session_time]"):
                        dt_text = str(message)[len("[session_time]"):].strip()
                        from app.services.temporal_normalizer import extract_dates
                        dates = extract_dates(dt_text)
                        if dates:
                            from zoneinfo import ZoneInfo
                            y, m, d = (int(x) for x in dates[0].split("-"))
                            anchor_dt = datetime(y, m, d, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
                            await redis.set(key, anchor_dt.isoformat(), ex=6 * 60 * 60)
                    else:
                        cached = await redis.get(key)
                        if cached:
                            anchor_dt = datetime.fromisoformat(str(cached))
            except Exception:
                anchor_dt = None
            mem_id, _event_id = await self.transaction_manager.create_memory_with_outbox(
                user_id=user_id,
                content=message,
                embedding=embedding,
                valence=emotion.get("valence", 0),
                conversation_id=session_id,
                idempotency_key=(idempotency_key or str(uuid.uuid4())),
                skip_llm_extraction=True,
                process_inline=True,
                anchor_dt=anchor_dt,
            )

            response_time = (datetime.now() - start_time).total_seconds() * 1000
            return ConversationResponse(
                reply="",
                session_id=session_id,
                turn_id=str(uuid.uuid4()),
                emotion=emotion,
                affinity={"score": 0.0, "state": "unknown", "delta": 0.0},
                memories_used=[],
                tone_type="neutral",
                response_time_ms=response_time,
                mode=mode,
                context_source={
                    "mode": mode,
                    "eval_mode": bool(eval_mode),
                    "cached": False,
                    "graph_facts_count": 0,
                    "history_turns_count": 0,
                    "vector_memories_count": 0,
                    "memorize_only": True,
                    "memory_id": mem_id,
                },
            )
        
        # ========== Fast Path: 响应缓存检查 ==========
        # 对于简单问候，直接返回缓存响应（< 100ms）
        if not eval_mode and self.response_cache_service.is_cacheable(message):
            # 获取好感度状态（用于选择合适的语气）
            affinity = await self.affinity_service.get_affinity(user_id)
            
            # 尝试从缓存获取响应
            cached_response = await self.response_cache_service.get_cached_response(
                message, affinity.state
            )
            
            if cached_response:
                # 缓存命中！直接返回
                response_time = (datetime.now() - start_time).total_seconds() * 1000
                
                logger.info(f"Cache hit for '{message}' (affinity={affinity.state}), response_time={response_time:.0f}ms")
                
                # 简单情感分析
                emotion = self.emotion_analyzer.analyze(message)
                
                # 更新好感度（即使是缓存响应也要更新）
                signals = AffinitySignals(
                    user_initiated=True,
                    emotion_valence=emotion.get("valence", 0)
                )
                new_affinity = await self.affinity_service.update_affinity(user_id, signals)
                
                # 保存对话轮次（仅 Hybrid 模式）- 后台异步，不阻塞响应
                if mode == ConversationMode.HYBRID:
                    self._save_conversation_turn_background(
                        session_id=session_id,
                        user_id=user_id,
                        user_message=message,
                        assistant_reply=cached_response,
                        emotion=emotion,
                        affinity_score=new_affinity.new_score
                    )
                
                return ConversationResponse(
                    reply=cached_response,
                    session_id=session_id,
                    turn_id=str(uuid.uuid4()),
                    emotion=emotion,
                    affinity={
                        "score": new_affinity.new_score,
                        "state": new_affinity.state,
                        "delta": new_affinity.delta
                    },
                    memories_used=[],  # 缓存响应不使用记忆
                    tone_type=self._get_tone_type(new_affinity.new_score),
                    response_time_ms=response_time,
                    mode=mode,
                    context_source={
                        "mode": mode,
                        "eval_mode": bool(eval_mode),
                        "cached": True,
                        "graph_facts_count": 0,
                        "history_turns_count": 0,
                        "vector_memories_count": 0
                    }
                )
        
        # ========== Slow Path: 完整的对话流程 ==========
        
        # 上下文来源追踪
        context_source = {
            "mode": mode,
            "eval_mode": bool(eval_mode),
            "cached": False,
            "graph_facts_count": 0,
            "history_turns_count": 0,
            "vector_memories_count": 0
        }
        
        # 情感分析
        emotion = self.emotion_analyzer.analyze(message)
        
        # 获取好感度
        affinity = await self.affinity_service.get_affinity(user_id)
        
        # 决定 Tier
        tier = self.tier_router.route(message, emotion, affinity.state, affinity.new_score)
        
        # ========== 并行检索：向量检索 + 图谱检索 ==========
        import asyncio

        if bool(eval_mode) and mode == ConversationMode.GRAPH_ONLY:
            from app.services.evidence_reasoner import compute_answer_from_record_excerpt
            computed_inline = compute_answer_from_record_excerpt(message)
            if computed_inline and computed_inline.get("answer") and (computed_inline.get("evidence") or []):
                response_time = (datetime.now() - start_time).total_seconds() * 1000
                context_source["computed_answer"] = True
                context_source["computed_kind"] = computed_inline.get("kind")
                context_source["computed_evidence_count"] = len(computed_inline.get("evidence") or [])
                context_source["computed_source"] = "record_excerpt"
                reply = f"根据记录片段，是 {computed_inline['answer']}。"
                return ConversationResponse(
                    reply=reply,
                    session_id=session_id,
                    turn_id=str(uuid.uuid4()),
                    emotion=emotion,
                    affinity={"score": affinity.new_score, "state": affinity.state, "delta": 0.0},
                    memories_used=[],
                    tone_type="neutral",
                    response_time_ms=response_time,
                    mode=mode,
                    context_source=context_source,
                )
            from app.services.psychoanalysis_reasoner import compute_psychoanalysis_from_record_excerpt
            psycho = compute_psychoanalysis_from_record_excerpt(message)
            if psycho and psycho.get("answer") and (psycho.get("evidence") or []):
                response_time = (datetime.now() - start_time).total_seconds() * 1000
                context_source["computed_answer"] = True
                context_source["computed_kind"] = psycho.get("kind")
                context_source["computed_evidence_count"] = len(psycho.get("evidence") or [])
                context_source["computed_source"] = "record_excerpt"
                reply = f"根据记录片段，我的判断是：{psycho['answer']}"
                return ConversationResponse(
                    reply=reply,
                    session_id=session_id,
                    turn_id=str(uuid.uuid4()),
                    emotion=emotion,
                    affinity={"score": affinity.new_score, "state": affinity.state, "delta": 0.0},
                    memories_used=[],
                    tone_type="neutral",
                    response_time_ms=response_time,
                    mode=mode,
                    context_source=context_source,
                )
        
        # 创建并行任务
        vector_task = asyncio.create_task(
            self.retrieval_service.hybrid_retrieve(
                user_id, message, affinity.new_score
            )
        )
        graph_task = asyncio.create_task(
            self.retrieval_service.retrieve_entity_facts(
                user_id, message, self.graph_service
            )
        )
        
        # 等待两个任务完成
        retrieval_result, entity_facts = await asyncio.gather(
            vector_task, graph_task
        )
        
        logger.info(f"Parallel retrieval completed: vector={len(retrieval_result.memories)}, graph={len(entity_facts) if entity_facts else 0}")
        
        # ========== 统一 Re-rank：合并两种检索结果后重排序 ==========
        ranked_memories, ranked_facts = self.retrieval_service.unified_rerank(
            vector_memories=retrieval_result.memories,
            graph_facts=entity_facts or [],
            affinity_score=affinity.new_score,
            top_k=10
        )
        
        context_source["vector_memories_count"] = len(ranked_memories)
        context_source["graph_facts_count"] = len(ranked_facts)
        context_source["retrieval_empty"] = (len(ranked_memories) == 0 and len(ranked_facts) == 0)
        context_source["top_vector_memory_ids"] = [getattr(m, "id", None) for m in (ranked_memories or [])[:3] if getattr(m, "id", None)]
        context_source["top_graph_facts"] = [
            {"entity": f.get("entity"), "relation": f.get("relation"), "target": f.get("target")}
            for f in (ranked_facts or [])[:3]
            if isinstance(f, dict)
        ]
        
        # ========== 关键：物理隔离短期记忆 ==========
        conversation_history = None
        if mode == ConversationMode.HYBRID:
            # Hybrid 模式：获取短期记忆（最近 K 轮对话）
            conversation_history = await self._get_conversation_history(session_id, limit=5)
            context_source["history_turns_count"] = len(conversation_history) if conversation_history else 0
            logger.info(f"Hybrid mode: loaded {context_source['history_turns_count']} history turns")
        else:
            # Graph-only 模式：物理隔离，不注入 history
            logger.info("Graph-only mode: history physically isolated (None)")

        from app.services.evidence_reasoner import compute_answer_from_facts
        computed = compute_answer_from_facts(message, ranked_facts or [])
        if computed and computed.get("answer") and (computed.get("evidence") or []):
            signals = AffinitySignals(
                user_initiated=True,
                emotion_valence=emotion.get("valence", 0)
            )
            new_affinity = await self.affinity_service.update_affinity(user_id, signals)

            if mode == ConversationMode.HYBRID:
                self._save_conversation_turn_background(
                    session_id=session_id,
                    user_id=user_id,
                    user_message=message,
                    assistant_reply=f"根据我记下来的记录，是 {computed['answer']}。",
                    emotion=emotion,
                    affinity_score=new_affinity.new_score
                )

            response_time = (datetime.now() - start_time).total_seconds() * 1000
            context_source["computed_answer"] = True
            context_source["computed_kind"] = computed.get("kind")
            context_source["computed_evidence_count"] = len(computed.get("evidence") or [])
            reply = f"根据我记下来的记录，是 {computed['answer']}。"
            return ConversationResponse(
                reply=reply,
                session_id=session_id,
                turn_id=str(uuid.uuid4()),
                emotion=emotion,
                affinity={
                    "score": new_affinity.new_score,
                    "state": new_affinity.state,
                    "delta": new_affinity.delta
                },
                memories_used=[m.id for m in retrieval_result.memories],
                tone_type=self._get_tone_type(new_affinity.new_score),
                response_time_ms=response_time,
                mode=mode,
                context_source=context_source
            )

        if bool(eval_mode) and mode == ConversationMode.GRAPH_ONLY and context_source.get("retrieval_empty"):
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            context_source["failure_bucket"] = "retrieval_empty"
            return ConversationResponse(
                reply="信息不足：未检索到可引用的记录证据。",
                session_id=session_id,
                turn_id=str(uuid.uuid4()),
                emotion=emotion,
                affinity={"score": affinity.new_score, "state": affinity.state, "delta": 0.0},
                memories_used=[],
                tone_type="neutral",
                response_time_ms=response_time,
                mode=mode,
                context_source=context_source,
            )
        
        # 生成回复（使用重排序后的结果）
        reply = await self._generate_reply(
            message,
            ranked_memories,
            affinity,
            emotion,
            tier,
            ranked_facts,
            conversation_history,
            mode,
            eval_mode=bool(eval_mode),
        )
        
        # 更新好感度
        signals = AffinitySignals(
            user_initiated=True,
            emotion_valence=emotion.get("valence", 0)
        )
        new_affinity = await self.affinity_service.update_affinity(user_id, signals)
        
        # 保存对话轮次（仅 Hybrid 模式）- 后台异步，不阻塞响应
        if mode == ConversationMode.HYBRID:
            self._save_conversation_turn_background(
                session_id=session_id,
                user_id=user_id,
                user_message=message,
                assistant_reply=reply,
                emotion=emotion,
                affinity_score=new_affinity.new_score
            )
        
        response_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return ConversationResponse(
            reply=reply,
            session_id=session_id,
            turn_id=str(uuid.uuid4()),
            emotion=emotion,
            affinity={
                "score": new_affinity.new_score,
                "state": new_affinity.state,
                "delta": new_affinity.delta
            },
            memories_used=[m.id for m in retrieval_result.memories],
            tone_type=self._get_tone_type(new_affinity.new_score),
            response_time_ms=response_time,
            mode=mode,
            context_source=context_source
        )
    
    async def _generate_stream(
        self,
        message: str,
        memories: list,
        affinity,
        emotion: dict,
        tier: int,
        entity_facts: list = None
    ) -> AsyncIterator[str]:
        """流式生成回复"""
        prompt = self._build_prompt(message, memories, affinity, emotion, entity_facts)
        tier_config = TierRouter.TIERS.get(tier, TierRouter.TIERS[2])
        
        logger.info(f"Calling LLM API: model={tier_config['model']}, max_tokens={tier_config['max_tokens']}")
        logger.info(f"Entity facts count: {len(entity_facts) if entity_facts else 0}")
        
        try:
            response = await self.llm_client.chat.completions.create(
                model=tier_config["model"],
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": message}
                ],
                max_tokens=tier_config["max_tokens"],
                stream=True,
                temperature=0.7,
                presence_penalty=0.6,
                frequency_penalty=0.3
            )
            
            logger.info("LLM API call successful, streaming response...")
            
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    logger.debug(f"Stream chunk: {content}")
                    yield content
                    
        except Exception as e:
            logger.error(f"LLM stream generation failed: {e}", exc_info=True)
            # 降级到模拟回复
            reply = self._generate_mock_reply(message, affinity.state, emotion)
            for char in reply:
                yield char
    
    async def _generate_reply(
        self,
        message: str,
        memories: list,
        affinity,
        emotion: dict,
        tier: int,
        entity_facts: list = None,
        conversation_history: list = None,
        mode: str = "hybrid",
        eval_mode: bool = False,
    ) -> str:
        """生成回复（非流式）"""
        prompt = self._build_prompt(
            message,
            memories,
            affinity,
            emotion,
            entity_facts,
            conversation_history,
            mode,
            eval_mode=bool(eval_mode),
        )
        tier_config = TierRouter.TIERS.get(tier, TierRouter.TIERS[2])
        
        try:
            response = await self.llm_client.chat.completions.create(
                model=tier_config["model"],
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": message}
                ],
                max_tokens=tier_config["max_tokens"],
                stream=False,
                temperature=0.7,
                presence_penalty=0.6,
                frequency_penalty=0.3
            )
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # 降级到模拟回复
            return self._generate_mock_reply(message, affinity.state, emotion)
    
    def _build_prompt(
        self,
        message: str,
        memories: list,
        affinity,
        emotion: dict,
        entity_facts: list = None,
        conversation_history: list = None,
        mode: str = "hybrid",
        eval_mode: bool = False,
    ) -> str:
        """
        构建动态 Prompt
        
        架构决策：明确区分【长期记忆】和【短期记忆】的来源
        - 长期记忆（Graph）：用于事实性问题，是推理的基础
        - 短期记忆（History）：仅用于上下文理解，不作为事实来源
        """
        tone_config = AffinityService.get_tone_config(affinity.state)
        
        # ========== 长期记忆：图谱事实（多跳推理的基础）==========
        direct_facts = []
        indirect_facts = []
        
        if entity_facts:
            for fact in entity_facts[:20]:
                hop = fact.get("hop", 1)
                relation_cn = self._translate_relation(fact.get("relation", ""))
                
                if hop == 1:
                    direct_facts.append(f"- {fact['entity']} {relation_cn} {fact['target']}")
                else:
                    path = fact.get("path", "")
                    via = fact.get("via", "")
                    if path:
                        indirect_facts.append(f"- [{hop}-hop] {path}")
                    elif via:
                        indirect_facts.append(f"- [{hop}-hop] {fact['entity']} -> (通过{via}) -> {fact['target']}")
        
        # 构建图谱事实上下文
        graph_context = ""
        if direct_facts:
            graph_context += "【直接关系】\n" + "\n".join(direct_facts)
        if indirect_facts:
            if graph_context:
                graph_context += "\n\n"
            graph_context += "【间接关系（通过关联人物）】\n" + "\n".join(indirect_facts)
        
        has_graph_facts = bool(direct_facts or indirect_facts)
        
        # ========== 长期记忆：向量检索结果 ==========
        vector_context = ""
        if memories:
            vector_context = "\n".join([
                f"- {m.content} (相关度: {m.final_score:.2f})"
                for m in memories[:5]
            ])
        
        # ========== 短期记忆：对话历史（仅 Hybrid 模式）==========
        history_context = ""
        if mode == ConversationMode.HYBRID and conversation_history:
            history_lines = []
            for turn in conversation_history[-5:]:  # 最近 5 轮
                role = "用户" if turn.get("role") == "user" else "AI"
                history_lines.append(f"- {role}: {turn.get('content', '')[:100]}")
            history_context = "\n".join(history_lines)
        
        # ========== 构建 Prompt ==========
        prompt = f"""你是一个严谨的评测型 AI 助手，名叫 Affinity。""" if eval_mode else f"""你是一个情感陪伴 AI，名叫 Affinity。

当前用户状态:
- 好感度: {affinity.new_score:.2f} ({affinity.state})
- 情绪: {emotion.get('primary_emotion', 'neutral')} (强度: {emotion.get('valence', 0):.2f})

语气要求:
- 正式程度: {tone_config['formality']}
- 亲密度: {tone_config['intimacy_level']}/5

=== 长期记忆（图谱推理结果）===
{graph_context if has_graph_facts else "（没有找到相关的结构化记录）"}

=== 长期记忆（向量检索结果）===
{vector_context if vector_context else "（没有找到相关的对话记忆）"}
"""
        
        # 仅 Hybrid 模式添加短期记忆
        if mode == ConversationMode.HYBRID and history_context:
            prompt += f"""
=== 短期记忆（本次对话历史）===
【注意：仅供理解上下文，不作为事实来源】
{history_context}
"""
        
        # 添加回答规则
        prompt += """
【回答规则 - 必须严格遵守】
1. 事实性问题必须基于「长期记忆」中的信息
2. 如果有「间接关系」，可以基于关联人物进行合理推断
3. 可以结合常识知识对已知事实进行推理（例如：大连是海边城市，上海是南方城市）
4. 「短期记忆」只用于理解对话上下文，不能作为事实来源
5. 如果长期记忆没有相关信息，诚实回答"我不记得你告诉过我这些"
6. 可以询问用户来获取更多信息

【常识推理示例】
- 用户问"谁住在海边"，记忆中有"昊哥住在大连"→ 可以推理"大连是海边城市，所以昊哥住在海边"
- 用户问"谁来自南方"，记忆中有"张伟住在上海"→ 可以推理"上海是南方城市"

【严禁行为】
❌ 绝对禁止编造用户从未提及的具体信息
❌ 禁止猜测未知的具体细节
❌ 禁止使用"说不定"、"或许"来填补信息空白
✅ 正确做法：直接说"我不知道"，然后询问用户

请根据以上信息，生成一个温暖、诚实的回复。"""

        if eval_mode:
            prompt += """

【评测模式补充规则】
1. 如果用户消息中包含记录片段/record excerpt（例如以“Below is the record excerpt”开头），必须优先根据该片段作答
2. 在评测模式下，不要输出“我不记得你告诉过我这些”，应基于用户消息中的记录片段回答或明确说明片段中没有答案
3. 对时间/数值问题，必须给出明确答案（例如“8 minutes 40 seconds”），不要泛泛而谈
"""
        
        return prompt
    
    def _translate_relation(self, relation_type: str) -> str:
        """将关系类型翻译为中文"""
        translations = {
            "LIKES": "喜欢",
            "DISLIKES": "不喜欢",
            "FROM": "来自",
            "LIVES_IN": "住在",
            "WORKS_AT": "工作于",
            "FRIEND_OF": "是...的朋友",
            "FAMILY": "是...的家人",
            "SIBLING_OF": "是...的兄弟姐妹",
            "PARENT_OF": "是...的父母",
            "CHILD_OF": "是...的孩子",
            "COUSIN_OF": "是...的表亲",
            "COLLEAGUE_OF": "是...的同事",
            "CLASSMATE_OF": "是...的同学",
            "RELATED_TO": "与...相关",
            "HAPPENED_AT": "发生于",
            "LASTED": "持续",
            "COST": "花费",
        }
        return translations.get(relation_type, relation_type)
    
    def _generate_mock_reply(
        self,
        message: str,
        affinity_state: str,
        emotion: dict
    ) -> str:
        """生成模拟回复（用于测试）"""
        # 根据好感度状态调整语气
        greetings = {
            "stranger": "你好，",
            "acquaintance": "嗨，",
            "friend": "哈喽～",
            "close_friend": "亲爱的～",
            "best_friend": "宝贝！"
        }
        
        greeting = greetings.get(affinity_state, "你好，")
        
        # 根据情绪调整回复
        valence = emotion.get("valence", 0)
        
        if valence > 0.3:
            response = f"{greeting}看到你这么开心我也很高兴呢！有什么想分享的吗？"
        elif valence < -0.3:
            response = f"{greeting}感觉你今天心情不太好，想聊聊吗？我在这里陪着你。"
        else:
            response = f"{greeting}收到你的消息了！今天过得怎么样？"
        
        return response
    
    def _get_tone_type(self, affinity_score: float) -> str:
        """根据好感度获取语气类型"""
        if affinity_score >= 0.7:
            return "intimate"
        elif affinity_score >= 0.5:
            return "warm"
        elif affinity_score >= 0.3:
            return "friendly"
        else:
            return "polite"
    
    async def _get_conversation_history(
        self,
        session_id: str,
        limit: int = 5
    ) -> List[dict]:
        """
        获取当前会话的最近 K 轮对话（短期记忆）
        
        用途：Latency Masking Layer（异步写入延迟掩盖）
        注意：仅用于上下文理解，不作为事实来源
        """
        from sqlalchemy import text
        from app.core.database import AsyncSessionLocal
        
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    text("""
                        SELECT role, content, created_at
                        FROM conversation_turns
                        WHERE session_id = :session_id
                        ORDER BY created_at DESC
                        LIMIT :limit
                    """),
                    {"session_id": session_id, "limit": limit * 2}  # user + assistant
                )
                rows = result.fetchall()
                
                if not rows:
                    return []
                
                # 转换为字典列表，按时间正序
                history = [
                    {"role": row[0], "content": row[1], "created_at": row[2]}
                    for row in reversed(rows)
                ]
                
                logger.info(f"Loaded {len(history)} conversation turns for session {session_id[:8]}")
                return history
                
        except Exception as e:
            logger.warning(f"Failed to load conversation history: {e}")
            return []
    
    def _save_conversation_turn_background(
        self,
        session_id: str,
        user_id: str,
        user_message: str,
        assistant_reply: str,
        emotion: dict,
        affinity_score: float
    ):
        """
        后台保存对话轮次到数据库（不阻塞响应）
        
        用于短期记忆（Hybrid 模式）
        
        优化：使用 asyncio.create_task 异步执行，不等待完成
        """
        import asyncio
        
        async def _save():
            from sqlalchemy import text
            from app.core.database import AsyncSessionLocal
            import json
            
            try:
                async with AsyncSessionLocal() as db:
                    # 保存用户消息
                    await db.execute(
                        text("""
                            INSERT INTO conversation_turns 
                            (id, session_id, user_id, role, content, emotion_result, affinity_at_turn, created_at)
                            VALUES (:id, :session_id, :user_id, 'user', :content, :emotion, :affinity, NOW())
                        """),
                        {
                            "id": str(uuid.uuid4()),
                            "session_id": session_id,
                            "user_id": user_id,
                            "content": user_message,
                            "emotion": emotion,
                            "affinity": float(affinity_score)
                        }
                    )
                    
                    # 保存 AI 回复
                    await db.execute(
                        text("""
                            INSERT INTO conversation_turns 
                            (id, session_id, user_id, role, content, created_at)
                            VALUES (:id, :session_id, :user_id, 'assistant', :content, NOW())
                        """),
                        {
                            "id": str(uuid.uuid4()),
                            "session_id": session_id,
                            "user_id": user_id,
                            "content": assistant_reply
                        }
                    )
                    
                    await db.commit()
                    logger.debug(f"Background saved conversation turn for session {session_id[:8]}")
                    
            except Exception as e:
                logger.warning(f"Failed to save conversation turn in background: {e}")
        
        # 创建后台任务，不等待完成
        try:
            asyncio.create_task(_save())
        except RuntimeError:
            # 如果没有运行中的事件循环，直接忽略
            logger.warning("No running event loop, skipping conversation turn save")
