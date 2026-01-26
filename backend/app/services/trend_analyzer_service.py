"""
趋势分析服务 - 基于热度信号计算和更新趋势分数

核心功能：
1. 计算趋势分数（0-100）基于多个信号
2. 将分数映射到趋势等级（新兴/上升/热门/巅峰/衰退）
3. 重新计算所有活跃表情包的分数
4. 识别衰退表情包（分数<30持续7+天）

MVP阶段简化：
- 使用基于平台popularity_score和时间衰减的简化公式
- 阶段2将实现完整公式（提及频率、互动指标、传播速度）

设计原则：
- 趋势等级映射：0-30新兴、30-60上升、60-85热门、85-100巅峰
- 衰退检测：分数<30持续7天
- 时间衰减：新内容（<24小时）获得加成
"""
import logging
import math
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meme import Meme

logger = logging.getLogger(__name__)


class TrendAnalyzerService:
    """
    趋势分析服务
    
    负责计算和更新表情包的趋势分数和等级
    """
    
    # 趋势等级阈值
    TREND_LEVEL_THRESHOLDS = {
        "emerging": (0, 30),      # 新兴：0-30
        "rising": (30, 60),       # 上升：30-60
        "hot": (60, 85),          # 热门：60-85
        "peak": (85, 100),        # 巅峰：85-100
    }
    
    # 衰退检测阈值
    DECLINING_SCORE_THRESHOLD = 30  # 分数低于此值视为衰退
    DECLINING_DAYS_THRESHOLD = 7    # 持续天数
    
    def __init__(self, db_session: AsyncSession):
        """
        初始化趋势分析服务
        
        Args:
            db_session: 异步数据库会话
        """
        self.db = db_session
    
    # ==================== 趋势分数计算 ====================
    
    async def calculate_trend_score(self, meme: Meme) -> float:
        """
        从多个信号计算趋势分数（0-100）
        
        MVP阶段简化公式：
        trend_score = popularity_score * time_decay_boost
        
        其中：
        - popularity_score: 平台提供的初始热度分数（0-100）
        - time_decay_boost: 时间衰减加成
          * 如果年龄 < 24小时：boost = 1.2（新内容加成）
          * 否则：boost = exp(-0.1 * 首次发现天数)
        
        阶段2完整公式：
        trend_score = (
            0.3 * 提及频率标准化 +
            0.2 * 时间衰减加成 +
            0.3 * 互动分数标准化 +
            0.2 * 传播速度标准化
        ) * 100
        
        Args:
            meme: 表情包对象
        
        Returns:
            float: 趋势分数（0-100）
        """
        try:
            # 获取基础热度分数
            base_score = meme.popularity_score
            
            # 计算时间衰减加成
            time_boost = self._calculate_time_decay_boost(meme)
            
            # MVP简化公式
            trend_score = base_score * time_boost
            
            # 确保分数在0-100范围内
            trend_score = max(0.0, min(100.0, trend_score))
            
            logger.debug(
                f"Calculated trend score for meme {meme.id}: "
                f"base={base_score:.1f}, boost={time_boost:.2f}, "
                f"final={trend_score:.1f}"
            )
            
            return trend_score
            
        except Exception as e:
            logger.error(f"Failed to calculate trend score for meme {meme.id}: {e}")
            # 返回默认分数
            return 0.0
    
    def _calculate_time_decay_boost(self, meme: Meme) -> float:
        """
        计算时间衰减加成
        
        新内容（<24小时）获得1.2倍加成
        旧内容按指数衰减：exp(-0.1 * 天数)
        
        Args:
            meme: 表情包对象
        
        Returns:
            float: 时间衰减加成系数
        """
        now = datetime.utcnow()
        age = now - meme.first_seen_at
        age_hours = age.total_seconds() / 3600
        age_days = age.total_seconds() / 86400
        
        if age_hours < 24:
            # 新内容加成
            boost = 1.2
            logger.debug(f"Meme {meme.id} is fresh ({age_hours:.1f}h), boost=1.2")
        else:
            # 指数衰减
            boost = math.exp(-0.1 * age_days)
            logger.debug(
                f"Meme {meme.id} is {age_days:.1f} days old, "
                f"boost={boost:.3f}"
            )
        
        return boost
    
    # ==================== 趋势等级映射 ====================
    
    def determine_trend_level(self, score: float) -> str:
        """
        将分数映射到趋势等级
        
        映射规则：
        - 0-30: emerging（新兴）
        - 30-60: rising（上升）
        - 60-85: hot（热门）
        - 85-100: peak（巅峰）
        
        注意：declining（衰退）状态由identify_declining_memes()单独判断
        
        Args:
            score: 趋势分数（0-100）
        
        Returns:
            str: 趋势等级
        """
        # 确保分数在有效范围内
        score = max(0.0, min(100.0, score))
        
        # 映射到等级
        if score < 30:
            return "emerging"
        elif score < 60:
            return "rising"
        elif score < 85:
            return "hot"
        else:
            return "peak"
    
    # ==================== 批量更新 ====================
    
    async def update_all_trend_scores(self) -> int:
        """
        重新计算所有活跃表情包的分数
        
        活跃表情包定义：status为'approved'且trend_level不为'declining'
        
        Returns:
            int: 更新的表情包数量
        """
        logger.info("Starting to update all trend scores...")
        
        try:
            # 查询所有活跃表情包
            query = select(Meme).where(
                and_(
                    Meme.status == "approved",
                    Meme.trend_level != "declining"
                )
            )
            
            result = await self.db.execute(query)
            active_memes = result.scalars().all()
            
            logger.info(f"Found {len(active_memes)} active memes to update")
            
            # 更新每个表情包的趋势分数
            updated_count = 0
            for meme in active_memes:
                try:
                    # 计算新分数
                    new_score = await self.calculate_trend_score(meme)
                    
                    # 确定新等级
                    new_level = self.determine_trend_level(new_score)
                    
                    # 更新数据库
                    meme.trend_score = new_score
                    meme.trend_level = new_level
                    meme.last_updated_at = datetime.utcnow()
                    
                    updated_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to update meme {meme.id}: {e}")
                    continue
            
            # 提交所有更新
            await self.db.commit()
            
            logger.info(
                f"Trend score update complete: {updated_count}/{len(active_memes)} "
                "memes updated"
            )
            
            return updated_count
            
        except Exception as e:
            logger.error(f"Failed to update trend scores: {e}")
            await self.db.rollback()
            return 0
    
    # ==================== 衰退检测 ====================
    
    async def identify_declining_memes(self) -> List[Meme]:
        """
        查找分数<30持续7+天的表情包
        
        衰退条件：
        1. 当前trend_score < 30
        2. trend_level不为'declining'（避免重复标记）
        3. last_updated_at距今超过7天（说明分数持续低迷）
        
        Returns:
            List[Meme]: 符合衰退条件的表情包列表
        """
        logger.info("Identifying declining memes...")
        
        try:
            # 计算阈值日期
            threshold_date = datetime.utcnow() - timedelta(
                days=self.DECLINING_DAYS_THRESHOLD
            )
            
            # 查询符合条件的表情包
            query = select(Meme).where(
                and_(
                    Meme.status == "approved",
                    Meme.trend_score < self.DECLINING_SCORE_THRESHOLD,
                    Meme.trend_level != "declining",
                    Meme.last_updated_at <= threshold_date
                )
            )
            
            result = await self.db.execute(query)
            declining_memes = result.scalars().all()
            
            logger.info(
                f"Found {len(declining_memes)} declining memes "
                f"(score < {self.DECLINING_SCORE_THRESHOLD} for "
                f"{self.DECLINING_DAYS_THRESHOLD}+ days)"
            )
            
            # 更新这些表情包的trend_level为'declining'
            for meme in declining_memes:
                meme.trend_level = "declining"
                meme.last_updated_at = datetime.utcnow()
                logger.info(
                    f"Marked meme {meme.id} as declining "
                    f"(score={meme.trend_score:.1f})"
                )
            
            # 提交更新
            await self.db.commit()
            
            return list(declining_memes)
            
        except Exception as e:
            logger.error(f"Failed to identify declining memes: {e}")
            await self.db.rollback()
            return []
    
    # ==================== 辅助方法 ====================
    
    async def get_trend_statistics(self) -> dict:
        """
        获取趋势统计信息
        
        Returns:
            dict: 统计信息
        """
        try:
            stats = {}
            
            # 按趋势等级统计
            for level in ["emerging", "rising", "hot", "peak", "declining"]:
                query = select(Meme).where(
                    and_(
                        Meme.status == "approved",
                        Meme.trend_level == level
                    )
                )
                result = await self.db.execute(query)
                count = len(result.scalars().all())
                stats[f"{level}_count"] = count
            
            # 平均趋势分数
            query = select(Meme).where(Meme.status == "approved")
            result = await self.db.execute(query)
            approved_memes = result.scalars().all()
            
            if approved_memes:
                avg_score = sum(m.trend_score for m in approved_memes) / len(approved_memes)
                stats["avg_trend_score"] = round(avg_score, 2)
                stats["total_approved"] = len(approved_memes)
            else:
                stats["avg_trend_score"] = 0.0
                stats["total_approved"] = 0
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get trend statistics: {e}")
            return {}
