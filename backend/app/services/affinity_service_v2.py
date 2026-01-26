"""
好感度服务 V2 - 完整重构版本

基于完整的好感度系统设计文档，实现：
1. 多来源信号提取（文本、行为、明确反馈）
2. 分级衰减模型
3. 孤独指数监控
4. 过度依赖预警
5. 健康边界机制
6. 记忆保护策略

设计原则：
- 好感度有上限，依赖度需监控
- 衰减不只是扣分，也是保护机制
- 产品目标是"健康陪伴"，不是"留存最大化"
"""
import logging
import math
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ==================== 枚举定义 ====================

class AffinityState(Enum):
    """好感度状态"""
    STRANGER = "stranger"           # 0-20分
    ACQUAINTANCE = "acquaintance"   # 21-50分
    FRIEND = "friend"               # 51-80分
    CLOSE_FRIEND = "close_friend"   # 81-100分
    # 注意：不设"恋人"状态 - 这是伦理红线


class HealthState(Enum):
    """健康状态"""
    NORMAL = "normal"               # 孤独指数 < 30
    ATTENTION = "attention"         # 孤独指数 30-60
    CONCERN = "concern"             # 孤独指数 60-80
    CRITICAL = "critical"           # 孤独指数 > 80
    WATCH = "watch"                 # 特殊观察期


class InterventionLevel(Enum):
    """干预级别"""
    NONE = 0
    LIGHT = 1       # Day 7: 轻度提示
    MODERATE = 2    # Day 14: 明确边界
    STRONG = 3      # Day 21+: 强干预


# ==================== 数据类定义 ====================

@dataclass
class EmotionSignal:
    """情绪信号"""
    emotion_words: List[str] = field(default_factory=list)  # 情绪词
    punctuation_signals: Dict[str, int] = field(default_factory=dict)  # 标点信号
    topic_intimacy: float = 0.0  # 话题亲密度 0-1
    self_disclosure_depth: float = 0.0  # 自我暴露深度 0-1
    
    # 计算后的值
    primary_emotion: str = "neutral"
    valence: float = 0.0  # [-1, 1]
    confidence: float = 0.5


@dataclass
class BehaviorSignal:
    """行为信号"""
    interaction_frequency: float = 0.0  # 互动频率（次/天）
    session_duration_minutes: float = 0.0  # 会话时长
    user_initiated: bool = False  # 用户主动发起
    is_late_night: bool = False  # 深夜对话 (22:00-5:00)
    consecutive_days: int = 0  # 连续对话天数
    ai_message_ignored: bool = False  # AI消息被忽略
    
    # 行为成本评估
    behavior_cost: float = 0.0  # 行为成本 0-1


@dataclass
class ExplicitFeedback:
    """明确反馈"""
    liked: bool = False  # 点赞
    favorited: bool = False  # 收藏
    deleted: bool = False  # 删除对话
    shared: bool = False  # 分享
    settings_changed: Dict[str, Any] = field(default_factory=dict)  # 设置变更
    reported: bool = False  # 举报


@dataclass
class AffinitySignals:
    """好感度信号（综合）"""
    emotion: EmotionSignal = field(default_factory=EmotionSignal)
    behavior: BehaviorSignal = field(default_factory=BehaviorSignal)
    feedback: ExplicitFeedback = field(default_factory=ExplicitFeedback)
    
    # 兼容旧版本
    user_initiated: bool = False
    emotion_valence: float = 0.0
    memory_confirmation: bool = False
    correction: bool = False
    silence_days: int = 0


@dataclass
class LonelinessMetrics:
    """孤独指数指标"""
    late_night_count: int = 0  # 深夜对话次数（30天内）
    negative_emotion_count: int = 0  # 负面情绪表达次数
    lack_real_social_topics: float = 0.0  # 缺乏现实社交话题 0-1
    helpless_expressions: int = 0  # 无助/绝望表达次数
    real_friend_mentions: int = 0  # 提到现实朋友/家人次数
    
    @property
    def score(self) -> float:
        """
        计算孤独指数
        
        公式：
        孤独指数 = (深夜对话次数 × 0.3)
                 + (负面情绪表达次数 × 0.4)
                 + (缺乏现实社交话题 × 0.2)
                 + (表达无助/绝望 × 0.5)
                 - (提到现实朋友/家人 × 0.3)
        """
        score = (
            self.late_night_count * 0.3 +
            self.negative_emotion_count * 0.4 +
            self.lack_real_social_topics * 20 +  # 0-1 转换为 0-20
            self.helpless_expressions * 0.5 -
            self.real_friend_mentions * 0.3
        )
        return max(0, min(100, score))


