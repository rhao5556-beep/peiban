"""
IR Critic 服务 - 对 LLM 抽取结果进行二次校验

职责：
1. 置信度过滤：confidence < 0.5 的实体/关系丢弃
2. 实体类型校验：确保类型在允许列表内
3. 关系类型校验：确保关系类型合法
4. 自环检测：source == target 的关系丢弃
5. 重复检测：去除重复的实体和关系

架构决策：
- IR Critic 是"过滤器"，不是"增强器"
- 宁可漏掉，不可错写（高精度优先）
- 所有过滤操作记录日志，便于调试
"""
import logging
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 允许的实体类型
ALLOWED_ENTITY_TYPES = {
    "Person", "Location", "Organization", 
    "Event", "Preference", "TimeExpression", "Duration", "Quantity", "Other"
}

# 允许的关系类型
ALLOWED_RELATION_TYPES = {
    # 家庭关系
    "FAMILY", "PARENT_OF", "CHILD_OF", "SIBLING_OF", "COUSIN_OF",
    # 社交关系
    "FRIEND_OF", "COLLEAGUE_OF", "CLASSMATE_OF",
    # 地理关系
    "FROM", "LIVES_IN", "WORKS_AT",
    # 偏好关系
    "LIKES", "DISLIKES",
    # 时间关系
    "HAPPENED_AT", "LASTED",
    # 数值关系
    "COST",
    # 其他
    "RELATED_TO"
}

# 置信度阈值
CONFIDENCE_THRESHOLD = 0.5


@dataclass
class CriticResult:
    """Critic 校验结果"""
    entities: List[Dict[str, Any]]
    relations: List[Dict[str, Any]]
    filtered_entities: List[Dict[str, Any]]  # 被过滤的实体
    filtered_relations: List[Dict[str, Any]]  # 被过滤的关系
    stats: Dict[str, int]  # 统计信息


