"""GDPR 删除任务 - 物理删除 Worker"""
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import uuid

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from neo4j import AsyncGraphDatabase
from pymilvus import Collection

from app.worker import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)

# 物理删除 SLA: 72 小时
PHYSICAL_DELETION_SLA_HOURS = 72


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def execute_physical_deletion(self):
    """
    执行物理删除（高优先级任务）
    
    由 Celery Beat 每 6 小时调用
    SLA: 72 小时内完成物理删除
    
    Property 8: 物理删除 72h SLA
    """
    import asyncio
    from app.core.database import AsyncSessionLocal, get_neo4j_driver
    from app.models.memory import Memory, DeletionAudit, IdMapping
    
    async def _execute():
        deleted_count = 0
        errors = []
        
        async with AsyncSessionLocal() as db:
            try:
                # 1. 获取所有 status='deleted' 且超过 SLA 时间的记录
                cutoff_time = datetime.utcnow() - timedelta(hours=PHYSICAL_DELETION_SLA_HOURS)
                
                # 查找需要物理删除的记忆（已逻辑删除且超过 72h）
                query = select(Memory).where(
                    Memory.status == "deleted",
                    Memory.created_at < cutoff_time
                ).limit(1000)  # 批量处理，避免大事务
                
                result = await db.execute(query)
                memories_to_delete = result.scalars().all()
                
                if not memories_to_delete:
                    logger.info("No memories pending physical deletion")
                    return {"status": "completed", "deleted_count": 0}
                
                memory_ids = [str(m.id) for m in memories_to_delete]
                user_ids = list(set(str(m.user_id) for m in memories_to_delete))
                
                logger.info(f"Physical deletion: {len(memory_ids)} memories from {len(user_ids)} users")
                
                # 2. 从 Neo4j 删除相关节点和边
                neo4j_deleted = await _delete_from_neo4j(memory_ids, user_ids)
                
                # 3. 从 Milvus 删除向量
                milvus_deleted = await _delete_from_milvus(memory_ids)
                
                # 4. 从 Postgres 物理删除
                for memory in memories_to_delete:
                    await db.delete(memory)
                    deleted_count += 1
                
                # 5. 更新相关审计记录
                await _update_audit_records(db, user_ids)
                
                await db.commit()
                
                logger.info(f"Physical deletion completed: {deleted_count} memories, "
                           f"{neo4j_deleted} neo4j nodes, {milvus_deleted} milvus vectors")
                
            except Exception as e:
                logger.error(f"Physical deletion failed: {e}")
                await db.rollback()
                errors.append(str(e))
                raise self.retry(exc=e)
        
        return {
            "status": "completed",
            "deleted_count": deleted_count,
            "neo4j_deleted": neo4j_deleted,
            "milvus_deleted": milvus_deleted,
            "errors": errors,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    return asyncio.get_event_loop().run_until_complete(_execute())


async def _delete_from_neo4j(memory_ids: List[str], user_ids: List[str]) -> int:
    """从 Neo4j 删除相关节点和边"""
    deleted_count = 0
    
    try:
        from app.core.database import get_neo4j_driver
        driver = get_neo4j_driver()
        
        if not driver:
            logger.warning("Neo4j driver not available, skipping")
            return 0
        
        async with driver.session() as session:
            # 删除与这些记忆相关的实体节点
            for user_id in user_ids:
                result = await session.run(
                    """
                    MATCH (e:Entity {user_id: $user_id})
                    WHERE e.status = 'deleted' OR e.id IN $memory_ids
                    DETACH DELETE e
                    RETURN count(e) as deleted
                    """,
                    user_id=user_id,
                    memory_ids=memory_ids
                )
                record = await result.single()
                if record:
                    deleted_count += record["deleted"]
                    
    except Exception as e:
        logger.error(f"Neo4j deletion error: {e}")
    
    return deleted_count


async def _delete_from_milvus(memory_ids: List[str]) -> int:
    """从 Milvus 删除向量"""
    deleted_count = 0
    
    try:
        from app.core.database import get_milvus_collection, milvus_connected
        
        if not milvus_connected:
            logger.warning("Milvus not connected, skipping")
            return 0
        
        collection = get_milvus_collection()
        
        expr = f"id in {json.dumps(memory_ids)}"
        result = collection.delete(expr)
        deleted_count = result.delete_count if hasattr(result, 'delete_count') else len(memory_ids)
        
    except Exception as e:
        logger.error(f"Milvus deletion error: {e}")
    
    return deleted_count


async def _update_audit_records(db: AsyncSession, user_ids: List[str]):
    """更新审计记录状态"""
    from app.models.memory import DeletionAudit
    
    for user_id in user_ids:
        try:
            user_uuid = uuid.UUID(user_id)
            
            # 更新该用户的 pending 审计记录为 completed
            stmt = (
                update(DeletionAudit)
                .where(
                    DeletionAudit.user_id == user_uuid,
                    DeletionAudit.status == "pending"
                )
                .values(
                    status="completed",
                    completed_at=datetime.utcnow()
                )
            )
            await db.execute(stmt)
            
        except Exception as e:
            logger.error(f"Audit update error for user {user_id}: {e}")


@celery_app.task(bind=True, max_retries=5, default_retry_delay=60)
def delete_user_data(self, user_id: str, deletion_type: str = "full"):
    """
    删除用户数据（异步任务）
    
    Args:
        user_id: 用户 ID
        deletion_type: 删除类型 (full, selective)
        
    Property 7: 删除后不可检索
    """
    import asyncio
    from app.core.database import AsyncSessionLocal
    from app.models.memory import Memory, IdMapping
    
    async def _delete():
        affected_records = {
            "memories": 0,
            "entities": 0,
            "edges": 0,
            "vectors": 0
        }
        
        async with AsyncSessionLocal() as db:
            try:
                user_uuid = uuid.UUID(user_id)
                
                # 1. 标记 Neo4j 节点为删除状态
                neo4j_count = await _mark_neo4j_deleted(user_id)
                affected_records["entities"] = neo4j_count
                
                # 2. 标记 Milvus 向量为删除（通过 ID 映射）
                milvus_count = await _mark_milvus_deleted(user_id)
                affected_records["vectors"] = milvus_count
                
                # 3. 获取已删除的记忆数量
                query = select(Memory).where(
                    Memory.user_id == user_uuid,
                    Memory.status == "deleted"
                )
                result = await db.execute(query)
                memories = result.scalars().all()
                affected_records["memories"] = len(memories)
                
                await db.commit()
                
                logger.info(f"User data marked for deletion: {user_id}, affected: {affected_records}")
                
            except Exception as e:
                logger.error(f"Delete user data failed: {e}")
                await db.rollback()
                raise self.retry(exc=e)
        
        return {
            "status": "success",
            "user_id": user_id,
            "deletion_type": deletion_type,
            "affected_records": affected_records
        }
    
    return asyncio.get_event_loop().run_until_complete(_delete())


async def _mark_neo4j_deleted(user_id: str) -> int:
    """标记 Neo4j 节点为删除状态"""
    count = 0
    
    try:
        from app.core.database import get_neo4j_driver
        driver = get_neo4j_driver()
        
        if not driver:
            return 0
        
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (e:Entity {user_id: $user_id})
                SET e.status = 'deleted', e.deleted_at = datetime()
                RETURN count(e) as count
                """,
                user_id=user_id
            )
            record = await result.single()
            if record:
                count = record["count"]
                
    except Exception as e:
        logger.error(f"Neo4j mark deleted error: {e}")
    
    return count


async def _mark_milvus_deleted(user_id: str) -> int:
    """标记 Milvus 向量为删除（实际上 Milvus 不支持软删除，这里记录数量）"""
    count = 0
    
    try:
        from app.core.database import get_milvus_collection, milvus_connected
        
        if not milvus_connected:
            return 0
        
        collection = get_milvus_collection()
        
        # 查询该用户的向量数量
        expr = f'user_id == "{user_id}"'
        results = collection.query(expr=expr, output_fields=["id"])
        count = len(results)
        
    except Exception as e:
        logger.error(f"Milvus query error: {e}")
    
    return count


def generate_audit_hash(data: Dict) -> str:
    """
    生成审计数据的 HMAC 签名
    
    用于验证删除已执行（Property 13: 删除可验证性）
    """
    message = json.dumps(data, sort_keys=True, default=str).encode()
    secret = settings.JWT_SECRET.encode()
    
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def verify_audit_signature(audit_data: Dict, signature: str) -> bool:
    """
    验证审计签名
    
    Args:
        audit_data: 审计数据（不含签名）
        signature: 待验证的签名
        
    Returns:
        签名是否有效
    """
    expected_hash = generate_audit_hash(audit_data)
    return hmac.compare_digest(expected_hash, signature)


@celery_app.task
def complete_deletion_audit(audit_id: str):
    """
    完成删除审计
    
    在物理删除完成后调用，生成最终签名
    """
    import asyncio
    from app.core.database import AsyncSessionLocal
    from app.models.memory import DeletionAudit
    
    async def _complete():
        async with AsyncSessionLocal() as db:
            try:
                audit_uuid = uuid.UUID(audit_id)
                
                query = select(DeletionAudit).where(DeletionAudit.id == audit_uuid)
                result = await db.execute(query)
                audit = result.scalar_one_or_none()
                
                if not audit:
                    return {"status": "error", "message": "Audit not found"}
                
                # 生成完成签名
                completion_data = {
                    "audit_id": str(audit.id),
                    "user_id": str(audit.user_id),
                    "deletion_type": audit.deletion_type,
                    "affected_records": audit.affected_records,
                    "requested_at": audit.requested_at.isoformat(),
                    "completed_at": datetime.utcnow().isoformat()
                }
                
                final_signature = generate_audit_hash(completion_data)
                
                audit.status = "completed"
                audit.completed_at = datetime.utcnow()
                audit.signature = final_signature
                
                await db.commit()
                
                return {
                    "status": "completed",
                    "audit_id": audit_id,
                    "signature": final_signature,
                    "completed_at": audit.completed_at.isoformat()
                }
                
            except Exception as e:
                logger.error(f"Complete audit failed: {e}")
                await db.rollback()
                return {"status": "error", "message": str(e)}
    
    return asyncio.get_event_loop().run_until_complete(_complete())


@celery_app.task
def cleanup_expired_idempotency_keys():
    """清理过期的幂等键（24h TTL）"""
    import asyncio
    from app.core.database import AsyncSessionLocal
    
    async def _cleanup():
        async with AsyncSessionLocal() as db:
            try:
                from app.models.outbox import IdempotencyKey
                
                cutoff = datetime.utcnow() - timedelta(hours=24)
                
                stmt = delete(IdempotencyKey).where(
                    IdempotencyKey.created_at < cutoff
                )
                result = await db.execute(stmt)
                await db.commit()
                
                return {
                    "status": "completed",
                    "deleted_count": result.rowcount,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
            except Exception as e:
                logger.error(f"Cleanup idempotency keys failed: {e}")
                await db.rollback()
                return {"status": "error", "message": str(e)}
    
    return asyncio.get_event_loop().run_until_complete(_cleanup())
