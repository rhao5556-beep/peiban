"""Outbox 任务 - 异步写入 Neo4j 和 Milvus

架构决策：
- All-in LLM 实体抽取，不做正则降级
- 必须传入 recent_entities 作为实体消歧上下文
- 失败不写入 Neo4j，标记 pending_review
- 重试属于 delivery reliability，不是语义降级
"""
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List

from app.worker import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


def get_sync_db_session():
    """获取同步数据库会话（用于 Celery worker）"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    sync_url = settings.DATABASE_URL  # 已经是同步 URL
    engine = create_engine(sync_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    return Session()


def get_recent_entities(user_id: str, limit: int = 50) -> List[Dict]:
    """从 Neo4j 获取用户最近的实体，用于 LLM 消歧
    
    注意：实体节点使用动态标签（Person, Location 等），不是 Entity
    """
    from neo4j import GraphDatabase
    
    try:
        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
        
        with driver.session() as session:
            # 查询所有带 user_id 的节点（排除 User 节点）
            result = session.run(
                """
                MATCH (e {user_id: $user_id})
                WHERE NOT e:User
                RETURN e.id AS id, e.name AS name, e.type AS type
                ORDER BY e.last_mentioned_at DESC
                LIMIT $limit
                """,
                user_id=user_id,
                limit=limit
            )
            entities = [{"id": r["id"], "name": r["name"], "type": r["type"]} for r in result]
        
        driver.close()
        logger.info(f"Got {len(entities)} recent entities for user {user_id[:8]}")
        return entities
        
    except Exception as e:
        logger.warning(f"Failed to get recent entities: {e}")
        return []


@celery_app.task(bind=True, max_retries=settings.OUTBOX_MAX_RETRIES)
def process_outbox_event(self, event_id: str, payload: Dict[str, Any]):
    """
    处理单个 Outbox 事件
    
    流程：
    1. LLM 抽取实体和关系
    2. 写入 Milvus（向量存储）
    3. 写入 Neo4j（图谱存储）
    
    失败策略：
    - LLM 失败 → Celery 重试
    - 超过重试次数 → 标记 pending_review，不写入 Neo4j
    """
    from sqlalchemy import text
    from app.services.llm_extraction_service import extract_ir
    
    db = get_sync_db_session()
    
    try:
        # 1. 幂等检查 - 标记为 processing（允许重试时重新处理）
        result = db.execute(
            text("""
                UPDATE outbox_events 
                SET status = 'processing'
                WHERE event_id = :event_id AND status IN ('pending', 'processing')
                RETURNING id
            """),
            {"event_id": event_id}
        )
        if result.rowcount == 0:
            logger.info(f"Event {event_id} already processed (done/dlq/pending_review)")
            db.close()
            return {"status": "skipped", "reason": "already_processed"}
        
        db.commit()
        
        memory_id = payload.get("memory_id")
        user_id = payload.get("user_id")
        content = payload.get("content")
        embedding = payload.get("embedding")
        
        # 2. 获取用户已有实体（用于 LLM 消歧）
        context_entities = get_recent_entities(user_id)
        
        # 3. LLM 实体抽取
        extraction_result = extract_ir(
            text=content,
            user_id=user_id,
            context_entities=context_entities
        )
        
        # 4. 检查抽取结果
        if not extraction_result.success:
            # LLM 抽取失败，进入重试
            retry_count = self.request.retries
            
            if retry_count < settings.OUTBOX_MAX_RETRIES:
                countdown = settings.OUTBOX_BACKOFF_BASE ** retry_count
                logger.warning(f"LLM extraction failed, retrying in {countdown}s (attempt {retry_count + 1})")
                raise self.retry(exc=Exception(extraction_result.error), countdown=countdown)
            else:
                # 超过重试次数，标记 pending_review，但仍然提交记忆（避免前端一直显示"记忆中..."）
                logger.error(f"LLM extraction failed after {retry_count + 1} attempts, marking pending_review but committing memory")
                db.execute(
                    text("""
                        UPDATE outbox_events 
                        SET status = 'pending_review', 
                            error_message = :error,
                            processed_at = NOW()
                        WHERE event_id = :event_id
                    """),
                    {"event_id": event_id, "error": extraction_result.error}
                )
                
                # 即使 LLM 失败，也要提交记忆，避免前端一直显示"记忆中..."
                db.execute(
                    text("""
                        UPDATE memories 
                        SET status = 'committed', committed_at = NOW()
                        WHERE id = :id
                    """),
                    {"id": memory_id}
                )
                
                db.commit()
                return {
                    "status": "pending_review",
                    "event_id": event_id,
                    "memory_id": memory_id,
                    "error": extraction_result.error,
                    "note": "Memory committed despite LLM failure to avoid frontend stuck in 'remembering' state"
                }
        
        # 4.5 IR Critic - 二次校验（过滤低置信度/无效类型）
        from app.services.ir_critic_service import critique_ir
        
        critic_result = critique_ir(
            entities=extraction_result.entities,
            relations=extraction_result.relations,
            strict_mode=False  # 正常模式，threshold=0.5
        )
        
        logger.info(
            f"IR Critic stats: entities {critic_result.stats['input_entities']}->{critic_result.stats['output_entities']}, "
            f"relations {critic_result.stats['input_relations']}->{critic_result.stats['output_relations']}"
        )
        
        # 使用校验后的实体和关系
        validated_entities = critic_result.entities
        validated_relations = critic_result.relations
        
        # 5. 写入 Milvus
        milvus_id = write_to_milvus_sync(
            memory_id=memory_id,
            user_id=user_id,
            content=content,
            embedding=embedding,
            valence=payload.get("valence", 0)
        )
        
        # 6. 写入 Neo4j（使用 IR Critic 校验后的结果）
        neo4j_result = write_ir_to_neo4j(
            user_id=user_id,
            entities=validated_entities,
            relations=validated_relations,
            metadata=extraction_result.metadata,
            conversation_id=payload.get("conversation_id")
        )

        try:
            memory_entities_rows = []
            for ent in validated_entities:
                if ent.get("is_user") or ent.get("id") == "user":
                    continue
                ent_id = ent.get("id")
                if not ent_id:
                    continue
                memory_entities_rows.append(
                    {
                        "user_id": user_id,
                        "memory_id": memory_id,
                        "entity_id": str(ent_id),
                        "entity_name": ent.get("name"),
                        "entity_type": ent.get("type"),
                        "confidence": float(ent.get("confidence") or 0.8),
                    }
                )

            if memory_entities_rows:
                db.execute(
                    text(
                        """
                        INSERT INTO memory_entities (user_id, memory_id, entity_id, entity_name, entity_type, confidence, source)
                        VALUES (:user_id, :memory_id, :entity_id, :entity_name, :entity_type, :confidence, 'llm')
                        ON CONFLICT (user_id, memory_id, entity_id) DO NOTHING
                        """
                    ),
                    memory_entities_rows,
                )
        except Exception as e:
            logger.warning(f"Failed to write memory_entities: {e}")
        
        # 7. 更新 Outbox 状态为 done
        db.execute(
            text("""
                UPDATE outbox_events 
                SET status = 'done', processed_at = NOW()
                WHERE event_id = :event_id
            """),
            {"event_id": event_id}
        )
        
        # 8. 更新 Memory 状态为 committed
        db.execute(
            text("""
                UPDATE memories 
                SET status = 'committed', committed_at = NOW()
                WHERE id = :id
            """),
            {"id": memory_id}
        )
        
        db.commit()
        
        logger.info(f"Event {event_id} processed successfully")
        return {
            "status": "success",
            "event_id": event_id,
            "memory_id": memory_id,
            "milvus_id": milvus_id,
            "neo4j_result": neo4j_result,
            "entities_count": len(validated_entities),
            "relations_count": len(validated_relations),
            "critic_stats": critic_result.stats,
            "processed_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Event {event_id} processing failed: {e}")
        
        retry_count = self.request.retries
        
        if retry_count < settings.OUTBOX_MAX_RETRIES:
            countdown = settings.OUTBOX_BACKOFF_BASE ** retry_count
            logger.info(f"Retrying event {event_id} in {countdown}s (attempt {retry_count + 1})")
            raise self.retry(exc=e, countdown=countdown)
        else:
            move_to_dlq_sync(event_id, str(e))
            return {
                "status": "failed",
                "event_id": event_id,
                "error": str(e),
                "moved_to_dlq": True
            }
    finally:
        db.close()


@celery_app.task
def process_pending_events():
    """批量处理待处理的 Outbox 事件"""
    from sqlalchemy import text
    
    db = get_sync_db_session()
    
    try:
        result = db.execute(
            text("""
                SELECT event_id, payload 
                FROM outbox_events 
                WHERE status = 'pending'
                ORDER BY created_at
                LIMIT 100
            """)
        )
        pending_events = result.fetchall()
        
        processed_count = 0
        for event_id, payload in pending_events:
            payload_dict = json.loads(payload) if isinstance(payload, str) else payload
            process_outbox_event.delay(event_id, payload_dict)
            processed_count += 1
        
        logger.info(f"Dispatched {processed_count} pending events")
        return {
            "status": "completed",
            "processed_count": processed_count,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to process pending events: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


@celery_app.task
def process_failed_events():
    """重试失败的事件"""
    from sqlalchemy import text
    
    db = get_sync_db_session()
    
    try:
        result = db.execute(
            text("""
                SELECT event_id, payload, retry_count
                FROM outbox_events 
                WHERE status = 'failed' AND retry_count < :max_retries
                ORDER BY created_at
                LIMIT 50
            """),
            {"max_retries": settings.OUTBOX_MAX_RETRIES}
        )
        failed_events = result.fetchall()
        
        retried_count = 0
        for event_id, payload, retry_count in failed_events:
            payload_dict = json.loads(payload) if isinstance(payload, str) else payload
            process_outbox_event.delay(event_id, payload_dict)
            retried_count += 1
        
        logger.info(f"Retried {retried_count} failed events")
        return {"status": "completed", "retried_count": retried_count}
        
    except Exception as e:
        logger.error(f"Failed to process failed events: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


@celery_app.task
def process_dlq_events():
    """处理死信队列中的事件"""
    from sqlalchemy import text
    
    db = get_sync_db_session()
    
    try:
        result = db.execute(
            text("""
                SELECT event_id, payload, error_message, created_at
                FROM outbox_events 
                WHERE status = 'dlq'
                ORDER BY created_at
                LIMIT 100
            """)
        )
        dlq_events = result.fetchall()
        
        for event_id, payload, error_message, created_at in dlq_events:
            logger.warning(f"DLQ Event: {event_id}, Error: {error_message}")
        
        return {
            "status": "completed",
            "dlq_count": len(dlq_events),
            "events": [{"event_id": e[0], "error": e[2]} for e in dlq_events[:10]]
        }
        
    except Exception as e:
        logger.error(f"Failed to process DLQ: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


def move_to_dlq_sync(event_id: str, error_message: str):
    """将事件移入死信队列"""
    from sqlalchemy import text
    
    db = get_sync_db_session()
    
    try:
        db.execute(
            text("""
                UPDATE outbox_events 
                SET status = 'dlq', error_message = :error_message
                WHERE event_id = :event_id
            """),
            {"event_id": event_id, "error_message": error_message}
        )
        db.commit()
        logger.warning(f"Event {event_id} moved to DLQ: {error_message}")
    except Exception as e:
        logger.error(f"Failed to move event to DLQ: {e}")
    finally:
        db.close()


# ============================================================================
# 关系权重配置（LLM 输出的关系类型映射）
# ============================================================================

RELATION_WEIGHT_CONFIG = {
    # 核心关系 - 家人、最亲密的人
    "FAMILY": (0.95, 0.05 / 30),
    "PARENT_OF": (0.95, 0.05 / 30),
    "CHILD_OF": (0.95, 0.05 / 30),
    "SIBLING_OF": (0.90, 0.05 / 30),
    "COUSIN_OF": (0.85, 0.08 / 30),
    
    # 重要社交关系
    "FRIEND_OF": (0.7, 0.1 / 30),
    "COLLEAGUE_OF": (0.65, 0.12 / 30),
    "CLASSMATE_OF": (0.65, 0.12 / 30),
    
    # 一般关系
    "LIKES": (0.5, 0.2 / 30),
    "DISLIKES": (0.5, 0.2 / 30),
    "FROM": (0.6, 0.15 / 30),
    "LIVES_IN": (0.6, 0.15 / 30),
    "WORKS_AT": (0.6, 0.15 / 30),
    
    # 弱关系
    "RELATED_TO": (0.4, 0.3 / 30),
    "OTHER": (0.3, 0.5 / 30),
    
    # 默认
    "default": (0.5, 0.2 / 30)
}


def get_weight_for_relation(relation_type: str) -> tuple:
    """根据关系类型获取权重配置"""
    return RELATION_WEIGHT_CONFIG.get(relation_type.upper(), RELATION_WEIGHT_CONFIG["default"])


def write_ir_to_neo4j(
    user_id: str,
    entities: List[Dict],
    relations: List[Dict],
    metadata: Dict,
    conversation_id: str
) -> Dict:
    """
    将 LLM 抽取的 IR 写入 Neo4j
    
    支持：
    - User → Entity 关系
    - Entity → Entity 关系（网状结构）
    - 带 provenance 的审计信息
    """
    from neo4j import GraphDatabase
    
    try:
        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
        
        created_entities = []
        created_relations = []
        
        with driver.session() as session:
            # 1. 确保用户节点存在
            session.run(
                """
                MERGE (u:User {id: $user_id})
                ON CREATE SET u.created_at = datetime(), u.name = '我'
                """,
                user_id=user_id
            )
            
            # 2. 创建/更新实体节点
            for ent in entities:
                ent_id = ent.get("id", str(uuid.uuid4()))
                ent_type = ent.get("type", "Other")
                is_user = ent.get("is_user", False)
                
                # 跳过 user 节点（已经创建）
                if is_user or ent_id == "user":
                    continue
                
                # 使用动态标签，MERGE 时包含 user_id 确保用户隔离
                label = ent_type if ent_type in ["Person", "Location", "Organization", "Event", "Preference"] else "Other"
                
                result = session.run(
                    f"""
                    MERGE (e:{label} {{id: $id, user_id: $user_id}})
                    ON CREATE SET 
                        e.name = $name,
                        e.type = $type,
                        e.confidence = $confidence,
                        e.created_at = datetime(),
                        e.last_mentioned_at = datetime(),
                        e.mention_count = 1,
                        e.source = $source,
                        e.model_version = $model_version
                    ON MATCH SET 
                        e.last_mentioned_at = datetime(),
                        e.mention_count = e.mention_count + 1
                    RETURN e.id AS id
                    """,
                    id=ent_id,
                    name=ent.get("name", ""),
                    type=ent_type,
                    user_id=user_id,
                    confidence=float(ent.get("confidence", 0.8)),
                    source=metadata.get("source", "llm"),
                    model_version=metadata.get("model_version", "unknown")
                )
                record = result.single()
                if record:
                    created_entities.append(record["id"])
            
            # 3. 创建关系（支持 Entity → Entity）
            for rel in relations:
                source_id = rel.get("source")
                target_id = rel.get("target")
                rel_type = rel.get("type", "RELATED_TO").upper()
                
                if not source_id or not target_id:
                    continue
                
                # 获取权重配置
                weight, decay_rate = get_weight_for_relation(rel_type)
                # 如果 LLM 提供了权重，使用 LLM 的
                if "weight" in rel:
                    weight = float(rel["weight"])
                
                # 确定源节点类型（user 或 entity）
                if source_id == "user":
                    # User → Entity
                    session.run(
                        f"""
                        MATCH (u:User {{id: $user_id}})
                        MATCH (e {{id: $target_id, user_id: $user_id}})
                        MERGE (u)-[r:{rel_type}]->(e)
                        ON CREATE SET 
                            r.id = $rel_id,
                            r.desc = $desc,
                            r.weight = $weight,
                            r.decay_rate = $decay_rate,
                            r.confidence = $confidence,
                            r.created_at = datetime(),
                            r.updated_at = datetime(),
                            r.source = $source
                        ON MATCH SET 
                            r.updated_at = datetime(),
                            r.weight = CASE WHEN r.weight < $weight THEN $weight ELSE r.weight END
                        """,
                        user_id=user_id,
                        target_id=target_id,
                        rel_id=str(uuid.uuid4()),
                        desc=rel.get("desc", ""),
                        weight=weight,
                        decay_rate=decay_rate,
                        confidence=float(rel.get("confidence", 0.8)),
                        source=metadata.get("source", "llm")
                    )
                else:
                    # Entity → Entity（网状结构的关键）
                    session.run(
                        f"""
                        MATCH (a {{id: $source_id, user_id: $user_id}})
                        MATCH (b {{id: $target_id, user_id: $user_id}})
                        MERGE (a)-[r:{rel_type}]->(b)
                        ON CREATE SET 
                            r.id = $rel_id,
                            r.desc = $desc,
                            r.weight = $weight,
                            r.decay_rate = $decay_rate,
                            r.confidence = $confidence,
                            r.created_at = datetime(),
                            r.updated_at = datetime(),
                            r.source = $source
                        ON MATCH SET 
                            r.updated_at = datetime(),
                            r.weight = CASE WHEN r.weight < $weight THEN $weight ELSE r.weight END
                        """,
                        source_id=source_id,
                        target_id=target_id,
                        user_id=user_id,
                        rel_id=str(uuid.uuid4()),
                        desc=rel.get("desc", ""),
                        weight=weight,
                        decay_rate=decay_rate,
                        confidence=float(rel.get("confidence", 0.8)),
                        source=metadata.get("source", "llm")
                    )
                
                created_relations.append(f"{source_id}->{target_id}")
        
        driver.close()
        logger.info(f"Wrote {len(created_entities)} entities and {len(created_relations)} relations to Neo4j")
        
        return {
            "entities_created": len(created_entities),
            "relations_created": len(created_relations),
            "entity_ids": created_entities
        }
        
    except Exception as e:
        logger.error(f"Failed to write IR to Neo4j: {e}")
        return {"error": str(e), "entities_created": 0, "relations_created": 0}


def write_to_milvus_sync(
    memory_id: str,
    user_id: str,
    content: str,
    embedding: List[float],
    valence: float
) -> str:
    """写入 Milvus 向量存储（同步版本）"""
    from pymilvus import connections, Collection, utility
    
    try:
        try:
            connections.connect(
                alias="default",
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT
            )
        except Exception:
            pass
        
        if not utility.has_collection(settings.MILVUS_COLLECTION):
            logger.warning(f"Milvus collection {settings.MILVUS_COLLECTION} not found")
            return None
        
        collection = Collection(settings.MILVUS_COLLECTION)
        
        # 确保 embedding 是正确的维度
        if embedding is None or len(embedding) == 0:
            embedding = [0.0] * 1024
        elif len(embedding) != 1024:
            if len(embedding) < 1024:
                embedding = embedding + [0.0] * (1024 - len(embedding))
            else:
                embedding = embedding[:1024]
        
        data = [{
            "id": memory_id,
            "user_id": user_id,
            "content": content[:4096] if content else "",
            "embedding": embedding,
            "valence": float(valence) if valence else 0.0,
            "created_at": int(datetime.now().timestamp()),
        }]
        
        result = collection.insert(data)
        collection.flush()
        
        logger.info(f"Inserted memory {memory_id} into Milvus")
        return memory_id
        
    except Exception as e:
        logger.error(f"Failed to write to Milvus: {e}")
        return None


def write_to_neo4j_sync(
    user_id: str,
    entities: List[Dict],
    edges: List[Dict],
    conversation_id: str
) -> List[str]:
    """写入 Neo4j 图谱（同步版本）"""
    from neo4j import GraphDatabase
    
    try:
        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
        
        created_ids = []
        
        with driver.session() as session:
            # 确保用户节点存在（使用 user_id 作为 id）
            session.run(
                """
                MERGE (u:User {id: $user_id})
                ON CREATE SET u.created_at = datetime()
                """,
                user_id=user_id
            )
            
            # 创建实体节点
            for entity in entities:
                result = session.run(
                    """
                    MERGE (e:Entity {id: $id, user_id: $user_id})
                    ON CREATE SET e.name = $name, e.type = $type, 
                                  e.created_at = datetime(), e.mention_count = 1
                    ON MATCH SET e.mention_count = e.mention_count + 1
                    RETURN e.id as id
                    """,
                    id=entity["id"],
                    user_id=user_id,
                    name=entity["name"],
                    type=entity["type"]
                )
                record = result.single()
                if record:
                    created_ids.append(record["id"])
            
            # 创建关系（source 是 User 节点，target 是 Entity 节点）
            for edge in edges:
                # 获取边的权重配置（如果没有则使用默认值）
                weight = edge.get("weight", 0.5)
                decay_rate = edge.get("decay_rate", 0.2 / 30)
                
                session.run(
                    """
                    MATCH (u:User {id: $source_id})
                    MATCH (e:Entity {id: $target_id})
                    MERGE (u)-[r:RELATES_TO]->(e)
                    ON CREATE SET r.id = $edge_id, r.relation_type = $relation_type, 
                                  r.weight = $weight, r.decay_rate = $decay_rate,
                                  r.created_at = datetime(), r.updated_at = datetime()
                    ON MATCH SET r.weight = CASE 
                                   WHEN r.weight < $weight THEN $weight 
                                   ELSE r.weight 
                                 END,
                                 r.updated_at = datetime()
                    """,
                    edge_id=str(uuid.uuid4()),
                    source_id=edge["source_id"],
                    target_id=edge["target_id"],
                    relation_type=edge["relation_type"],
                    weight=weight,
                    decay_rate=decay_rate
                )
        
        driver.close()
        logger.info(f"Wrote {len(entities)} entities and {len(edges)} edges to Neo4j")
        return created_ids
        
    except Exception as e:
        logger.error(f"Failed to write to Neo4j: {e}")
        return []
