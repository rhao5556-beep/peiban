"""边权重衰减任务"""
import math
from datetime import datetime
from typing import List, Dict

from app.worker import celery_app


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
    
    # TODO: 实现完整的批量更新逻辑
    # while True:
    #     edges = fetch_edges_for_decay(limit=batch_size, min_days_since_update=1)
    #     
    #     if not edges:
    #         break
    #     
    #     for edge in edges:
    #         new_weight = calculate_decayed_weight(
    #             edge.weight,
    #             edge.decay_rate,
    #             edge.updated_at
    #         )
    #         
    #         # 防止下溢
    #         if new_weight < 0.01:
    #             new_weight = 0.01
    #         
    #         update_edge_weight(edge.id, new_weight)
    #         total_updated += 1
    #     
    #     # 限速
    #     time.sleep(0.1)
    
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
    # TODO: 实现边权重刷新
    # 1. 获取边当前状态
    # 2. 重置权重为 1.0（或增加权重）
    # 3. 更新 updated_at
    # 4. 添加 provenance
    
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
    # TODO: 实现查询逻辑
    # 返回需要主动关怀的关系列表
    
    return []
