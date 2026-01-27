"""图谱端点"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from datetime import datetime

from app.core.security import get_current_user
from app.core.database import get_neo4j_driver
from app.services.graph_service import GraphService

router = APIRouter()


class Entity(BaseModel):
    """实体"""
    id: str
    name: str
    type: str  # person, place, preference, event
    mention_count: int = 1
    first_mentioned_at: Optional[datetime] = None
    last_mentioned_at: Optional[datetime] = None


class Edge(BaseModel):
    """关系边"""
    id: str
    source_id: str
    target_id: str
    relation_type: str  # family, friend, like, concern
    weight: float = 1.0
    current_weight: Optional[float] = None  # 衰减后的当前权重
    decay_rate: float = 0.03
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GraphData(BaseModel):
    """图谱数据"""
    nodes: List[Entity]
    edges: List[Edge]


class GraphSnapshot(BaseModel):
    """图谱快照（用于时间轴）"""
    timestamp: datetime
    node_count: int
    edge_count: int
    data: GraphData


@router.get("/", response_model=GraphData)
async def get_graph(
    current_user: dict = Depends(get_current_user)
):
    """获取用户完整图谱"""
    user_id = current_user["user_id"]
    
    # 从 Neo4j 获取图谱
    neo4j_driver = get_neo4j_driver()
    graph_service = GraphService(neo4j_driver=neo4j_driver)
    
    try:
        graph_data = await graph_service.get_user_graph(user_id)
        
        # 转换为响应格式 - 传递所有属性
        nodes = [
            Entity(
                id=n.get("id", ""),
                name=n.get("name", ""),
                type=n.get("type", "entity"),
                mention_count=n.get("mention_count", 1),
                first_mentioned_at=n.get("first_mentioned_at"),
                last_mentioned_at=n.get("last_mentioned_at")
            )
            for n in graph_data.get("nodes", [])
        ]
        
        edges = [
            Edge(
                id=e.get("id", ""),
                source_id=e.get("source_id", ""),
                target_id=e.get("target_id", ""),
                relation_type=e.get("relation_type", "RELATES_TO"),
                weight=e.get("weight", 1.0),
                current_weight=e.get("current_weight"),  # 传递衰减后的权重
                decay_rate=e.get("decay_rate", 0.03),
                created_at=e.get("created_at"),
                updated_at=e.get("updated_at")
            )
            for e in graph_data.get("edges", [])
        ]
        
        return GraphData(nodes=nodes, edges=edges)
    except Exception as e:
        # 如果 Neo4j 不可用，返回空图谱
        import logging
        logging.error(f"Failed to get graph: {e}")
        return GraphData(nodes=[], edges=[])


@router.get("/entity/{entity_id}")
async def get_entity(
    entity_id: str,
    current_user: dict = Depends(get_current_user)
):
    """获取实体详情"""
    # TODO: 从 Neo4j 获取实体
    return {"entity_id": entity_id, "status": "not_found"}


@router.get("/entity/{entity_id}/neighbors")
async def get_neighbors(
    entity_id: str,
    max_depth: int = Query(1, le=3),
    current_user: dict = Depends(get_current_user)
):
    """获取实体的邻居节点"""
    # TODO: 从 Neo4j 获取邻居
    return {"entity_id": entity_id, "neighbors": [], "depth": max_depth}


@router.get("/timeline", response_model=List[GraphSnapshot])
async def get_graph_timeline(
    days: int = Query(30, le=365),
    interval: str = Query("day", regex="^(day|week|month)$"),
    current_user: dict = Depends(get_current_user)
):
    """
    获取图谱时间轴数据
    
    用于前端图谱演化可视化
    """
    user_id = current_user["user_id"]
    
    # TODO: 生成时间轴快照
    return []


@router.get("/export")
async def export_graph(
    format: str = Query("json", regex="^(json|cypher)$"),
    current_user: dict = Depends(get_current_user)
):
    """
    导出图谱数据
    
    支持 JSON 和 Cypher 格式
    """
    user_id = current_user["user_id"]
    
    # TODO: 实现导出
    return {
        "format": format,
        "data": None,
        "message": "Export not implemented"
    }


@router.get("/stats")
async def get_graph_stats(current_user: dict = Depends(get_current_user)):
    """获取图谱统计信息"""
    user_id = current_user["user_id"]
    
    return {
        "user_id": user_id,
        "total_nodes": 0,
        "total_edges": 0,
        "node_types": {
            "person": 0,
            "place": 0,
            "preference": 0,
            "event": 0
        },
        "avg_edge_weight": 0.0
    }