def critique_ir(
    entities: List[Dict[str, Any]],
    relations: List[Dict[str, Any]],
    strict_mode: bool = False
) -> CriticResult:
    """
    对 LLM 抽取的 IR 进行二次校验
    
    Args:
        entities: LLM 抽取的实体列表
        relations: LLM 抽取的关系列表
        strict_mode: 严格模式（更高的置信度阈值）
    
    Returns:
        CriticResult: 校验后的结果
    """
    threshold = 0.7 if strict_mode else CONFIDENCE_THRESHOLD
    
    valid_entities = []
    filtered_entities = []
    valid_relations = []
    filtered_relations = []
    
    stats = {
        "input_entities": len(entities),
        "input_relations": len(relations),
        "filtered_low_confidence_entities": 0,
        "filtered_invalid_type_entities": 0,
        "filtered_low_confidence_relations": 0,
        "filtered_invalid_type_relations": 0,
        "filtered_self_loop_relations": 0,
        "filtered_duplicate_entities": 0,
        "filtered_duplicate_relations": 0,
    }
    
    # ========== 实体校验 ==========
    seen_entity_ids = set()
    
    for ent in entities:
        ent_id = ent.get("id", "")
        ent_name = ent.get("name", "")
        ent_type = ent.get("type", "Other")
        confidence = float(ent.get("confidence", 0.8))
        is_user = ent.get("is_user", False)
        
        # 用户节点始终保留
        if is_user or ent_id == "user":
            if ent_id not in seen_entity_ids:
                valid_entities.append(ent)
                seen_entity_ids.add(ent_id)
            continue
        
        # 1. 置信度过滤
        if confidence < threshold:
            stats["filtered_low_confidence_entities"] += 1
            filtered_entities.append({
                **ent,
                "filter_reason": f"low_confidence ({confidence:.2f} < {threshold})"
            })
            logger.debug(f"Filtered entity '{ent_name}': low confidence {confidence:.2f}")
            continue
        
        # 2. 类型校验
        if ent_type not in ALLOWED_ENTITY_TYPES:
            stats["filtered_invalid_type_entities"] += 1
            filtered_entities.append({
                **ent,
                "filter_reason": f"invalid_type ({ent_type})"
            })
            logger.debug(f"Filtered entity '{ent_name}': invalid type {ent_type}")
            continue
        
        # 3. 重复检测
        if ent_id in seen_entity_ids:
            stats["filtered_duplicate_entities"] += 1
            filtered_entities.append({
                **ent,
                "filter_reason": "duplicate"
            })
            logger.debug(f"Filtered entity '{ent_name}': duplicate id {ent_id}")
            continue
        
        # 4. 空名称检测
        if not ent_name or not ent_name.strip():
            filtered_entities.append({
                **ent,
                "filter_reason": "empty_name"
            })
            logger.debug(f"Filtered entity: empty name")
            continue
        
        valid_entities.append(ent)
        seen_entity_ids.add(ent_id)
    
    # ========== 关系校验 ==========
    seen_relations = set()
    
    for rel in relations:
        source = rel.get("source", "")
        target = rel.get("target", "")
        rel_type = rel.get("type", "RELATED_TO").upper()
        confidence = float(rel.get("confidence", 0.8))
        
        # 1. 自环检测
        if source == target:
            stats["filtered_self_loop_relations"] += 1
            filtered_relations.append({
                **rel,
                "filter_reason": "self_loop"
            })
            logger.debug(f"Filtered relation: self loop {source} -> {target}")
            continue
        
        # 2. 置信度过滤
        if confidence < threshold:
            stats["filtered_low_confidence_relations"] += 1
            filtered_relations.append({
                **rel,
                "filter_reason": f"low_confidence ({confidence:.2f} < {threshold})"
            })
            logger.debug(f"Filtered relation {source}->{target}: low confidence {confidence:.2f}")
            continue
        
        # 3. 关系类型校验
        if rel_type not in ALLOWED_RELATION_TYPES:
            stats["filtered_invalid_type_relations"] += 1
            filtered_relations.append({
                **rel,
                "filter_reason": f"invalid_type ({rel_type})"
            })
            logger.debug(f"Filtered relation {source}->{target}: invalid type {rel_type}")
            continue
        
        # 4. 源/目标存在性检查（必须在有效实体中）
        if source != "user" and source not in seen_entity_ids:
            filtered_relations.append({
                **rel,
                "filter_reason": f"source_not_found ({source})"
            })
            logger.debug(f"Filtered relation: source {source} not in valid entities")
            continue
        
        if target not in seen_entity_ids:
            filtered_relations.append({
                **rel,
                "filter_reason": f"target_not_found ({target})"
            })
            logger.debug(f"Filtered relation: target {target} not in valid entities")
            continue
        
        # 5. 重复检测（同源同目标同类型）
        rel_key = (source, target, rel_type)
        if rel_key in seen_relations:
            stats["filtered_duplicate_relations"] += 1
            filtered_relations.append({
                **rel,
                "filter_reason": "duplicate"
            })
            logger.debug(f"Filtered relation: duplicate {source}-[{rel_type}]->{target}")
            continue
        
        valid_relations.append(rel)
        seen_relations.add(rel_key)
    
    # 更新统计
    stats["output_entities"] = len(valid_entities)
    stats["output_relations"] = len(valid_relations)
    stats["total_filtered_entities"] = len(filtered_entities)
    stats["total_filtered_relations"] = len(filtered_relations)
    
    logger.info(
        f"IR Critic: {stats['input_entities']} entities -> {stats['output_entities']}, "
        f"{stats['input_relations']} relations -> {stats['output_relations']}"
    )
    
    return CriticResult(
        entities=valid_entities,
        relations=valid_relations,
        filtered_entities=filtered_entities,
        filtered_relations=filtered_relations,
        stats=stats
    )


def validate_entity(entity: Dict[str, Any], threshold: float = CONFIDENCE_THRESHOLD) -> Tuple[bool, str]:
    """
    校验单个实体
    
    Returns:
        (is_valid, reason)
    """
    ent_type = entity.get("type", "Other")
    confidence = float(entity.get("confidence", 0.8))
    name = entity.get("name", "")
    
    if not name or not name.strip():
        return False, "empty_name"
    
    if confidence < threshold:
        return False, f"low_confidence ({confidence:.2f})"
    
    if ent_type not in ALLOWED_ENTITY_TYPES:
        return False, f"invalid_type ({ent_type})"
    
    return True, "valid"


def validate_relation(
    relation: Dict[str, Any],
    valid_entity_ids: set,
    threshold: float = CONFIDENCE_THRESHOLD
) -> Tuple[bool, str]:
    """
    校验单个关系
    
    Returns:
        (is_valid, reason)
    """
    source = relation.get("source", "")
    target = relation.get("target", "")
    rel_type = relation.get("type", "RELATED_TO").upper()
    confidence = float(relation.get("confidence", 0.8))
    
    if source == target:
        return False, "self_loop"
    
    if confidence < threshold:
        return False, f"low_confidence ({confidence:.2f})"
    
    if rel_type not in ALLOWED_RELATION_TYPES:
        return False, f"invalid_type ({rel_type})"
    
    if source != "user" and source not in valid_entity_ids:
        return False, f"source_not_found ({source})"
    
    if target not in valid_entity_ids:
        return False, f"target_not_found ({target})"
    
    return True, "valid"
