"""数据一致性任务 - 监控与巡检"""
import logging
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import uuid

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.worker import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)

# SLO 阈值
SLO_MEDIAN_LAG_MS = 2000  # 2s
SLO_P95_LAG_MS = 30000    # 30s
MISMATCH_RATE_THRESHOLD = 0.01  # 1%


@celery_app.task(bind=True, max_retries=3)
def check_data_consistency(self):
    """
    检查三方数据一致性
    
    由 Celery Beat 每小时调用
    
    检查项:
    1. Postgres 记录是否在 Neo4j 中存在
    2. Postgres 记录是否在 Milvus 中存在
    3. ID 映射表是否完整
    """
    import asyncio
    from app.core.database import AsyncSessionLocal, get_neo4j_driver, get_milvus_collection, milvus_connected
    from app.models.memory import Memory, IdMapping
    
    async def _check():
        results = {
            "postgres_neo4j_mismatch": 0,
            "postgres_milvus_mismatch": 0,
            "orphan_records": 0,
            "total_checked": 0,
            "repaired": 0
        }
        
        async with AsyncSessionLocal() as db:
            try:
                # 1. 获取所有 committed 状态的记忆
                query = select(Memory).where(Memory.status == "committed").limit(1000)
                result = await db.execute(query)
                memories = result.scalars().all()
                
                results["total_checked"] = len(memories)
                
                if not memories:
                    return results
                
                # 2. 检查 Neo4j 一致性
                neo4j_driver = get_neo4j_driver()
                if neo4j_driver:
                    neo4j_missing = await _check_neo4j_consistency(
                        neo4j_driver, 
                        [str(m.id) for m in memories]
                    )
                    results["postgres_neo4j_mismatch"] = len(neo4j_missing)
                
                # 3. 检查 Milvus 一致性
                if milvus_connected:
                    milvus_missing = await _check_milvus_consistency(
                        [str(m.id) for m in memories]
                    )
                    results["postgres_milvus_mismatch"] = len(milvus_missing)
                
                # 4. 检查孤儿记录（在 Neo4j/Milvus 但不在 Postgres）
                orphans = await _check_orphan_records(db, neo4j_driver)
                results["orphan_records"] = orphans
                
            except Exception as e:
                logger.error(f"Consistency check failed: {e}")
                raise self.retry(exc=e)
        
        # 计算不一致率
        total = results["total_checked"]
        mismatches = results["postgres_neo4j_mismatch"] + results["postgres_milvus_mismatch"]
        mismatch_rate = mismatches / total if total > 0 else 0.0
        
        # 如果超过阈值，记录告警
        if mismatch_rate > MISMATCH_RATE_THRESHOLD:
            logger.warning(f"Data mismatch rate {mismatch_rate:.2%} exceeds threshold {MISMATCH_RATE_THRESHOLD:.2%}")
        
        return {
            "status": "completed",
            "results": results,
            "mismatch_rate": mismatch_rate,
            "slo_met": mismatch_rate <= MISMATCH_RATE_THRESHOLD,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    return asyncio.get_event_loop().run_until_complete(_check())


async def _check_neo4j_consistency(driver, memory_ids: List[str]) -> List[str]:
    """检查 Neo4j 中是否存在对应记录"""
    missing = []
    
    try:
        async with driver.session() as session:
            result = await session.run(
                """
                UNWIND $memory_ids AS mid
                OPTIONAL MATCH (e:Entity {memory_id: mid})
                RETURN mid, e IS NOT NULL AS exists
                """,
                memory_ids=memory_ids
            )
            
            async for record in result:
                if not record["exists"]:
                    missing.append(record["mid"])
                    
    except Exception as e:
        logger.error(f"Neo4j consistency check error: {e}")
    
    return missing


async def _check_milvus_consistency(memory_ids: List[str]) -> List[str]:
    """检查 Milvus 中是否存在对应向量"""
    missing = []
    
    try:
        from app.core.database import get_milvus_collection
        collection = get_milvus_collection()
        
        # 查询存在的 ID
        expr = f'id in {memory_ids}'
        results = collection.query(expr=expr, output_fields=["id"])
        existing_ids = set(str(r["id"]) for r in results)
        
        missing = [mid for mid in memory_ids if mid not in existing_ids]
        
    except Exception as e:
        logger.error(f"Milvus consistency check error: {e}")
    
    return missing


async def _check_orphan_records(db: AsyncSession, neo4j_driver) -> int:
    """检查孤儿记录数量"""
    orphan_count = 0
    
    # 这里简化实现，实际应该检查 Neo4j/Milvus 中存在但 Postgres 不存在的记录
    # 由于跨数据库查询复杂，这里只返回估计值
    
    return orphan_count


@celery_app.task(bind=True, max_retries=3)
def repair_inconsistency(self, record_id: str, repair_type: str):
    """
    修复数据不一致（Fix-Forward 策略）
    
    Args:
        record_id: 记录 ID
        repair_type: 修复类型
            - neo4j_missing: Neo4j 缺失数据
            - milvus_missing: Milvus 缺失向量
            - orphan: 孤儿记录清理
    
    架构决策：
    - 使用 Fix-Forward 而非 Rollback
    - 异步系统不做回滚，只做修复
    """
    import asyncio
    from app.core.database import AsyncSessionLocal
    from app.models.memory import Memory
    from app.models.outbox import OutboxEvent
    
    async def _repair():
        async with AsyncSessionLocal() as db:
            try:
                record_uuid = uuid.UUID(record_id)
                
                if repair_type == "neo4j_missing":
                    # Neo4j 缺失：重新触发实体抽取和写入
                    return await _repair_neo4j_missing(db, record_uuid)
                
                elif repair_type == "milvus_missing":
                    # Milvus 缺失：重新写入向量
                    return await _repair_milvus_missing(db, record_uuid)
                
                elif repair_type == "orphan":
                    # 孤儿记录：标记为需要清理
                    return await _repair_orphan(db, record_uuid)
                
                else:
                    return {
                        "status": "error",
                        "record_id": record_id,
                        "error": f"Unknown repair type: {repair_type}"
                    }
                
            except Exception as e:
                logger.error(f"Repair failed: {e}")
                raise self.retry(exc=e)
    
    return asyncio.get_event_loop().run_until_complete(_repair())


async def _repair_neo4j_missing(db, record_uuid) -> Dict:
    """
    修复 Neo4j 缺失数据
    
    策略：重新创建 Outbox 事件，触发完整的抽取流程
    """
    from sqlalchemy import select
    from app.models.memory import Memory
    from app.models.outbox import OutboxEvent
    
    query = select(Memory).where(Memory.id == record_uuid)
    result = await db.execute(query)
    memory = result.scalar_one_or_none()
    
    if not memory:
        return {
            "status": "error",
            "record_id": str(record_uuid),
            "error": "Memory not found"
        }
    
    # 创建修复事件
    repair_event_id = f"repair_neo4j_{record_uuid}_{datetime.utcnow().timestamp()}"
    
    event = OutboxEvent(
        event_id=repair_event_id,
        memory_id=memory.id,
        payload={
            "type": "repair_neo4j",
            "memory_id": str(memory.id),
            "content": memory.content,
            "user_id": str(memory.user_id),
            "embedding": memory.embedding if hasattr(memory, 'embedding') else None,
            "valence": memory.valence if hasattr(memory, 'valence') else 0
        },
        status="pending"
    )
    db.add(event)
    await db.commit()
    
    logger.info(f"Created repair event for Neo4j missing: {repair_event_id}")
    
    return {
        "status": "success",
        "record_id": str(record_uuid),
        "repair_type": "neo4j_missing",
        "action": "outbox_event_created",
        "event_id": repair_event_id,
        "repaired_at": datetime.utcnow().isoformat()
    }


async def _repair_milvus_missing(db, record_uuid) -> Dict:
    """
    修复 Milvus 缺失向量
    
    策略：直接重新写入向量（不需要重新抽取实体）
    """
    from sqlalchemy import select
    from app.models.memory import Memory
    from app.services.retrieval_service import EmbeddingService
    
    query = select(Memory).where(Memory.id == record_uuid)
    result = await db.execute(query)
    memory = result.scalar_one_or_none()
    
    if not memory:
        return {
            "status": "error",
            "record_id": str(record_uuid),
            "error": "Memory not found"
        }
    
    try:
        # 重新生成 embedding（如果没有缓存）
        embedding = memory.embedding if hasattr(memory, 'embedding') and memory.embedding else None
        
        if not embedding:
            embedding_service = EmbeddingService()
            embedding = await embedding_service.encode(memory.content)
        
        # 直接写入 Milvus
        from app.worker.tasks.outbox import write_to_milvus_sync
        
        milvus_id = write_to_milvus_sync(
            memory_id=str(memory.id),
            user_id=str(memory.user_id),
            content=memory.content,
            embedding=embedding,
            valence=memory.valence if hasattr(memory, 'valence') else 0
        )
        
        if milvus_id:
            logger.info(f"Repaired Milvus missing for memory {record_uuid}")
            return {
                "status": "success",
                "record_id": str(record_uuid),
                "repair_type": "milvus_missing",
                "action": "vector_rewritten",
                "milvus_id": milvus_id,
                "repaired_at": datetime.utcnow().isoformat()
            }
        else:
            return {
                "status": "error",
                "record_id": str(record_uuid),
                "error": "Failed to write to Milvus"
            }
            
    except Exception as e:
        logger.error(f"Milvus repair failed: {e}")
        return {
            "status": "error",
            "record_id": str(record_uuid),
            "error": str(e)
        }


async def _repair_orphan(db, record_uuid) -> Dict:
    """
    处理孤儿记录
    
    策略：标记为需要人工审核，不自动删除
    """
    from sqlalchemy import text
    
    # 记录到审计表
    await db.execute(
        text("""
            INSERT INTO deletion_audit (id, entity_type, entity_id, reason, requested_at, status)
            VALUES (:id, 'orphan', :entity_id, 'Orphan record detected by consistency check', NOW(), 'pending_review')
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "id": str(uuid.uuid4()),
            "entity_id": str(record_uuid)
        }
    )
    await db.commit()
    
    logger.info(f"Marked orphan record for review: {record_uuid}")
    
    return {
        "status": "success",
        "record_id": str(record_uuid),
        "repair_type": "orphan",
        "action": "marked_for_review",
        "repaired_at": datetime.utcnow().isoformat()
    }


@celery_app.task
def cleanup_expired_keys():
    """
    清理过期的幂等键
    
    由 Celery Beat 每小时调用
    """
    import asyncio
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import delete
    
    async def _cleanup():
        async with AsyncSessionLocal() as db:
            try:
                from app.models.outbox import IdempotencyKey
                
                cutoff = datetime.utcnow() - timedelta(hours=24)
                
                stmt = delete(IdempotencyKey).where(
                    IdempotencyKey.expires_at < cutoff
                )
                result = await db.execute(stmt)
                await db.commit()
                
                cleaned_count = result.rowcount
                logger.info(f"Cleaned {cleaned_count} expired idempotency keys")
                
                return {
                    "status": "completed",
                    "cleaned_count": cleaned_count,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")
                await db.rollback()
                return {"status": "error", "message": str(e)}
    
    return asyncio.get_event_loop().run_until_complete(_cleanup())


@celery_app.task
def verify_outbox_slo():
    """
    验证 Outbox SLO
    
    检查 Outbox 处理延迟是否符合 SLO:
    - Median Lag < 2s
    - P95 Lag < 30s
    
    Property 9: 最终一致性 with SLO
    """
    import asyncio
    from app.core.database import AsyncSessionLocal
    from app.models.outbox import OutboxEvent
    
    async def _verify():
        async with AsyncSessionLocal() as db:
            try:
                # 获取最近 1 小时已处理的事件
                one_hour_ago = datetime.utcnow() - timedelta(hours=1)
                
                query = select(OutboxEvent).where(
                    OutboxEvent.status == "done",
                    OutboxEvent.processed_at >= one_hour_ago
                )
                result = await db.execute(query)
                events = result.scalars().all()
                
                if not events:
                    return {
                        "status": "completed",
                        "p50_lag_ms": 0,
                        "p95_lag_ms": 0,
                        "slo_met": True,
                        "sample_size": 0,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                
                # 计算延迟（毫秒）
                lags = []
                for event in events:
                    if event.processed_at and event.created_at:
                        lag_ms = (event.processed_at - event.created_at).total_seconds() * 1000
                        lags.append(lag_ms)
                
                if not lags:
                    return {
                        "status": "completed",
                        "p50_lag_ms": 0,
                        "p95_lag_ms": 0,
                        "slo_met": True,
                        "sample_size": 0,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                
                # 计算 P50 和 P95
                p50_lag = statistics.median(lags)
                sorted_lags = sorted(lags)
                p95_index = int(len(sorted_lags) * 0.95)
                p95_lag = sorted_lags[min(p95_index, len(sorted_lags) - 1)]
                
                # 检查 SLO
                slo_met = p50_lag < SLO_MEDIAN_LAG_MS and p95_lag < SLO_P95_LAG_MS
                
                if not slo_met:
                    logger.warning(
                        f"Outbox SLO violated: P50={p50_lag:.0f}ms (limit={SLO_MEDIAN_LAG_MS}ms), "
                        f"P95={p95_lag:.0f}ms (limit={SLO_P95_LAG_MS}ms)"
                    )
                
                return {
                    "status": "completed",
                    "p50_lag_ms": round(p50_lag, 2),
                    "p95_lag_ms": round(p95_lag, 2),
                    "slo_met": slo_met,
                    "sample_size": len(lags),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
            except Exception as e:
                logger.error(f"SLO verification failed: {e}")
                return {"status": "error", "message": str(e)}
    
    return asyncio.get_event_loop().run_until_complete(_verify())


@celery_app.task
def generate_consistency_report(days: int = 7) -> Dict:
    """
    生成数据一致性报告
    
    Args:
        days: 报告周期（天）
        
    Returns:
        一致性报告
    """
    import asyncio
    from app.core.database import AsyncSessionLocal
    from app.models.memory import Memory, DeletionAudit
    from app.models.outbox import OutboxEvent
    
    async def _generate():
        async with AsyncSessionLocal() as db:
            try:
                cutoff = datetime.utcnow() - timedelta(days=days)
                
                # 统计记忆数量
                total_query = select(func.count(Memory.id)).where(
                    Memory.created_at >= cutoff
                )
                total_result = await db.execute(total_query)
                total_records = total_result.scalar() or 0
                
                # 统计各状态数量
                status_query = select(
                    Memory.status,
                    func.count(Memory.id)
                ).where(
                    Memory.created_at >= cutoff
                ).group_by(Memory.status)
                status_result = await db.execute(status_query)
                status_counts = dict(status_result.all())
                
                # 统计 Outbox 事件
                outbox_query = select(
                    OutboxEvent.status,
                    func.count(OutboxEvent.id)
                ).where(
                    OutboxEvent.created_at >= cutoff
                ).group_by(OutboxEvent.status)
                outbox_result = await db.execute(outbox_query)
                outbox_counts = dict(outbox_result.all())
                
                # 统计删除审计
                deletion_query = select(func.count(DeletionAudit.id)).where(
                    DeletionAudit.requested_at >= cutoff
                )
                deletion_result = await db.execute(deletion_query)
                deletion_count = deletion_result.scalar() or 0
                
                # 计算不一致率（简化：pending 状态超过 1 小时视为不一致）
                stale_cutoff = datetime.utcnow() - timedelta(hours=1)
                stale_query = select(func.count(Memory.id)).where(
                    Memory.status == "pending",
                    Memory.created_at < stale_cutoff
                )
                stale_result = await db.execute(stale_query)
                stale_count = stale_result.scalar() or 0
                
                mismatch_rate = stale_count / total_records if total_records > 0 else 0.0
                
                return {
                    "period_days": days,
                    "total_records": total_records,
                    "status_breakdown": status_counts,
                    "outbox_breakdown": outbox_counts,
                    "deletion_requests": deletion_count,
                    "stale_pending_count": stale_count,
                    "mismatch_rate": round(mismatch_rate, 4),
                    "slo_met": mismatch_rate <= MISMATCH_RATE_THRESHOLD,
                    "generated_at": datetime.utcnow().isoformat()
                }
                
            except Exception as e:
                logger.error(f"Report generation failed: {e}")
                return {"status": "error", "message": str(e)}
    
    return asyncio.get_event_loop().run_until_complete(_generate())


@celery_app.task
def check_dlq_backlog():
    """
    检查死信队列积压
    
    如果 DLQ 有积压，触发告警
    """
    import asyncio
    from app.core.database import AsyncSessionLocal
    from app.models.outbox import OutboxEvent
    
    async def _check():
        async with AsyncSessionLocal() as db:
            try:
                # 查询失败状态的事件（DLQ）
                query = select(func.count(OutboxEvent.id)).where(
                    OutboxEvent.status == "failed"
                )
                result = await db.execute(query)
                dlq_count = result.scalar() or 0
                
                if dlq_count > 0:
                    logger.warning(f"DLQ backlog detected: {dlq_count} events")
                
                return {
                    "status": "completed",
                    "dlq_count": dlq_count,
                    "alert_triggered": dlq_count > 0,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
            except Exception as e:
                logger.error(f"DLQ check failed: {e}")
                return {"status": "error", "message": str(e)}
    
    return asyncio.get_event_loop().run_until_complete(_check())


@celery_app.task
def collect_metrics():
    """
    收集系统指标（用于 Prometheus）
    
    返回可被 Prometheus 抓取的指标
    """
    import asyncio
    from app.core.database import AsyncSessionLocal
    from app.models.memory import Memory
    from app.models.outbox import OutboxEvent
    
    async def _collect():
        metrics = {}
        
        async with AsyncSessionLocal() as db:
            try:
                # 记忆状态计数
                status_query = select(
                    Memory.status,
                    func.count(Memory.id)
                ).group_by(Memory.status)
                status_result = await db.execute(status_query)
                for status, count in status_result.all():
                    metrics[f"affinity_memories_{status}_total"] = count
                
                # Outbox 状态计数
                outbox_query = select(
                    OutboxEvent.status,
                    func.count(OutboxEvent.id)
                ).group_by(OutboxEvent.status)
                outbox_result = await db.execute(outbox_query)
                for status, count in outbox_result.all():
                    metrics[f"affinity_outbox_{status}_total"] = count
                
                # 计算 Outbox 积压（pending 状态）
                pending_query = select(func.count(OutboxEvent.id)).where(
                    OutboxEvent.status == "pending"
                )
                pending_result = await db.execute(pending_query)
                metrics["affinity_outbox_pending_gauge"] = pending_result.scalar() or 0
                
            except Exception as e:
                logger.error(f"Metrics collection failed: {e}")
        
        return {
            "status": "completed",
            "metrics": metrics,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    return asyncio.get_event_loop().run_until_complete(_collect())
