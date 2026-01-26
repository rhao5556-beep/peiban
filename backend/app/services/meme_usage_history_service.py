"""
表情包使用历史服务

跟踪表情包使用和用户反馈：
- 记录表情包在对话中的使用
- 记录用户反应（喜欢/忽略/不喜欢）
- 查询最近使用历史
- 计算接受率

设计原则：
- 完整记录：所有使用都包含必需字段（user_id, meme_id, conversation_id, used_at）
- 反馈跟踪：支持三种反应类型（liked, ignored, disliked）
- 时间窗口查询：支持灵活的时间范围过滤
- 统计分析：计算接受率用于监控
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID
from sqlalchemy import select, update, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meme_usage_history import MemeUsageHistory

logger = logging.getLogger(__name__)


class MemeUsageHistoryService:
    """
    表情包使用历史服务
    
    负责跟踪表情包使用和用户反馈
    """
    
    # 有效的反应类型
    VALID_REACTIONS = ["liked", "ignored", "disliked"]
    
    def __init__(self, db_session: AsyncSession):
        """
        初始化表情包使用历史服务
        
        Args:
            db_session: 异步数据库会话
        """
        self.db = db_session
    
    async def record_usage(
        self,
        user_id: UUID,
        meme_id: UUID,
        conversation_id: UUID
    ) -> MemeUsageHistory:
        """
        记录表情包在对话中的使用
        
        Args:
            user_id: 用户ID
            meme_id: 表情包ID
            conversation_id: 对话会话ID
        
        Returns:
            创建的MemeUsageHistory对象
        
        Raises:
            ValueError: 如果必需字段缺失
        """
        try:
            # 验证必需字段
            if not user_id:
                raise ValueError("user_id is required")
            if not meme_id:
                raise ValueError("meme_id is required")
            if not conversation_id:
                raise ValueError("conversation_id is required")
            
            # 创建使用历史记录
            usage = MemeUsageHistory(
                user_id=user_id,
                meme_id=meme_id,
                conversation_id=conversation_id,
                used_at=datetime.utcnow(),
                user_reaction=None  # 初始无反应
            )
            
            self.db.add(usage)
            await self.db.commit()
            await self.db.refresh(usage)
            
            logger.info(
                f"Recorded meme usage: usage_id={usage.id}, "
                f"user_id={user_id}, meme_id={meme_id}"
            )
            
            return usage
            
        except ValueError as e:
            logger.warning(f"Failed to record meme usage: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error recording meme usage: {e}")
            await self.db.rollback()
            raise
    
    async def record_feedback(
        self,
        usage_id: UUID,
        reaction: str
    ) -> bool:
        """
        记录用户对表情包使用的反应
        
        Args:
            usage_id: 使用历史记录ID
            reaction: 用户反应（liked, ignored, disliked）
        
        Returns:
            是否更新成功
        
        Raises:
            ValueError: 如果反应类型无效
        """
        try:
            # 验证反应类型
            if reaction not in self.VALID_REACTIONS:
                raise ValueError(
                    f"Invalid reaction: {reaction}. "
                    f"Valid reactions: {self.VALID_REACTIONS}"
                )
            
            # 获取使用历史记录
            result = await self.db.execute(
                select(MemeUsageHistory).where(MemeUsageHistory.id == usage_id)
            )
            usage = result.scalar_one_or_none()
            
            if not usage:
                logger.warning(f"Usage history not found: {usage_id}")
                return False
            
            # 更新反应
            usage.user_reaction = reaction
            
            await self.db.commit()
            
            logger.info(
                f"Recorded feedback: usage_id={usage_id}, "
                f"reaction={reaction}"
            )
            
            return True
            
        except ValueError as e:
            logger.warning(f"Failed to record feedback: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error recording feedback: {e}")
            await self.db.rollback()
            return False
    
    async def get_recent_usage(
        self,
        user_id: UUID,
        hours: int = 24
    ) -> List[MemeUsageHistory]:
        """
        获取用户在指定时间窗口内使用的表情包
        
        Args:
            user_id: 用户ID
            hours: 时间窗口（小时），默认24小时
        
        Returns:
            使用历史记录列表，按时间降序排序
        """
        try:
            # 计算时间阈值
            threshold_time = datetime.utcnow() - timedelta(hours=hours)
            
            # 查询最近使用
            query = select(MemeUsageHistory).where(
                and_(
                    MemeUsageHistory.user_id == user_id,
                    MemeUsageHistory.used_at >= threshold_time
                )
            ).order_by(MemeUsageHistory.used_at.desc())
            
            result = await self.db.execute(query)
            usage_list = result.scalars().all()
            
            logger.debug(
                f"Retrieved {len(usage_list)} recent usages for user {user_id} "
                f"(past {hours} hours)"
            )
            
            return list(usage_list)
            
        except Exception as e:
            logger.error(f"Failed to get recent usage: {e}")
            return []
    
    async def calculate_acceptance_rate(self) -> float:
        """
        计算整体表情包接受率（喜欢 / 总数）
        
        接受率定义：
        - 分子：user_reaction = 'liked' 的记录数
        - 分母：所有有反应的记录数（liked + ignored + disliked）
        - 如果没有反应记录，返回0.0
        
        Returns:
            接受率（0.0-1.0），如果没有数据则返回0.0
        """
        try:
            # 查询所有有反应的记录
            result = await self.db.execute(
                select(MemeUsageHistory).where(
                    MemeUsageHistory.user_reaction.isnot(None)
                )
            )
            all_reactions = result.scalars().all()
            
            if not all_reactions:
                logger.debug("No feedback data available for acceptance rate")
                return 0.0
            
            # 统计喜欢的数量
            liked_count = sum(
                1 for usage in all_reactions
                if usage.user_reaction == "liked"
            )
            
            total_count = len(all_reactions)
            acceptance_rate = liked_count / total_count if total_count > 0 else 0.0
            
            logger.debug(
                f"Calculated acceptance rate: {acceptance_rate:.2%} "
                f"({liked_count}/{total_count})"
            )
            
            return acceptance_rate
            
        except Exception as e:
            logger.error(f"Failed to calculate acceptance rate: {e}")
            return 0.0
    
    async def get_usage_by_id(self, usage_id: UUID) -> Optional[MemeUsageHistory]:
        """
        根据ID获取使用历史记录
        
        Args:
            usage_id: 使用历史记录ID
        
        Returns:
            使用历史记录对象，如果不存在则返回None
        """
        try:
            result = await self.db.execute(
                select(MemeUsageHistory).where(MemeUsageHistory.id == usage_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get usage by id: {e}")
            return None
    
    async def get_meme_usage_count(
        self,
        meme_id: UUID,
        hours: Optional[int] = None
    ) -> int:
        """
        获取表情包的使用次数
        
        Args:
            meme_id: 表情包ID
            hours: 可选时间窗口（小时），如果不指定则统计所有时间
        
        Returns:
            使用次数
        """
        try:
            query = select(func.count(MemeUsageHistory.id)).where(
                MemeUsageHistory.meme_id == meme_id
            )
            
            # 添加时间过滤
            if hours:
                threshold_time = datetime.utcnow() - timedelta(hours=hours)
                query = query.where(MemeUsageHistory.used_at >= threshold_time)
            
            result = await self.db.execute(query)
            count = result.scalar_one()
            
            return count
            
        except Exception as e:
            logger.error(f"Failed to get meme usage count: {e}")
            return 0
    
    async def get_user_reaction_stats(
        self,
        user_id: Optional[UUID] = None
    ) -> dict:
        """
        获取用户反应统计
        
        Args:
            user_id: 可选用户ID，如果不指定则统计所有用户
        
        Returns:
            统计字典，包含liked、ignored、disliked的数量和百分比
        """
        try:
            # 构建查询
            query = select(MemeUsageHistory).where(
                MemeUsageHistory.user_reaction.isnot(None)
            )
            
            if user_id:
                query = query.where(MemeUsageHistory.user_id == user_id)
            
            result = await self.db.execute(query)
            reactions = result.scalars().all()
            
            if not reactions:
                return {
                    "total": 0,
                    "liked": 0,
                    "ignored": 0,
                    "disliked": 0,
                    "liked_percentage": 0.0,
                    "ignored_percentage": 0.0,
                    "disliked_percentage": 0.0
                }
            
            # 统计各类反应
            liked = sum(1 for r in reactions if r.user_reaction == "liked")
            ignored = sum(1 for r in reactions if r.user_reaction == "ignored")
            disliked = sum(1 for r in reactions if r.user_reaction == "disliked")
            total = len(reactions)
            
            stats = {
                "total": total,
                "liked": liked,
                "ignored": ignored,
                "disliked": disliked,
                "liked_percentage": round(liked / total * 100, 2) if total > 0 else 0.0,
                "ignored_percentage": round(ignored / total * 100, 2) if total > 0 else 0.0,
                "disliked_percentage": round(disliked / total * 100, 2) if total > 0 else 0.0
            }
            
            logger.debug(
                f"User reaction stats {'for user ' + str(user_id) if user_id else 'overall'}: "
                f"liked={liked}, ignored={ignored}, disliked={disliked}"
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get user reaction stats: {e}")
            return {
                "total": 0,
                "liked": 0,
                "ignored": 0,
                "disliked": 0,
                "liked_percentage": 0.0,
                "ignored_percentage": 0.0,
                "disliked_percentage": 0.0
            }