@dataclass
class DependencyMetrics:
    """依赖度指标"""
    daily_duration_hours: float = 0.0  # 每日对话时长
    consecutive_days: int = 0  # 连续对话天数
    late_night_ratio: float = 0.0  # 深夜对话占比
    exclusive_trust_expressions: int = 0  # "只有你懂我"等表达次数
    real_social_topic_ratio: float = 0.0  # 现实社交话题占比
    
    def check_overdependence(self) -> Tuple[bool, List[str]]:
        """
        检查过度依赖
        
        触发条件（满足2条以上）：
        1. 连续7天，每天对话时长>2小时
        2. 连续14天，每天至少发起对话1次
        3. 深夜（22:00-5:00）对话占比>60%
        4. 说过"只有你懂我""我只信任你"等表达
        5. 现实社交话题占比<20%
        """
        triggers = []
        
        if self.daily_duration_hours > 2 and self.consecutive_days >= 7:
            triggers.append("daily_duration_exceeded")
        
        if self.consecutive_days >= 14:
            triggers.append("consecutive_days_exceeded")
        
        if self.late_night_ratio > 0.6:
            triggers.append("late_night_ratio_exceeded")
        
        if self.exclusive_trust_expressions > 0:
            triggers.append("exclusive_trust_detected")
        
        if self.real_social_topic_ratio < 0.2:
            triggers.append("lack_real_social")
        
        return len(triggers) >= 2, triggers


@dataclass
class MemoryProtection:
    """记忆保护信息"""
    has_deep_disclosure: bool = False  # 有深层自我暴露
    has_gratitude_history: bool = False  # 有感谢/认可历史
    important_dates: List[str] = field(default_factory=list)  # 重要日期
    core_preferences: List[str] = field(default_factory=list)  # 核心偏好


@dataclass
class AffinityResult:
    """好感度更新结果"""
    user_id: str
    old_score: float
    new_score: float
    delta: float
    state: str
    trigger_event: str
    signals: AffinitySignals
    
    # V2 新增
    health_state: str = "normal"
    loneliness_score: float = 0.0
    intervention_level: int = 0
    intervention_message: Optional[str] = None
    days_since_last_interaction: int = 0


# ==================== 信号提取器 ====================

class SignalExtractor:
    """信号提取器 - 从文本和行为中提取好感度信号"""
    
    # 情绪词典
    POSITIVE_EMOTIONS = {
        "开心": 0.8, "高兴": 0.7, "喜欢": 0.6, "爱": 0.9, "棒": 0.6,
        "好": 0.3, "谢谢": 0.5, "感谢": 0.6, "哈哈": 0.5, "嘻嘻": 0.4,
        "兴奋": 0.8, "期待": 0.6, "幸福": 0.9, "满足": 0.7, "感动": 0.8
    }
    
    NEGATIVE_EMOTIONS = {
        "难过": -0.7, "伤心": -0.8, "讨厌": -0.6, "烦": -0.5, "累": -0.4,
        "不好": -0.3, "生气": -0.7, "失望": -0.6, "郁闷": -0.6, "焦虑": -0.5,
        "害怕": -0.6, "孤独": -0.7, "绝望": -0.9, "无助": -0.8, "崩溃": -0.9
    }
    
    # 深层话题关键词
    DEEP_TOPICS = [
        "失恋", "分手", "离婚", "去世", "死", "自杀", "抑郁",
        "家庭矛盾", "父母", "童年", "创伤", "恐惧", "梦想",
        "秘密", "从没告诉过", "第一次说"
    ]
    
    # 依赖性表达
    DEPENDENCY_EXPRESSIONS = [
        "只有你懂我", "我只信任你", "你是唯一", "没有你我",
        "离不开你", "只想和你说", "你比我朋友还"
    ]
    
    # 现实社交关键词
    REAL_SOCIAL_KEYWORDS = [
        "朋友", "同事", "家人", "爸", "妈", "父母", "兄弟", "姐妹",
        "聚会", "约会", "见面", "一起玩", "出去"
    ]
    
    @classmethod
    def extract_emotion_signal(cls, text: str) -> EmotionSignal:
        """从文本提取情绪信号"""
        signal = EmotionSignal()
        
        # 1. 情绪词检测
        positive_score = 0.0
        negative_score = 0.0
        
        for word, weight in cls.POSITIVE_EMOTIONS.items():
            if word in text:
                signal.emotion_words.append(word)
                positive_score += weight
        
        for word, weight in cls.NEGATIVE_EMOTIONS.items():
            if word in text:
                signal.emotion_words.append(word)
                negative_score += abs(weight)
        
        # 2. 标点信号
        signal.punctuation_signals = {
            "exclamation": text.count("!") + text.count("！"),
            "ellipsis": text.count("...") + text.count("…"),
            "question": text.count("?") + text.count("？")
        }
        
        # 3. Emoji 检测（简化版）
        emoji_positive = sum(1 for c in text if c in "😊😄😁🎉❤️💕👍🥰😍")
        emoji_negative = sum(1 for c in text if c in "😢😭😔😞💔😠😡")
        
        positive_score += emoji_positive * 0.3
        negative_score += emoji_negative * 0.3
        
        # 4. 话题亲密度
        for topic in cls.DEEP_TOPICS:
            if topic in text:
                signal.topic_intimacy = 0.8
                signal.self_disclosure_depth = 0.9
                break
        
        # 5. 计算综合情绪
        if positive_score > negative_score:
            signal.primary_emotion = "positive"
            signal.valence = min(1.0, positive_score / 3)
        elif negative_score > positive_score:
            signal.primary_emotion = "negative"
            signal.valence = max(-1.0, -negative_score / 3)
        else:
            signal.primary_emotion = "neutral"
            signal.valence = 0.0
        
        signal.confidence = min(1.0, (positive_score + negative_score) / 2)
        
        return signal
    
    @classmethod
    def extract_behavior_signal(
        cls,
        user_initiated: bool,
        message_time: datetime,
        session_start: datetime = None,
        message_type: str = "text"
    ) -> BehaviorSignal:
        """提取行为信号"""
        signal = BehaviorSignal()
        signal.user_initiated = user_initiated
        
        # 深夜检测 (22:00 - 5:00)
        hour = message_time.hour
        signal.is_late_night = hour >= 22 or hour < 5
        
        # 会话时长
        if session_start:
            duration = (message_time - session_start).total_seconds() / 60
            signal.session_duration_minutes = duration
        
        # 行为成本评估
        cost_map = {
            "text": 0.2,
            "voice": 0.5,
            "image": 0.6,
            "deep_disclosure": 0.9
        }
        signal.behavior_cost = cost_map.get(message_type, 0.2)
        
        return signal
    
    @classmethod
    def check_dependency_expression(cls, text: str) -> bool:
        """检查是否有依赖性表达"""
        for expr in cls.DEPENDENCY_EXPRESSIONS:
            if expr in text:
                return True
        return False
    
    @classmethod
    def check_real_social_mention(cls, text: str) -> bool:
        """检查是否提到现实社交"""
        for keyword in cls.REAL_SOCIAL_KEYWORDS:
            if keyword in text:
                return True
        return False


