"""
冲突解决服务 - 完整的长期方案

功能：
1. 检测记忆冲突
2. 生成澄清问题
3. 处理用户澄清回答
4. 更新记忆状态
5. 记录冲突历史
"""
import logging
import uuid
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.conflict_detector_service import ConflictDetector
from app.services.retrieval_service import Memory

logger = logging.getLogger(__name__)


class ConflictResolutionService:
    """
    冲突解决服务 - 完整实现
    
    工作流程：
    1. 检测冲突 -> 2. 记录冲突 -> 3. 生成澄清问题 -> 4. 等待用户回答 -> 5. 更新记忆状态
    """
    
    def __init__(self, db_session: AsyncSession = None):
        self.db = db_session
        self.detector = ConflictDetector()
    
    async def detect_and_record_conflicts(
        self,
        user_id: str,
        memories: List[Memory],
        threshold: float = 0.8
    ) -> List[Dict]:
        """
        检测冲突并记录到数据库
        
        Args:
            user_id: 用户 ID
            memories: 记忆列表
            threshold: 冲突判定阈值
            
        Returns:
            冲突列表
        """
        # 1. 检测冲突
        conflicts = self.detector.detect_conflicts(memories, threshold)
        
        if not conflicts or not self.db:
            return conflicts
        
        # 2. 记录到数据库
        for conflict in conflicts:
            await self._record_conflict(user_id, conflict)
        
        logger.info(f"Detected and recorded {len(conflicts)} conflicts for user {user_id[:8]}")
        return conflicts
    
    async def _record_conflict(
        self,
        user_id: str,
        conflict: Dict
    ) -> str:
        """
        记录冲突到数据库
        
        Returns:
            conflict_id: 冲突记录 ID
        """
        try:
            conflict_id = str(uuid.uuid4())
            
            # 提取冲突信息（支持字典和 dataclass）
            mem1 = conflict["memory_1"]
            mem2 = conflict["memory_2"]
            
            mem1_id = mem1.get("id") if isinstance(mem1, dict) else mem1.id
            mem2_id = mem2.get("id") if isinstance(mem2, dict) else mem2.id
            
            conflict_type = conflict["conflict_type"]
            common_topic = conflict.get("common_topic", [])
            confidence = conflict.get("confidence", 0.9)
            
            # 插入冲突记录
            await self.db.execute(
                text("""
                    INSERT INTO memory_conflicts 
                    (id, user_id, memory_1_id, memory_2_id, conflict_type, common_topic, confidence, status)
                    VALUES (:id, :user_id, :mem1_id, :mem2_id, :conflict_type, :common_topic, :confidence, 'pending')
                    ON CONFLICT (memory_1_id, memory_2_id) DO NOTHING
                """),
                {
                    "id": conflict_id,
                    "user_id": user_id,
                    "mem1_id": mem1_id,
                    "mem2_id": mem2_id,
                    "conflict_type": conflict_type,
                    "common_topic": common_topic,
                    "confidence": confidence
                }
            )
            
            await self.db.commit()
            
            logger.info(f"Recorded conflict {conflict_id[:8]} for user {user_id[:8]}")
            return conflict_id
            
        except Exception as e:
            logger.error(f"Failed to record conflict: {e}")
            await self.db.rollback()
            return None
    
    async def should_ask_clarification(
        self,
        user_id: str,
        conflicts: List[Dict]
    ) -> Tuple[bool, Optional[Dict]]:
        """
        判断是否应该询问用户澄清
        
        策略：
        1. 如果有高置信度冲突（> 0.8），询问澄清
        2. 如果用户最近已经回答过澄清问题，不再询问（避免打扰）
        3. 每个会话最多询问一次
        
        Returns:
            (should_ask, conflict_to_clarify)
        """
        if not conflicts:
            return False, None
        
        # 选择置信度最高的冲突
        conflict = max(conflicts, key=lambda c: c.get("confidence", 0))
        
        if conflict.get("confidence", 0) < 0.8:
            return False, None
        
        # 检查是否最近已经询问过
        if self.db:
            try:
                result = await self.db.execute(
                    text("""
                        SELECT COUNT(*) FROM clarification_sessions
                        WHERE user_id = :user_id
                        AND created_at > NOW() - INTERVAL '1 hour'
                        AND status = 'pending'
                    """),
                    {"user_id": user_id}
                )
                count = result.scalar()
                
                if count > 0:
                    logger.info(f"User {user_id[:8]} already has pending clarification, skip")
                    return False, None
                    
            except Exception as e:
                logger.warning(f"Failed to check clarification history: {e}")
        
        return True, conflict
    
    async def create_clarification_session(
        self,
        user_id: str,
        session_id: str,
        conflict: Dict
    ) -> Optional[str]:
        """
        创建澄清会话
        
        Returns:
            clarification_session_id
        """
        if not self.db:
            return None
        
        try:
            clarification_id = str(uuid.uuid4())
            
            # 生成澄清问题
            clarification_question = self.detector.generate_clarification_prompt(conflict)
            
            # 获取 conflict_id（从数据库查询）
            mem1 = conflict["memory_1"]
            mem2 = conflict["memory_2"]
            
            mem1_id = mem1.get("id") if isinstance(mem1, dict) else mem1.id
            mem2_id = mem2.get("id") if isinstance(mem2, dict) else mem2.id
            
            result = await self.db.execute(
                text("""
                    SELECT id FROM memory_conflicts
                    WHERE memory_1_id = :mem1_id AND memory_2_id = :mem2_id
                    LIMIT 1
                """),
                {"mem1_id": mem1_id, "mem2_id": mem2_id}
            )
            conflict_record = result.fetchone()
            
            if not conflict_record:
                logger.warning("Conflict record not found, cannot create clarification session")
                return None
            
            conflict_id = conflict_record[0]
            
            # 插入澄清会话
            await self.db.execute(
                text("""
                    INSERT INTO clarification_sessions
                    (id, user_id, conflict_id, session_id, clarification_question, status)
                    VALUES (:id, :user_id, :conflict_id, :session_id, :question, 'pending')
                """),
                {
                    "id": clarification_id,
                    "user_id": user_id,
                    "conflict_id": conflict_id,
                    "session_id": session_id,
                    "question": clarification_question
                }
            )
            
            await self.db.commit()
            
            logger.info(f"Created clarification session {clarification_id[:8]} for user {user_id[:8]}")
            return clarification_id
            
        except Exception as e:
            logger.error(f"Failed to create clarification session: {e}")
            await self.db.rollback()
            return None
    
    async def process_clarification_response(
        self,
        user_id: str,
        session_id: str,
        user_response: str
    ) -> bool:
        """
        处理用户的澄清回答
        
        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            user_response: 用户回答
            
        Returns:
            是否成功处理
        """
        if not self.db:
            return False
        
        try:
            # 1. 查找待处理的澄清会话
            result = await self.db.execute(
                text("""
                    SELECT cs.id, cs.conflict_id, mc.memory_1_id, mc.memory_2_id
                    FROM clarification_sessions cs
                    JOIN memory_conflicts mc ON cs.conflict_id = mc.id
                    WHERE cs.user_id = :user_id
                    AND cs.session_id = :session_id
                    AND cs.status = 'pending'
                    ORDER BY cs.created_at DESC
                    LIMIT 1
                """),
                {"user_id": user_id, "session_id": session_id}
            )
            clarification = result.fetchone()
            
            if not clarification:
                logger.warning(f"No pending clarification found for user {user_id[:8]}")
                return False
            
            clarification_id, conflict_id, mem1_id, mem2_id = clarification
            
            # 2. 解析用户回答（简化版：基于关键词）
            preferred_memory_id = self._parse_user_choice(user_response, mem1_id, mem2_id)
            
            if not preferred_memory_id:
                logger.warning(f"Could not parse user choice from: {user_response}")
                return False
            
            # 3. 更新澄清会话状态
            await self.db.execute(
                text("""
                    UPDATE clarification_sessions
                    SET user_response = :response, status = 'answered', answered_at = NOW()
                    WHERE id = :id
                """),
                {"id": clarification_id, "response": user_response}
            )
            
            # 4. 解决冲突
            await self._resolve_conflict(
                conflict_id,
                preferred_memory_id,
                resolution_method="user_clarified"
            )
            
            await self.db.commit()
            
            logger.info(f"Processed clarification response for user {user_id[:8]}, preferred memory: {preferred_memory_id[:8]}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process clarification response: {e}")
            await self.db.rollback()
            return False
    
    def _parse_user_choice(
        self,
        user_response: str,
        mem1_id: str,
        mem2_id: str
    ) -> Optional[str]:
        """
        解析用户的选择
        
        简化版：基于关键词匹配
        - "第一个"、"A"、"1" -> mem1_id
        - "第二个"、"B"、"2" -> mem2_id
        """
        response_lower = user_response.lower()
        
        # 检测选择第一个
        if any(keyword in response_lower for keyword in ["第一个", "第一", "a", "1", "前者"]):
            return mem1_id
        
        # 检测选择第二个
        if any(keyword in response_lower for keyword in ["第二个", "第二", "b", "2", "后者"]):
            return mem2_id
        
        # 默认：如果无法判断，返回 None
        return None
    
    async def _resolve_conflict(
        self,
        conflict_id: str,
        preferred_memory_id: str,
        resolution_method: str
    ) -> bool:
        """
        解决冲突
        
        1. 更新冲突状态为 resolved
        2. 标记非首选记忆为 deprecated
        """
        if not self.db:
            return False
        
        try:
            # 调用数据库函数
            await self.db.execute(
                text("SELECT resolve_conflict(:conflict_id, :preferred_id, :method)"),
                {
                    "conflict_id": conflict_id,
                    "preferred_id": preferred_memory_id,
                    "method": resolution_method
                }
            )
            
            await self.db.commit()
            
            logger.info(f"Resolved conflict {conflict_id[:8]}, preferred memory: {preferred_memory_id[:8]}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to resolve conflict: {e}")
            await self.db.rollback()
            return False
    
    async def get_pending_conflicts(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        获取用户的待处理冲突
        
        Returns:
            冲突列表
        """
        if not self.db:
            return []
        
        try:
            result = await self.db.execute(
                text("""
                    SELECT * FROM pending_conflicts
                    WHERE user_id = :user_id
                    LIMIT :limit
                """),
                {"user_id": user_id, "limit": limit}
            )
            
            conflicts = []
            for row in result.fetchall():
                conflicts.append({
                    "id": row[0],
                    "user_id": row[1],
                    "memory_1_id": row[2],
                    "memory_2_id": row[3],
                    "conflict_type": row[4],
                    "common_topic": row[5],
                    "confidence": row[6],
                    "status": row[7],
                    "memory_1_content": row[11],
                    "memory_1_created_at": row[12],
                    "memory_2_content": row[13],
                    "memory_2_created_at": row[14]
                })
            
            return conflicts
            
        except Exception as e:
            logger.error(f"Failed to get pending conflicts: {e}")
            return []
