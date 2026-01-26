"""好感度服务"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from dataclasses import dataclass
import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class AffinitySignals:
    """好感度信号"""
    user_initiated: bool = False
    emotion_valence: float = 0.0  # [-1, 1]
    memory_confirmation: bool = False
    correction: bool = False
    silence_days: int = 0


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


class AffinityService:
    """
    好感度服务 - 管理情感倾向
    
    好感度范围: [0, 1] (统一存储尺度)
    状态映射:
    - stranger: score < 0.2
    - acquaintance: 0.2 <= score < 0.4
    - friend: 0.4 <= score < 0.6
    - close_friend: 0.6 <= score < 0.8
    - best_friend: score >= 0.8
    
    Property 3: 好感度分数边界不变量
    Property 4: 好感度状态映射正确性
    Property 10: 好感度变化可追溯性
    
    注意：内部计算仍使用 -1~1，但存储时统一转换为 0~1
    """
    
    # 信号权重配置（降低增长速度，避免亲密度过快上升）
    SIGNAL_WEIGHTS = {
        "user_initiated": 0.01,       # 降低：每条消息 +1%（原 5%）
        "positive_emotion": 0.005,    # 降低：正面情绪 +0.5%（原 2%）
        "memory_confirmation": 0.01,  # 降低：记忆确认 +1%（原 3%）
        "correction": -0.02,          # 保持：纠正 -2%
        "negative_emotion": -0.01,    # 保持：负面情绪 -1%
        "daily_decay": 0.005          # 降低：每日衰减 0.5%（原 1%）
    }
    
    def __init__(self, db_session: AsyncSession = None):
        self.db = db_session
    
    @staticmethod
    def _normalize_score(raw_score: float) -> float:
        """
        归一化分数到 0~1 范围
        
        自动识别并转换不同尺度的历史数据：
        - 如果 raw_score > 1.0：按 0~100 处理 → /100
        - 如果 raw_score < 0：按 -1~1 处理 → (x+1)/2
        - 否则：已经是 0~1
        
        Args:
            raw_score: 原始分数
            
        Returns:
            归一化后的分数 (0~1)
        """
        if raw_score > 1.0:
            # V2 历史数据 (0~100)
            return min(raw_score / 100.0, 1.0)
        elif raw_score < 0:
            # 旧版历史数据 (-1~1)
            return (raw_score + 1.0) / 2.0
        else:
            # 已经是 0~1
            return raw_score
    
    @staticmethod
    def _legacy_to_01(legacy_score: float) -> float:
        """
        将旧版 -1~1 分数转换为 0~1
        
        Args:
            legacy_score: 旧版分数 (-1~1)
            
        Returns:
            0~1 分数
        """
        return (legacy_score + 1.0) / 2.0
    
    @staticmethod
    def _01_to_legacy(score_01: float) -> float:
        """
        将 0~1 分数转换为旧版 -1~1（用于内部计算）
        
        Args:
            score_01: 0~1 分数
            
        Returns:
            旧版分数 (-1~1)
        """
        return score_01 * 2.0 - 1.0
    
    async def update_affinity(
        self,
        user_id: str,
        signals: AffinitySignals,
        trigger_event: str = "conversation"
    ) -> AffinityResult:
        """
        更新好感度分数
        
        Property 3: 好感度分数边界不变量
        Property 10: 好感度变化可追溯性
        
        Args:
            user_id: 用户 ID
            signals: 好感度信号
            trigger_event: 触发事件
            
        Returns:
            AffinityResult: 新分数、状态和变化记录
        """
        # 获取当前分数（已归一化为 0~1）
        current_01 = await self._get_current_affinity(user_id)
        old_score_01 = current_01 if current_01 is not None else 0.5
        
        # 转换为旧版 -1~1 进行计算（保持旧版逻辑不变）
        old_score_legacy = self._01_to_legacy(old_score_01)
        
        # 计算变化量（旧版逻辑）
        delta_legacy = self._calculate_delta(signals)
        
        # 应用变化（确保边界 -1~1）
        new_score_legacy = float(np.clip(old_score_legacy + delta_legacy, -1.0, 1.0))
        
        # 转换回 0~1 存储
        new_score_01 = self._legacy_to_01(new_score_legacy)
        delta_01 = new_score_01 - old_score_01
        
        # 计算状态
        state = self.calculate_state(new_score_01)
        
        # 保存到数据库（存储 0~1）
        await self._save_affinity(user_id, new_score_01, delta_01, trigger_event, signals)
        
        result = AffinityResult(
            user_id=user_id,
            old_score=old_score_01,
            new_score=new_score_01,
            delta=delta_01,
            state=state,
            trigger_event=trigger_event,
            signals=signals
        )
        
        logger.info(f"Affinity updated for {user_id}: {old_score_01:.3f} -> {new_score_01:.3f} ({state})")
        return result
    
    def _calculate_delta(self, signals: AffinitySignals) -> float:
        """
        计算好感度变化量
        
        基于 requirements.md 中的公式
        """
        delta = 0.0
        
        # 正向信号
        if signals.user_initiated:
            delta += self.SIGNAL_WEIGHTS["user_initiated"]
        
        if signals.emotion_valence > 0:
            delta += self.SIGNAL_WEIGHTS["positive_emotion"] * signals.emotion_valence
        
        if signals.memory_confirmation:
            delta += self.SIGNAL_WEIGHTS["memory_confirmation"]
        
        # 负向信号
        if signals.correction:
            delta += self.SIGNAL_WEIGHTS["correction"]
        
        if signals.emotion_valence < -0.5:
            delta += self.SIGNAL_WEIGHTS["negative_emotion"]
        
        # 时间衰减
        decay = self.SIGNAL_WEIGHTS["daily_decay"] * signals.silence_days
        
        return delta - decay
    
    async def _get_current_affinity(self, user_id: str) -> Optional[float]:
        """从数据库获取当前好感度（归一化为 0~1）"""
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
            if row:
                raw_score = row[0]
                # 自动归一化历史数据
                return self._normalize_score(raw_score)
            return None
        except Exception as e:
            logger.error(f"Failed to get affinity: {e}")
            return None
    
    async def _save_affinity(
        self,
        user_id: str,
        score: float,
        delta: float,
        trigger_event: str,
        signals: AffinitySignals
    ) -> bool:
        """保存好感度历史记录（存储 0~1 分数）"""
        if not self.db:
            return True
        
        import json
        
        try:
            # 获取旧分数用于 old_score 字段（已归一化）
            old_score = await self._get_current_affinity(user_id)
            if old_score is None:
                old_score = 0.5
            
            # 确保存储的分数在 0~1 范围
            score = float(np.clip(score, 0.0, 1.0))
            
            # 将 signals 转为 JSON 字符串
            signals_json = json.dumps({
                "user_initiated": signals.user_initiated,
                "emotion_valence": signals.emotion_valence,
                "memory_confirmation": signals.memory_confirmation,
                "correction": signals.correction,
                "silence_days": signals.silence_days,
                "source": "legacy",  # 标记数据来源
                "scale": "0-1"  # 标记存储尺度
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
    
    async def get_affinity(self, user_id: str) -> AffinityResult:
        """获取当前好感度状态"""
        score = await self._get_current_affinity(user_id)
        
        if score is None:
            # 新用户默认值
            score = 0.5
            await self._save_affinity(
                user_id, score, 0.0, "init", AffinitySignals()
            )
        
        return AffinityResult(
            user_id=user_id,
            old_score=score,
            new_score=score,
            delta=0.0,
            state=self.calculate_state(score),
            trigger_event="query",
            signals=AffinitySignals()
        )
    
    async def get_affinity_history(
        self,
        user_id: str,
        days: int = 30
    ) -> List[AffinityResult]:
        """
        获取好感度变化历史（所有分数归一化为 0~1）
        
        Property 10: 好感度变化可追溯性
        """
        if not self.db:
            return []
        
        try:
            # 注意：INTERVAL 不能用参数化，需要直接构建 SQL
            # 但 days 是整数，安全
            result = await self.db.execute(
                text(f"""
                    SELECT old_score, new_score, delta, trigger_event, signals, created_at
                    FROM affinity_history
                    WHERE user_id = :user_id 
                      AND created_at > NOW() - INTERVAL '{days} days'
                    ORDER BY created_at DESC
                """),
                {"user_id": user_id}
            )
            
            history = []
            
            for row in result.fetchall():
                old_score, new_score, delta, trigger_event, signals_dict, created_at = row
                
                # 归一化历史分数
                old_score_01 = self._normalize_score(old_score)
                new_score_01 = self._normalize_score(new_score)
                
                signals = AffinitySignals(
                    user_initiated=signals_dict.get("user_initiated", False),
                    emotion_valence=signals_dict.get("emotion_valence", 0.0),
                    memory_confirmation=signals_dict.get("memory_confirmation", False),
                    correction=signals_dict.get("correction", False),
                    silence_days=signals_dict.get("silence_days", 0)
                )
                
                history.append(AffinityResult(
                    user_id=user_id,
                    old_score=old_score_01,
                    new_score=new_score_01,
                    delta=new_score_01 - old_score_01,  # 重新计算 delta
                    state=self.calculate_state(new_score_01),
                    trigger_event=trigger_event,
                    signals=signals
                ))
            
            return history
            
        except Exception as e:
            logger.error(f"Failed to get affinity history: {e}")
            return []
    
    async def apply_silence_decay(self, user_id: str) -> Optional[AffinityResult]:
        """
        应用沉默衰减（用户长时间未互动）
        
        由 Celery Beat 每日调用
        """
        if not self.db:
            return None
        
        try:
            # 获取最后互动时间
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
                return None
            
            last_interaction = row[0]
            silence_days = (datetime.now() - last_interaction).days
            
            if silence_days > 0:
                signals = AffinitySignals(silence_days=silence_days)
                return await self.update_affinity(
                    user_id, signals, trigger_event="silence_decay"
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to apply silence decay: {e}")
            return None
    
    @staticmethod
    def calculate_state(score: float) -> str:
        """
        根据分数计算状态（0~1 尺度）
        
        Property 4: 好感度状态映射正确性
        
        状态映射：
        - stranger: 0-0.2
        - acquaintance: 0.2-0.4
        - friend: 0.4-0.6
        - close_friend: 0.6-0.8
        - best_friend: 0.8-1.0
        """
        if score < 0.2:
            return "stranger"
        elif score < 0.4:
            return "acquaintance"
        elif score < 0.6:
            return "friend"
        elif score < 0.8:
            return "close_friend"
        else:
            return "best_friend"
    
    @staticmethod
    def get_tone_config(state: str) -> dict:
        """根据状态获取语气配置"""
        configs = {
            "stranger": {
                "formality": "formal",
                "emoji_frequency": "low",
                "intimacy_level": 1
            },
            "acquaintance": {
                "formality": "polite",
                "emoji_frequency": "medium",
                "intimacy_level": 2
            },
            "friend": {
                "formality": "casual",
                "emoji_frequency": "medium",
                "intimacy_level": 3
            },
            "close_friend": {
                "formality": "informal",
                "emoji_frequency": "high",
                "intimacy_level": 4
            },
            "best_friend": {
                "formality": "intimate",
                "emoji_frequency": "high",
                "intimacy_level": 5
            }
        }
        return configs.get(state, configs["acquaintance"])