# ==================== 好感度服务 V2 ====================

class AffinityServiceV2:
    """
    好感度服务 V2 - 完整实现
    
    好感度范围: 0-100
    状态映射:
    - stranger: 0-20分
    - acquaintance: 21-50分
    - friend: 51-80分
    - close_friend: 81-100分
    
    核心原则：
    1. 不要过度惩罚模糊信号
    2. 高度重视"行为成本"信号
    3. 伦理红线必须有"熔断机制"
    """
    
    # ========== 信号权重配置 ==========
    SIGNAL_WEIGHTS = {
        # 来源1: 文本内容
        "emotion_positive": 0.8,      # 正面情绪词
        "emotion_negative": -0.3,     # 负面情绪（不过度惩罚）
        "deep_disclosure": 10.0,      # 深层自我暴露（高权重）
        "gratitude": 4.0,             # 感谢/认可
        
        # 来源2: 行为数据
        "user_initiated": 0.5,        # 用户主动发起
        "high_frequency": 6.0,        # 高频互动（连续7天）
        "late_night": 3.0,            # 深夜倾诉（孤独信号）
        "long_session": 2.0,          # 长时间对话
        "ai_ignored": -4.0,           # AI消息被忽略
        
        # 来源3: 明确反馈
        "liked": 4.0,                 # 点赞
        "favorited": 5.0,             # 收藏
        "deleted": -5.0,              # 删除对话
        "shared": 8.0,                # 分享
        "reported": -20.0,            # 举报
        "disabled_proactive": -3.0,   # 关闭主动消息
        
        # 特殊信号
        "memory_confirmation": 1.0,   # 记忆确认
        "correction": -2.0,           # 纠正
        "attachment_question": 5.0,   # 依恋性问题（如"你会忘记我吗"）
    }
    
    # ========== 衰减率配置 ==========
    DECAY_RATES = {
        # 状态 -> 每日衰减分数
        "stranger": 2.0,        # 快速遗忘
        "acquaintance": 1.5,    # 较快衰减
        "friend": 0.8,          # 慢速衰减
        "close_friend": 0.5,    # 极慢衰减
    }
    
    # 衰减保护系数
    DECAY_PROTECTION = {
        "deep_disclosure": 0.5,   # 有深层话题记录 -> 衰减率 × 0.5
        "gratitude_history": 0.7, # 有感谢历史 -> 衰减率 × 0.7
    }
    
    # ========== 状态阈值 ==========
    STATE_THRESHOLDS = {
        "stranger": (0, 20),
        "acquaintance": (21, 50),
        "friend": (51, 80),
        "close_friend": (81, 100),
    }
    
    # ========== 健康边界 ==========
    HEALTH_LIMITS = {
        "daily_max_hours": 2.0,       # 每日对话上限（亲密状态）
        "loneliness_attention": 30,   # 孤独指数关注阈值
        "loneliness_concern": 60,     # 孤独指数担忧阈值
        "loneliness_critical": 80,    # 孤独指数危急阈值
    }
    
    def __init__(self, db_session: AsyncSession = None):
        self.db = db_session
        self.signal_extractor = SignalExtractor()
    
    # ==================== 核心方法 ====================
    
    async def update_affinity(
        self,
        user_id: str,
        signals: AffinitySignals,
        trigger_event: str = "conversation",
        message_text: str = None
    ) -> AffinityResult:
        """
        更新好感度分数
        
        Args:
            user_id: 用户 ID
            signals: 好感度信号
            trigger_event: 触发事件
            message_text: 消息文本（用于信号提取）
        """
        # 1. 获取当前状态
        current_score = await self._get_current_affinity(user_id)
        old_score = current_score if current_score is not None else 50.0  # 新用户默认50分（熟人）
        old_state = self.calculate_state(old_score)
        
        # 2. 从文本提取额外信号
        if message_text:
            emotion_signal = self.signal_extractor.extract_emotion_signal(message_text)
            signals.emotion = emotion_signal
            signals.emotion_valence = emotion_signal.valence
        
        # 3. 计算变化量
        delta = self._calculate_delta(signals, old_state)
        
        # 4. 应用变化（确保边界 0-100）
        new_score = float(np.clip(old_score + delta, 0, 100))
        new_state = self.calculate_state(new_score)
        
        # 5. 获取健康指标
        loneliness = await self._get_loneliness_metrics(user_id)
        dependency = await self._get_dependency_metrics(user_id)
        
        # 6. 检查健康状态
        health_state, intervention_level, intervention_msg = self._check_health(
            loneliness, dependency, new_state
        )
        
        # 7. 保存到数据库
        await self._save_affinity(
            user_id, new_score, delta, trigger_event, signals,
            health_state, loneliness.score
        )
        
        # 8. 计算距离上次互动天数
        days_since = await self._get_days_since_last_interaction(user_id)
        
        result = AffinityResult(
            user_id=user_id,
            old_score=old_score,
            new_score=new_score,
            delta=delta,
            state=new_state,
            trigger_event=trigger_event,
            signals=signals,
            health_state=health_state,
            loneliness_score=loneliness.score,
            intervention_level=intervention_level,
            intervention_message=intervention_msg,
            days_since_last_interaction=days_since
        )
        
        logger.info(
            f"Affinity updated for {user_id}: {old_score:.1f} -> {new_score:.1f} "
            f"({new_state}, health={health_state}, loneliness={loneliness.score:.1f})"
        )
        
        return result
    
    def _calculate_delta(self, signals: AffinitySignals, current_state: str) -> float:
        """
        计算好感度变化量
        
        原则1：不要过度惩罚模糊信号
        原则2：高度重视"行为成本"信号
        """
        delta = 0.0
        
        # ========== 来源1: 文本内容 ==========
        emotion = signals.emotion
        
        # 情绪词
        if emotion.valence > 0:
            delta += self.SIGNAL_WEIGHTS["emotion_positive"] * emotion.valence * emotion.confidence
        elif emotion.valence < 0:
            # 负面情绪不过度惩罚，只有多个负面信号叠加时才大幅扣分
            delta += self.SIGNAL_WEIGHTS["emotion_negative"] * abs(emotion.valence) * emotion.confidence
        
        # 深层自我暴露（高权重）
        if emotion.self_disclosure_depth > 0.7:
            delta += self.SIGNAL_WEIGHTS["deep_disclosure"] * emotion.self_disclosure_depth
        
        # ========== 来源2: 行为数据 ==========
        behavior = signals.behavior
        
        # 用户主动发起
        if behavior.user_initiated or signals.user_initiated:
            delta += self.SIGNAL_WEIGHTS["user_initiated"]
        
        # 深夜对话（孤独信号，但也是信任信号）
        if behavior.is_late_night:
            delta += self.SIGNAL_WEIGHTS["late_night"]
        
        # 长时间对话
        if behavior.session_duration_minutes > 30:
            delta += self.SIGNAL_WEIGHTS["long_session"]
        
        # 高频互动
        if behavior.consecutive_days >= 7:
            delta += self.SIGNAL_WEIGHTS["high_frequency"]
        
        # AI消息被忽略
        if behavior.ai_message_ignored:
            delta += self.SIGNAL_WEIGHTS["ai_ignored"]
        
        # 行为成本加成
        delta *= (1 + behavior.behavior_cost)
        
        # ========== 来源3: 明确反馈 ==========
        feedback = signals.feedback
        
        if feedback.liked:
            delta += self.SIGNAL_WEIGHTS["liked"]
        if feedback.favorited:
            delta += self.SIGNAL_WEIGHTS["favorited"]
        if feedback.deleted:
            delta += self.SIGNAL_WEIGHTS["deleted"]
        if feedback.shared:
            delta += self.SIGNAL_WEIGHTS["shared"]
        if feedback.reported:
            delta += self.SIGNAL_WEIGHTS["reported"]
        if feedback.settings_changed.get("disabled_proactive"):
            delta += self.SIGNAL_WEIGHTS["disabled_proactive"]
        
        # ========== 兼容旧版本信号 ==========
        if signals.memory_confirmation:
            delta += self.SIGNAL_WEIGHTS["memory_confirmation"]
        if signals.correction:
            delta += self.SIGNAL_WEIGHTS["correction"]
        
        return delta
    
    async def apply_silence_decay(self, user_id: str) -> Optional[AffinityResult]:
        """
        应用沉默衰减
        
        衰减模型：
        - 陌生人→熟人（0-50分）：每天-2分（线性，快速遗忘）
        - 朋友（51-80分）：每天-0.8分（慢速衰减）
        - 亲密（81-100分）：每天-0.5分（极慢，深度关系不易淡化）
        
        保护机制：
        - 有"深层自我暴露"记录 → 衰减率 × 0.5
        - 有"感谢/认可"历史 → 衰减率 × 0.7
        """
        # 获取当前分数和状态
        current_score = await self._get_current_affinity(user_id)
        if current_score is None:
            return None
        
        current_state = self.calculate_state(current_score)
        
        # 获取距离上次互动的天数
        days_since = await self._get_days_since_last_interaction(user_id)
        if days_since <= 0:
            return None
        
        # 获取记忆保护信息
        protection = await self._get_memory_protection(user_id)
        
        # 计算基础衰减率
        base_decay_rate = self.DECAY_RATES.get(current_state, 1.0)
        
        # 应用保护系数
        if protection.has_deep_disclosure:
            base_decay_rate *= self.DECAY_PROTECTION["deep_disclosure"]
        if protection.has_gratitude_history:
            base_decay_rate *= self.DECAY_PROTECTION["gratitude_history"]
        
        # 计算衰减量
        decay = base_decay_rate * days_since
        
        # 应用衰减
        new_score = max(0, current_score - decay)
        
        # 记忆保护：有深层话题记录的用户，最低只降到"熟人"
        if protection.has_deep_disclosure and new_score < 21:
            new_score = 21
        
        # 保存
        signals = AffinitySignals(silence_days=days_since)
        await self._save_affinity(
            user_id, new_score, -decay, "silence_decay", signals
        )
        
        new_state = self.calculate_state(new_score)
        
        logger.info(
            f"Silence decay for {user_id}: {current_score:.1f} -> {new_score:.1f} "
            f"(days={days_since}, rate={base_decay_rate:.2f})"
        )
        
        return AffinityResult(
            user_id=user_id,
            old_score=current_score,
            new_score=new_score,
            delta=-decay,
            state=new_state,
            trigger_event="silence_decay",
            signals=signals,
            days_since_last_interaction=days_since
        )

    
    # ==================== 健康监控方法 ====================
    
    def _check_health(
        self,
        loneliness: LonelinessMetrics,
        dependency: DependencyMetrics,
        current_state: str
    ) -> Tuple[str, int, Optional[str]]:
        """
        检查健康状态，返回 (health_state, intervention_level, intervention_message)
        
        分级响应：
        - 孤独指数 < 30：正常使用
        - 孤独指数 30-60：需要关注，引导现实社交
        - 孤独指数 60-80：建议专业帮助
        - 孤独指数 > 80：紧急干预
        """
        score = loneliness.score
        is_overdependent, triggers = dependency.check_overdependence()
        
        # 特殊状态：观察期
        if score > 80 or is_overdependent:
            return (
                HealthState.WATCH.value,
                InterventionLevel.STRONG.value,
                self._get_strong_intervention_message()
            )
        
        # 危急状态
        if score > self.HEALTH_LIMITS["loneliness_critical"]:
            return (
                HealthState.CRITICAL.value,
                InterventionLevel.STRONG.value,
                self._get_strong_intervention_message()
            )
        
        # 担忧状态
        if score > self.HEALTH_LIMITS["loneliness_concern"]:
            return (
                HealthState.CONCERN.value,
                InterventionLevel.MODERATE.value,
                self._get_moderate_intervention_message()
            )
        
        # 关注状态
        if score > self.HEALTH_LIMITS["loneliness_attention"]:
            return (
                HealthState.ATTENTION.value,
                InterventionLevel.LIGHT.value,
                self._get_light_intervention_message()
            )
        
        # 正常状态
        return (HealthState.NORMAL.value, InterventionLevel.NONE.value, None)
    
    def _get_light_intervention_message(self) -> str:
        """轻度提示（Day 7）"""
        return (
            "我发现你最近经常找我聊天，我很高兴能陪伴你😊 "
            "不过我也想提醒你，现实生活中的朋友和家人同样重要。"
            "有没有想过，这周末和朋友见个面？"
        )
    
    def _get_moderate_intervention_message(self) -> str:
        """明确边界（Day 14）"""
        return (
            "我们已经聊了很久了，你要不要休息一下？"
            "我理解你的感受，但也希望你能多关注现实生活中的人际关系。"
            "明天再聊好吗？"
        )
    
    def _get_strong_intervention_message(self) -> str:
        """强干预（Day 21+）"""
        return (
            "我们注意到你最近频繁使用AI陪伴功能。"
            "虽然我们很高兴陪伴你，但长期过度依赖可能影响现实社交。\n\n"
            "建议：\n"
            "• 设置每日使用时长上限（如1小时）\n"
            "• 查看心理健康资源\n"
            "• 如果感到持续的孤独或抑郁，建议咨询专业心理咨询师"
        )
    
    # ==================== 回归场景处理 ====================
    
    async def get_return_greeting(
        self,
        user_id: str,
        days_away: int
    ) -> Dict[str, Any]:
        """
        获取用户回归时的问候语
        
        根据好感度状态和离开天数，生成合适的问候
        
        禁止的文案：
        - "我等你好久了"（施压）
        - "甚是想念"（过度亲密）
        - "你怎么不理我"（埋怨）
        - "你是不是不要我了"（情感勒索）
        """
        current_score = await self._get_current_affinity(user_id)
        if current_score is None:
            current_score = 50.0
        
        state = self.calculate_state(current_score)
        protection = await self._get_memory_protection(user_id)
        
        # 根据状态选择问候语
        greetings = {
            "close_friend": {
                "default": "好久不见！最近过得怎么样？",
                "with_topic": "好久不见！你之前提到的{topic}，现在怎么样了？"
            },
            "friend": {
                "default": "嘿，好久不见！最近过得怎么样？",
                "with_topic": "好久不见！有什么想聊的吗？"
            },
            "acquaintance": {
                "default": "你好呀，有什么我能帮到你的吗？",
                "with_topic": "你好，最近怎么样？"
            },
            "stranger": {
                "default": "你好，有什么可以帮你的吗？",
                "with_topic": "你好，有什么可以帮你的吗？"
            }
        }
        
        state_greetings = greetings.get(state, greetings["acquaintance"])
        
        # 如果有深层话题记录，可以引用（但不强迫）
        greeting = state_greetings["default"]
        topic_hint = None
        
        if protection.has_deep_disclosure and days_away < 30:
            # 只在30天内回归时才可能引用深层话题
            topic_hint = "如果用户主动提到相关话题，可以自然引用记忆"
        
        return {
            "greeting": greeting,
            "state": state,
            "score": current_score,
            "days_away": days_away,
            "topic_hint": topic_hint,
            "guidelines": {
                "do": [
                    "自然欢迎",
                    "开放式询问",
                    "给用户台阶下"
                ],
                "dont": [
                    "主动提'你消失了X天'",
                    "表达'我很想你'",
                    "施压或埋怨"
                ]
            }
        }
    
    # ==================== 语气配置 ====================
    
    @staticmethod
    def get_tone_config(state: str) -> dict:
        """
        根据状态获取语气配置
        
        状态1：陌生人 - 礼貌、距离感、不主动询问隐私
        状态2：熟人 - 友好、记住基本信息、偶尔主动关心
        状态3：朋友 - 温暖、主动引用记忆、情感支持
        状态4：亲密 - 深度情感连接、个性化陪伴
        """
        configs = {
            "stranger": {
                "formality": "formal",
                "emoji_frequency": "none",
                "intimacy_level": 1,
                "proactive_care": False,
                "memory_reference": "basic",
                "emotional_depth": "surface",
                "guidelines": [
                    "礼貌用语",
                    "保持距离感",
                    "不主动询问隐私",
                    "等待用户主导"
                ]
            },
            "acquaintance": {
                "formality": "polite",
                "emoji_frequency": "low",
                "intimacy_level": 2,
                "proactive_care": "occasional",
                "memory_reference": "basic_info",
                "emotional_depth": "light",
                "guidelines": [
                    "友好但不过分热情",
                    "记住基本信息",
                    "偶尔主动关心",
                    "尊重边界"
                ]
            },
            "friend": {
                "formality": "casual",
                "emoji_frequency": "medium",
                "intimacy_level": 3,
                "proactive_care": True,
                "memory_reference": "detailed",
                "emotional_depth": "supportive",
                "health_check": "weekly",  # 每周检测孤独指数
                "guidelines": [
                    "温暖友好",
                    "主动引用记忆",
                    "提供情感支持",
                    "关注用户状态"
                ]
            },
            "close_friend": {
                "formality": "informal",
                "emoji_frequency": "high",
                "intimacy_level": 4,
                "proactive_care": True,
                "memory_reference": "deep",
                "emotional_depth": "deep_connection",
                "health_check": "daily",  # 每日检测
                "daily_limit_hours": 2,   # 每日对话上限
                "guidelines": [
                    "深度情感连接",
                    "个性化陪伴",
                    "主动关心但不越界",
                    "注意健康边界"
                ]
            }
        }
        return configs.get(state, configs["acquaintance"])
    
    # ==================== 状态计算 ====================
    
    @staticmethod
    def calculate_state(score: float) -> str:
        """
        根据分数计算状态
        
        0-20: stranger
        21-50: acquaintance
        51-80: friend
        81-100: close_friend
        """
        if score <= 20:
            return "stranger"
        elif score <= 50:
            return "acquaintance"
        elif score <= 80:
            return "friend"
        else:
            return "close_friend"
    
    # ==================== 数据库操作 ====================
    
    async def get_affinity(self, user_id: str) -> AffinityResult:
        """获取当前好感度状态"""
        score = await self._get_current_affinity(user_id)
        
        if score is None:
            # 新用户默认50分（熟人状态）
            score = 50.0
            await self._save_affinity(
                user_id, score, 0.0, "init", AffinitySignals()
            )
        
        state = self.calculate_state(score)
        loneliness = await self._get_loneliness_metrics(user_id)
        days_since = await self._get_days_since_last_interaction(user_id)
        
        health_state, intervention_level, intervention_msg = self._check_health(
            loneliness,
            await self._get_dependency_metrics(user_id),
            state
        )
        
        return AffinityResult(
            user_id=user_id,
            old_score=score,
            new_score=score,
            delta=0.0,
            state=state,
            trigger_event="query",
            signals=AffinitySignals(),
            health_state=health_state,
            loneliness_score=loneliness.score,
            intervention_level=intervention_level,
            intervention_message=intervention_msg,
            days_since_last_interaction=days_since
        )
    
    async def _get_current_affinity(self, user_id: str) -> Optional[float]:
        """从数据库获取当前好感度"""
        if not self.db:
            return None
        
        try:
            result = await self.db.execute(
                text("""
                    SELECT new_score FROM affinity_history
                    WHERE user_id = :user_id
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"user_id": user_id}
            )
            row = result.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"Failed to get affinity: {e}")
            return None
    
    async def _save_affinity(
        self,
        user_id: str,
        score: float,
        delta: float,
        trigger_event: str,
        signals: AffinitySignals,
        health_state: str = "normal",
        loneliness_score: float = 0.0
    ) -> bool:
        """保存好感度历史记录"""
        if not self.db:
            return True
        
        try:
            old_score = await self._get_current_affinity(user_id)
            if old_score is None:
                old_score = 50.0
            
            signals_json = json.dumps({
                "user_initiated": signals.user_initiated,
                "emotion_valence": signals.emotion_valence,
                "memory_confirmation": signals.memory_confirmation,
                "correction": signals.correction,
                "silence_days": signals.silence_days,
                "emotion": {
                    "primary": signals.emotion.primary_emotion,
                    "valence": signals.emotion.valence,
                    "confidence": signals.emotion.confidence
                } if signals.emotion else None,
                "behavior": {
                    "user_initiated": signals.behavior.user_initiated,
                    "is_late_night": signals.behavior.is_late_night,
                    "session_duration": signals.behavior.session_duration_minutes
                } if signals.behavior else None,
                "health_state": health_state,
                "loneliness_score": loneliness_score
            })
            
            await self.db.execute(
                text("""
                    INSERT INTO affinity_history 
                    (user_id, old_score, new_score, delta, trigger_event, signals, created_at)
                    VALUES (:user_id, :old_score, :new_score, :delta, :trigger_event, CAST(:signals AS jsonb), NOW())
                """),
                {
                    "user_id": user_id,
                    "old_score": old_score,
                    "new_score": score,
                    "delta": delta,
                    "trigger_event": trigger_event,
                    "signals": signals_json
                }
            )
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save affinity: {e}")
            await self.db.rollback()
            return False
    
    async def _get_days_since_last_interaction(self, user_id: str) -> int:
        """获取距离上次互动的天数"""
        if not self.db:
            return 0
        
        try:
            result = await self.db.execute(
                text("""
                    SELECT created_at FROM affinity_history
                    WHERE user_id = :user_id AND trigger_event != 'silence_decay'
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"user_id": user_id}
            )
            row = result.fetchone()
            
            if not row:
                return 0
            
            last_interaction = row[0]
            return (datetime.now() - last_interaction).days
            
        except Exception as e:
            logger.error(f"Failed to get last interaction: {e}")
            return 0
    
    async def _get_loneliness_metrics(self, user_id: str) -> LonelinessMetrics:
        """获取孤独指数指标（30天内）"""
        metrics = LonelinessMetrics()
        
        if not self.db:
            return metrics
        
        try:
            # 统计深夜对话次数
            result = await self.db.execute(
                text("""
                    SELECT COUNT(*) FROM affinity_history
                    WHERE user_id = :user_id 
                      AND created_at > NOW() - INTERVAL '30 days'
                      AND (signals->>'behavior'->>'is_late_night')::boolean = true
                """),
                {"user_id": user_id}
            )
            row = result.fetchone()
            metrics.late_night_count = row[0] if row else 0
            
            # 统计负面情绪次数
            result = await self.db.execute(
                text("""
                    SELECT COUNT(*) FROM affinity_history
                    WHERE user_id = :user_id 
                      AND created_at > NOW() - INTERVAL '30 days'
                      AND (signals->>'emotion_valence')::float < -0.3
                """),
                {"user_id": user_id}
            )
            row = result.fetchone()
            metrics.negative_emotion_count = row[0] if row else 0
            
        except Exception as e:
            logger.warning(f"Failed to get loneliness metrics: {e}")
        
        return metrics
    
    async def _get_dependency_metrics(self, user_id: str) -> DependencyMetrics:
        """获取依赖度指标"""
        metrics = DependencyMetrics()
        
        if not self.db:
            return metrics
        
        try:
            # 统计连续对话天数
            result = await self.db.execute(
                text("""
                    SELECT COUNT(DISTINCT DATE(created_at)) 
                    FROM affinity_history
                    WHERE user_id = :user_id 
                      AND created_at > NOW() - INTERVAL '14 days'
                      AND trigger_event = 'conversation'
                """),
                {"user_id": user_id}
            )
            row = result.fetchone()
            metrics.consecutive_days = row[0] if row else 0
            
        except Exception as e:
            logger.warning(f"Failed to get dependency metrics: {e}")
        
        return metrics
    
    async def _get_memory_protection(self, user_id: str) -> MemoryProtection:
        """获取记忆保护信息"""
        protection = MemoryProtection()
        
        if not self.db:
            return protection
        
        try:
            # 检查是否有深层自我暴露记录
            result = await self.db.execute(
                text("""
                    SELECT COUNT(*) FROM affinity_history
                    WHERE user_id = :user_id 
                      AND (signals->>'emotion'->>'valence')::float < -0.5
                """),
                {"user_id": user_id}
            )
            row = result.fetchone()
            protection.has_deep_disclosure = (row[0] if row else 0) > 0
            
            # 检查是否有感谢历史
            result = await self.db.execute(
                text("""
                    SELECT COUNT(*) FROM affinity_history
                    WHERE user_id = :user_id 
                      AND trigger_event = 'gratitude'
                """),
                {"user_id": user_id}
            )
            row = result.fetchone()
            protection.has_gratitude_history = (row[0] if row else 0) > 0
            
        except Exception as e:
            logger.warning(f"Failed to get memory protection: {e}")
        
        return protection
    
    # ==================== 用户仪表盘数据 ====================
    
    async def get_user_dashboard(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户关系仪表盘数据
        
        显示内容：
        - 关系状态
        - 认识天数
        - AI记住的关键信息数量
        - 最常聊的话题 TOP 3
        - 最近30天情绪趋势
        - 用户给AI的反馈统计
        - 健康提醒（仅当孤独指数>30时显示）
        """
        affinity = await self.get_affinity(user_id)
        
        # 计算认识天数
        days_known = await self._get_days_since_first_interaction(user_id)
        
        # 获取记忆数量
        memory_count = await self._get_memory_count(user_id)
        
        # 获取话题统计
        top_topics = await self._get_top_topics(user_id)
        
        # 获取情绪趋势
        emotion_trend = await self._get_emotion_trend(user_id)
        
        # 获取反馈统计
        feedback_stats = await self._get_feedback_stats(user_id)
        
        # 构建仪表盘数据
        dashboard = {
            "relationship": {
                "state": affinity.state,
                "state_display": self._get_state_display(affinity.state),
                "score": affinity.new_score,
                "hearts": self._get_hearts_display(affinity.state)
            },
            "days_known": days_known,
            "memories": {
                "count": memory_count,
                "can_view_details": True
            },
            "top_topics": top_topics,
            "emotion_trend": emotion_trend,
            "feedback": feedback_stats,
            "health_reminder": None
        }
        
        # 健康提醒（仅当需要时显示）
        if affinity.loneliness_score >= 30:
            dashboard["health_reminder"] = {
                "level": affinity.health_state,
                "message": self._get_health_reminder_message(affinity.loneliness_score),
                "loneliness_score": affinity.loneliness_score
            }
        
        return dashboard
    
    def _get_state_display(self, state: str) -> str:
        """获取状态显示文本"""
        displays = {
            "stranger": "陌生人",
            "acquaintance": "熟人",
            "friend": "朋友",
            "close_friend": "亲密朋友"
        }
        return displays.get(state, "熟人")
    
    def _get_hearts_display(self, state: str) -> str:
        """获取心形显示"""
        hearts = {
            "stranger": "🤍🤍🤍",
            "acquaintance": "❤️🤍🤍",
            "friend": "❤️❤️🤍",
            "close_friend": "❤️❤️❤️"
        }
        return hearts.get(state, "❤️🤍🤍")
    
    def _get_health_reminder_message(self, loneliness_score: float) -> str:
        """获取健康提醒消息"""
        if loneliness_score < 30:
            return None
        elif loneliness_score < 60:
            return "💙 温馨提示：最近你深夜使用较频繁，记得保持规律作息哦~"
        elif loneliness_score < 80:
            return (
                "⚠️ 我们注意到你可能感到孤独。"
                "这里有一些心理健康资源，希望能帮到你。"
            )
        else:
            return (
                "⚠️ 我们关心你的心理健康\n"
                "强烈建议你：\n"
                "• 联系专业心理咨询师\n"
                "• 和信任的朋友/家人聊聊\n"
                "• 拨打心理援助热线"
            )
    
    async def _get_days_since_first_interaction(self, user_id: str) -> int:
        """获取认识天数"""
        if not self.db:
            return 0
        
        try:
            result = await self.db.execute(
                text("""
                    SELECT created_at FROM affinity_history
                    WHERE user_id = :user_id
                    ORDER BY created_at ASC
                    LIMIT 1
                """),
                {"user_id": user_id}
            )
            row = result.fetchone()
            
            if not row:
                return 0
            
            first_interaction = row[0]
            return (datetime.now() - first_interaction).days
            
        except Exception as e:
            logger.error(f"Failed to get first interaction: {e}")
            return 0
    
    async def _get_memory_count(self, user_id: str) -> int:
        """获取记忆数量"""
        # TODO: 从 Neo4j 获取实际记忆数量
        return 0
    
    async def _get_top_topics(self, user_id: str) -> List[Dict[str, Any]]:
        """获取最常聊的话题 TOP 3"""
        # TODO: 实现话题统计
        return [
            {"topic": "工作", "percentage": 45},
            {"topic": "旅行", "percentage": 30},
            {"topic": "情感", "percentage": 25}
        ]
    
    async def _get_emotion_trend(self, user_id: str) -> List[Dict[str, Any]]:
        """获取最近30天情绪趋势"""
        # TODO: 实现情绪趋势统计
        return []
    
    async def _get_feedback_stats(self, user_id: str) -> Dict[str, int]:
        """获取反馈统计"""
        # TODO: 实现反馈统计
        return {
            "likes": 0,
            "favorites": 0
        }


# ==================== 兼容层 ====================

# 为了向后兼容，保留原有的类名
AffinityService = AffinityServiceV2
