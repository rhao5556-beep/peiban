"""Prometheus 指标端点"""
from fastapi import APIRouter, Response
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal

router = APIRouter()


async def get_metrics_text() -> str:
    """生成 Prometheus 格式的指标"""
    lines = []
    
    async with AsyncSessionLocal() as db:
        try:
            from app.models.memory import Memory
            from app.models.outbox import OutboxEvent
            
            # 记忆状态计数
            status_query = select(
                Memory.status,
                func.count(Memory.id)
            ).group_by(Memory.status)
            status_result = await db.execute(status_query)
            
            lines.append("# HELP affinity_memories_total Total number of memories by status")
            lines.append("# TYPE affinity_memories_total gauge")
            for status, count in status_result.all():
                lines.append(f'affinity_memories_total{{status="{status}"}} {count}')
            
            # Outbox 状态计数
            outbox_query = select(
                OutboxEvent.status,
                func.count(OutboxEvent.id)
            ).group_by(OutboxEvent.status)
            outbox_result = await db.execute(outbox_query)
            
            lines.append("# HELP affinity_outbox_events_total Total outbox events by status")
            lines.append("# TYPE affinity_outbox_events_total gauge")
            for status, count in outbox_result.all():
                lines.append(f'affinity_outbox_events_total{{status="{status}"}} {count}')
            
            # Outbox 积压（pending 超过 30 秒）
            stale_cutoff = datetime.utcnow() - timedelta(seconds=30)
            stale_query = select(func.count(OutboxEvent.id)).where(
                OutboxEvent.status == "pending",
                OutboxEvent.created_at < stale_cutoff
            )
            stale_result = await db.execute(stale_query)
            stale_count = stale_result.scalar() or 0
            
            lines.append("# HELP affinity_outbox_stale_count Stale pending outbox events (>30s)")
            lines.append("# TYPE affinity_outbox_stale_count gauge")
            lines.append(f"affinity_outbox_stale_count {stale_count}")
            
            # 计算平均处理延迟
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            lag_query = select(OutboxEvent).where(
                OutboxEvent.status == "done",
                OutboxEvent.processed_at >= one_hour_ago
            ).limit(1000)
            lag_result = await db.execute(lag_query)
            events = lag_result.scalars().all()
            
            if events:
                lags = []
                for event in events:
                    if event.processed_at and event.created_at:
                        lag_ms = (event.processed_at - event.created_at).total_seconds() * 1000
                        lags.append(lag_ms)
                
                if lags:
                    import statistics
                    avg_lag = statistics.mean(lags)
                    p50_lag = statistics.median(lags)
                    sorted_lags = sorted(lags)
                    p95_idx = int(len(sorted_lags) * 0.95)
                    p95_lag = sorted_lags[min(p95_idx, len(sorted_lags) - 1)]
                    
                    lines.append("# HELP affinity_outbox_lag_ms Outbox processing lag in milliseconds")
                    lines.append("# TYPE affinity_outbox_lag_ms gauge")
                    lines.append(f'affinity_outbox_lag_ms{{quantile="0.5"}} {p50_lag:.2f}')
                    lines.append(f'affinity_outbox_lag_ms{{quantile="0.95"}} {p95_lag:.2f}')
                    lines.append(f'affinity_outbox_lag_ms{{quantile="avg"}} {avg_lag:.2f}')
            
            # DLQ 计数
            dlq_query = select(func.count(OutboxEvent.id)).where(
                OutboxEvent.status == "failed"
            )
            dlq_result = await db.execute(dlq_query)
            dlq_count = dlq_result.scalar() or 0
            
            lines.append("# HELP affinity_dlq_count Dead letter queue count")
            lines.append("# TYPE affinity_dlq_count gauge")
            lines.append(f"affinity_dlq_count {dlq_count}")
            
        except Exception as e:
            lines.append(f"# Error collecting metrics: {e}")
    
    return "\n".join(lines)


@router.get("/metrics")
async def prometheus_metrics():
    """Prometheus 指标端点"""
    metrics_text = await get_metrics_text()
    return Response(
        content=metrics_text,
        media_type="text/plain; charset=utf-8"
    )


@router.get("/health")
async def health_check():
    """健康检查端点"""
    from app.core.database import redis_client, neo4j_driver, milvus_connected
    
    health = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {}
    }
    
    # 检查 Redis
    try:
        if redis_client:
            await redis_client.ping()
            health["components"]["redis"] = "healthy"
        else:
            health["components"]["redis"] = "not_configured"
    except Exception as e:
        health["components"]["redis"] = f"unhealthy: {e}"
        health["status"] = "degraded"
    
    # 检查 Neo4j
    try:
        if neo4j_driver:
            async with neo4j_driver.session() as session:
                await session.run("RETURN 1")
            health["components"]["neo4j"] = "healthy"
        else:
            health["components"]["neo4j"] = "not_configured"
    except Exception as e:
        health["components"]["neo4j"] = f"unhealthy: {e}"
        health["status"] = "degraded"
    
    # 检查 Milvus
    health["components"]["milvus"] = "healthy" if milvus_connected else "not_connected"
    
    # 检查 Postgres
    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import text
            await db.execute(text("SELECT 1"))
        health["components"]["postgres"] = "healthy"
    except Exception as e:
        health["components"]["postgres"] = f"unhealthy: {e}"
        health["status"] = "unhealthy"
    
    return health
