"""边权重衰减任务"""
import math
import time
from datetime import datetime
from typing import List, Dict

from app.worker import celery_app
from app.core.config import settings

_sync_neo4j_driver = None


def get_sync_neo4j_driver():
    global _sync_neo4j_driver
    if _sync_neo4j_driver is not None:
        return _sync_neo4j_driver
    from neo4j import GraphDatabase
    _sync_neo4j_driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        max_connection_pool_size=50,
    )
    return _sync_neo4j_driver


def close_sync_neo4j_driver():
    global _sync_neo4j_driver
    if _sync_neo4j_driver is not None:
        try:
            _sync_neo4j_driver.close()
        except Exception:
            pass
        _sync_neo4j_driver = None


@celery_app.task
def batch_update_edge_weights(batch_size: int = 1000):
    """
    夜间批量更新边权重
    
    由 Celery Beat 每日凌晨 3 点调用
    
    策略:
    - 分页处理，避免大事务
    - 防止下溢，设置最小阈值 0.01
    - 限速，避免压垮数据库
    """
    total_updated = 0

    driver = get_sync_neo4j_driver()
    with driver.session() as session:
        while True:
            result = session.run(
                """
                MATCH ()-[r:RELATES_TO]->()
                WHERE r.updated_at < datetime() - duration({days: 1})
                WITH r LIMIT $limit
                SET r.weight = CASE
                    WHEN r.weight * exp(-r.decay_rate * duration.inDays(r.updated_at, datetime()).days) < 0.01 THEN 0.01
                    ELSE r.weight * exp(-r.decay_rate * duration.inDays(r.updated_at, datetime()).days)
                END,
                r.updated_at = datetime()
                RETURN count(r) as updated
                """,
                limit=int(batch_size),
            )
            updated = int((result.single() or {}).get("updated", 0))
            total_updated += updated
            if updated <= 0:
                break
            time.sleep(0.05)
    
    return {
        "status": "completed",
        "total_updated": total_updated,
        "timestamp": datetime.now().isoformat()
    }


def calculate_decayed_weight(
    stored_weight: float,
    decay_rate: float,
    updated_at: datetime
) -> float:
    """
    计算衰减后的权重
    
    公式: weight_new = weight_old × exp(-decay_rate × days)
    
    Args:
        stored_weight: 存储的权重
        decay_rate: 衰减率
        updated_at: 上次更新时间
        
    Returns:
        衰减后的权重
    """
    days = (datetime.now() - updated_at).days
    return stored_weight * math.exp(-decay_rate * days)


@celery_app.task
def refresh_edge_weight(edge_id: str, conversation_id: str):
    """
    刷新边权重（提及时调用）
    
    当用户在对话中提及某个实体时，刷新相关边的权重
    """
    driver = get_sync_neo4j_driver()
    with driver.session() as session:
        session.run(
            """
            MATCH ()-[r]->()
            WHERE r.id = $edge_id
            SET r.weight = 1.0,
                r.updated_at = datetime(),
                r.last_refreshed_conversation_id = $conversation_id,
                r.provenance = coalesce(r.provenance, []) + [$conversation_id]
            """,
            edge_id=edge_id,
            conversation_id=conversation_id,
        )
    
    return {
        "status": "success",
        "edge_id": edge_id,
        "refreshed_at": datetime.now().isoformat()
    }


@celery_app.task
def get_decayed_important_edges(user_id: str, threshold: float = 0.5) -> List[Dict]:
    """
    获取权重衰减到阈值以下的重要关系边
    
    用于触发主动关怀（如 Day 30 场景）
    """
    driver = get_sync_neo4j_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (u:User {id: $user_id})-[r:RELATES_TO]->(e:Entity)
            WHERE r.weight < $threshold
            RETURN r.id as edge_id,
                   e.id as entity_id,
                   e.name as entity_name,
                   r.relation_type as relation_type,
                   r.weight as weight,
                   r.updated_at as updated_at
            ORDER BY r.weight ASC
            LIMIT 200
            """,
            user_id=user_id,
            threshold=float(threshold),
        )
        return [dict(record) for record in result]
