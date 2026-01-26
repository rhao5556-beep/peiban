"""
使用决策引擎服务
"""
import logging
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class UsageDecisionEngineService:
    """使用决策引擎服务 - 最小实现"""
    
    def __init__(
        self,
        db_session: Optional[AsyncSession] = None,
        content_pool_manager=None,
        usage_history_service=None
    ):
        self.db = db_session
        self.content_pool_manager = content_pool_manager
        self.usage_history_service = usage_history_service
