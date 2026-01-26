"""
内容池管理服务

管理表情包生命周期和数据库操作：
- 创建候选表情包
- 更新表情包状态
- 查询已批准表情包
- 增加使用计数
- 归档过时表情包

设计原则：
- 状态转换：candidate → approved/rejected/flagged → archived
- 查询优化：使用索引进行高效过滤
- 软删除：保留已归档表情包用于分析
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meme import Meme

logger = logging.getLogger(__name__)


class ContentPoolManagerService:
    """
    内容池管理服务
    
    负责表情包的CRUD操作和生命周期管理
    """
    
    # 有效的状态转换
    VALID_STATUS_TRANSITIONS = {
        "candidate": ["approved", "rejected", "flagged"],
        "approved": ["archived", "flagged"],
        "rejected": ["archived"],
        "flagged": ["approved", "rejected", "archived"],
        "archived": []  # 归档后不可转换
    }
    
    def __init__(self, db_session: AsyncSession):
        """
        初始化内容池管理服务
        
        Args:
            db_session: 异步数据库会话
        """
        self.db = db_session
    
    async def create_meme_candidate(
        self,
        text_description: str,
        source_platform: str,
        content_hash: str,
        image_url: Optional[str] = None,
        category: Optional[str] = None,
        popularity_score: float = 0.0,
        original_source_url: Optional[str] = None
    ) -> Meme:
        """
        创建状态为"候选"的新表情包记录
        
        Args:
            text_description: 表情包文本描述（必需）
            source_platform: 来源平台（weibo, douyin, bilibili）
            content_hash: 内容哈希（用于去重）
            image_url: 图片URL（MVP阶段可为空）
            category: 分类（humor, emotion, trending_phrase）
            popularity_score: 初始热度分数
            original_source_url: 原始来源URL（审计用）
        
        Returns:
            创建的Meme对象
        
        Raises:
            ValueError: 如果必需字段缺失或content_hash重复
        """
        try:
            # 验证必需字段
            if not text_description:
                raise ValueError("text_description is required")
            if not source_platform:
                raise ValueError("source_platform is required")
            if not content_hash:
                raise ValueError("content_hash is required")
            
            # 检查content_hash是否已存在（去重）
            existing = await self.db.execute(
                select(Meme).where(Meme.content_hash == content_hash)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Meme with content_hash {content_hash} already exists")
            
            # 创建新表情包记录
            meme = Meme(
                text_description=text_description,
                source_platform=source_platform,
                content_hash=content_hash,
                image_url=image_url,
                category=category,
                popularity_score=popularity_score,
                original_source_url=original_source_url,
                status="candidate",  # 初始状态为候选
                safety_status="pending",  # 安全状态为待审核
                trend_level="emerging",  # 趋势等级为新兴
                trend_score=0.0,
                usage_count=0,
                first_seen_at=datetime.utcnow(),
                last_updated_at=datetime.utcnow()
            )
            
            self.db.add(meme)
            await self.db.commit()
            await self.db.refresh(meme)
            
            logger.info(
                f"Created meme candidate: id={meme.id}, "
                f"platform={source_platform}, hash={content_hash[:8]}..."
            )
            
            return meme
            
        except ValueError as e:
            logger.warning(f"Failed to create meme candidate: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating meme candidate: {e}")
            await self.db.rollback()
            raise
    
    async def update_meme_status(
        self,
        meme_id: UUID,
        new_status: str,
        safety_status: Optional[str] = None,
        safety_check_details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        更新表情包生命周期状态
        
        Args:
            meme_id: 表情包ID
            new_status: 新状态（candidate, approved, rejected, archived）
            safety_status: 安全状态（pending, approved, rejected, flagged）
            safety_check_details: 安全检查详细结果（审计用）
        
        Returns:
            是否更新成功
        
        Raises:
            ValueError: 如果状态转换无效
        """
        try:
            # 获取当前表情包
            result = await self.db.execute(
                select(Meme).where(Meme.id == meme_id)
            )
            meme = result.scalar_one_or_none()
            
            if not meme:
                logger.warning(f"Meme not found: {meme_id}")
                return False
            
            # 验证状态转换
            current_status = meme.status
            valid_transitions = self.VALID_STATUS_TRANSITIONS.get(current_status, [])
            
            if new_status not in valid_transitions:
                raise ValueError(
                    f"Invalid status transition: {current_status} -> {new_status}. "
                    f"Valid transitions: {valid_transitions}"
                )
            
            # 更新状态
            meme.status = new_status
            meme.last_updated_at = datetime.utcnow()
            
            if safety_status:
                meme.safety_status = safety_status
            
            if safety_check_details:
                meme.safety_check_details = safety_check_details
            
            await self.db.commit()
            
            logger.info(
                f"Updated meme status: id={meme_id}, "
                f"{current_status} -> {new_status}"
            )
            
            return True
            
        except ValueError as e:
            logger.warning(f"Failed to update meme status: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error updating meme status: {e}")
            await self.db.rollback()
            return False
    
    async def get_approved_memes(
        self,
        trend_level: Optional[str] = None,
        limit: int = 100
    ) -> List[Meme]:
        """
        获取已批准的表情包，可选按趋势等级过滤
        
        Args:
            trend_level: 趋势等级过滤（emerging, rising, hot, peak, declining）
            limit: 返回数量限制
        
        Returns:
            已批准的表情包列表
        """
        try:
            # 构建查询
            query = select(Meme).where(
                and_(
                    Meme.status == "approved",
                    Meme.safety_status == "approved"
                )
            )
            
            # 添加趋势等级过滤
            if trend_level:
                query = query.where(Meme.trend_level == trend_level)
            
            # 按趋势分数降序排序
            query = query.order_by(Meme.trend_score.desc()).limit(limit)
            
            result = await self.db.execute(query)
            memes = result.scalars().all()
            
            logger.debug(
                f"Retrieved {len(memes)} approved memes "
                f"(trend_level={trend_level})"
            )
            
            return list(memes)
            
        except Exception as e:
            logger.error(f"Failed to get approved memes: {e}")
            return []
    
    async def increment_usage_count(self, meme_id: UUID) -> bool:
        """
        表情包被使用时增加使用计数
        
        Args:
            meme_id: 表情包ID
        
        Returns:
            是否更新成功
        """
        try:
            # 使用原子操作增加计数
            result = await self.db.execute(
                update(Meme)
                .where(Meme.id == meme_id)
                .values(
                    usage_count=Meme.usage_count + 1,
                    last_updated_at=datetime.utcnow()
                )
            )
            
            await self.db.commit()
            
            if result.rowcount > 0:
                logger.debug(f"Incremented usage count for meme: {meme_id}")
                return True
            else:
                logger.warning(f"Meme not found for usage increment: {meme_id}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to increment usage count: {e}")
            await self.db.rollback()
            return False
    
    async def get_memes_for_archival(
        self,
        declining_days: int = 30
    ) -> List[Meme]:
        """
        查找符合归档条件的表情包（衰退超过指定天数）
        
        Args:
            declining_days: 衰退状态持续天数阈值（默认30天）
        
        Returns:
            符合归档条件的表情包列表
        """
        try:
            # 计算阈值日期
            threshold_date = datetime.utcnow() - timedelta(days=declining_days)
            
            # 查询衰退超过指定天数的表情包
            query = select(Meme).where(
                and_(
                    Meme.trend_level == "declining",
                    Meme.status == "approved",
                    Meme.last_updated_at <= threshold_date
                )
            )
            
            result = await self.db.execute(query)
            memes = result.scalars().all()
            
            logger.info(
                f"Found {len(memes)} memes for archival "
                f"(declining > {declining_days} days)"
            )
            
            return list(memes)
            
        except Exception as e:
            logger.error(f"Failed to get memes for archival: {e}")
            return []
    
    async def archive_meme(self, meme_id: UUID) -> bool:
        """
        将表情包移至已归档状态
        
        Args:
            meme_id: 表情包ID
        
        Returns:
            是否归档成功
        """
        try:
            # 获取表情包
            result = await self.db.execute(
                select(Meme).where(Meme.id == meme_id)
            )
            meme = result.scalar_one_or_none()
            
            if not meme:
                logger.warning(f"Meme not found for archival: {meme_id}")
                return False
            
            # 验证可以归档（不能从candidate直接归档）
            if meme.status == "candidate":
                logger.warning(
                    f"Cannot archive candidate meme: {meme_id}. "
                    "Must be approved/rejected/flagged first."
                )
                return False
            
            # 更新为已归档状态
            meme.status = "archived"
            meme.last_updated_at = datetime.utcnow()
            
            await self.db.commit()
            
            logger.info(f"Archived meme: id={meme_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to archive meme: {e}")
            await self.db.rollback()
            return False
    
    async def get_meme_by_id(self, meme_id: UUID) -> Optional[Meme]:
        """
        根据ID获取表情包
        
        Args:
            meme_id: 表情包ID
        
        Returns:
            表情包对象，如果不存在则返回None
        """
        try:
            result = await self.db.execute(
                select(Meme).where(Meme.id == meme_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get meme by id: {e}")
            return None
    
    async def get_meme_by_content_hash(self, content_hash: str) -> Optional[Meme]:
        """
        根据content_hash获取表情包（用于去重检查）
        
        Args:
            content_hash: 内容哈希
        
        Returns:
            表情包对象，如果不存在则返回None
        """
        try:
            result = await self.db.execute(
                select(Meme).where(Meme.content_hash == content_hash)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get meme by content_hash: {e}")
            return None
    
    async def check_duplicate(self, content_hash: str) -> bool:
        """
        检查content_hash是否已存在（去重检查）
        
        Args:
            content_hash: 内容哈希
        
        Returns:
            如果已存在返回True，否则返回False
        """
        meme = await self.get_meme_by_content_hash(content_hash)
        return meme is not None
    
    async def update_meme_trend(
        self,
        meme_id: UUID,
        trend_score: float,
        trend_level: str
    ) -> bool:
        """
        更新表情包的趋势分数和等级（别名方法）
        
        Args:
            meme_id: 表情包ID
            trend_score: 新的趋势分数（0-100）
            trend_level: 新的趋势等级
        
        Returns:
            是否更新成功
        """
        return await self.update_trend_score(meme_id, trend_score, trend_level)
    
    async def update_trend_score(
        self,
        meme_id: UUID,
        trend_score: float,
        trend_level: str
    ) -> bool:
        """
        更新表情包的趋势分数和等级
        
        Args:
            meme_id: 表情包ID
            trend_score: 新的趋势分数（0-100）
            trend_level: 新的趋势等级
        
        Returns:
            是否更新成功
        """
        try:
            # 验证趋势分数范围
            if not 0 <= trend_score <= 100:
                raise ValueError(f"trend_score must be between 0 and 100, got {trend_score}")
            
            # 验证趋势等级
            valid_levels = ["emerging", "rising", "hot", "peak", "declining"]
            if trend_level not in valid_levels:
                raise ValueError(f"Invalid trend_level: {trend_level}")
            
            # 更新趋势信息
            result = await self.db.execute(
                update(Meme)
                .where(Meme.id == meme_id)
                .values(
                    trend_score=trend_score,
                    trend_level=trend_level,
                    last_updated_at=datetime.utcnow()
                )
            )
            
            await self.db.commit()
            
            if result.rowcount > 0:
                logger.debug(
                    f"Updated trend for meme {meme_id}: "
                    f"score={trend_score:.1f}, level={trend_level}"
                )
                return True
            else:
                logger.warning(f"Meme not found for trend update: {meme_id}")
                return False
            
        except ValueError as e:
            logger.warning(f"Failed to update trend score: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error updating trend score: {e}")
            await self.db.rollback()
            return False
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        获取内容池统计信息
        
        Returns:
            统计信息字典
        """
        try:
            stats = {}
            
            # 总表情包数
            result = await self.db.execute(select(Meme))
            stats["total_memes"] = len(result.scalars().all())
            
            # 按状态统计
            for status in ["candidate", "approved", "rejected", "archived"]:
                result = await self.db.execute(
                    select(Meme).where(Meme.status == status)
                )
                stats[f"{status}_memes"] = len(result.scalars().all())
            
            # 按趋势等级统计（仅已批准）
            for level in ["emerging", "rising", "hot", "peak", "declining"]:
                result = await self.db.execute(
                    select(Meme).where(
                        and_(
                            Meme.status == "approved",
                            Meme.trend_level == level
                        )
                    )
                )
                stats[f"{level}_memes"] = len(result.scalars().all())
            
            # 平均趋势分数（已批准）
            result = await self.db.execute(
                select(Meme).where(Meme.status == "approved")
            )
            approved_memes = result.scalars().all()
            if approved_memes:
                avg_score = sum(m.trend_score for m in approved_memes) / len(approved_memes)
                stats["avg_trend_score"] = round(avg_score, 2)
            else:
                stats["avg_trend_score"] = 0.0
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}
