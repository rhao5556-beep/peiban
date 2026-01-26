"""好感度端点"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json

from app.core.security import get_current_user
from app.core.database import get_db
from app.services.affinity_service import AffinityService, AffinitySignals as ServiceSignals

router = APIRouter()


class AffinityState(BaseModel):
    """好感度状态（增量字段，保持向后兼容）"""
    user_id: str
    score: float  # 0~1，兼容现有前端
    score_100: Optional[int] = None  # 新增：0~100 展示用
    state: str  # stranger, acquaintance, friend, close_friend, best_friend
    state_v2: Optional[str] = None  # 新增：V2 4档状态
    status: str = "ready"  # ready, computing, error
    updated_at: Optional[datetime] = None
    
    # V2 健康信息（可选）
    health_state: Optional[str] = None
    loneliness_score: Optional[float] = None
    intervention_level: Optional[int] = None


class AffinityHistory(BaseModel):
    """好感度历史记录（归一化为 0~1）"""
    id: Optional[str] = None
    old_score: float  # 0~1
    new_score: float  # 0~1
    old_score_100: Optional[int] = None  # 新增：0~100 展示用
    new_score_100: Optional[int] = None  # 新增：0~100 展示用
    delta: float
    trigger_event: str
    signals: dict
    created_at: Optional[datetime] = None


class AffinitySignals(BaseModel):
    """好感度信号"""
    user_initiated: bool = False
    emotion_valence: float = 0.0
    memory_confirmation: bool = False
    correction: bool = False
    silence_days: int = 0


class ExplicitFeedbackRequest(BaseModel):
    action: str
    message_id: Optional[str] = None
    memory_id: Optional[str] = None


@router.get("/", response_model=AffinityState)
async def get_affinity(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取当前好感度状态（增量字段，保持向后兼容）"""
    user_id = current_user["user_id"]
    
    try:
        affinity_service = AffinityService(db_session=db)
        result = await affinity_service.get_affinity(user_id)
        
        # 尝试从 V2 获取健康信息
        health_state = None
        loneliness_score = None
        intervention_level = None
        
        try:
            from app.services.affinity_service_v2 import AffinityServiceV2
            affinity_v2 = AffinityServiceV2(db_session=db)
            result_v2 = await affinity_v2.get_affinity(user_id)
            health_state = result_v2.health_state
            loneliness_score = result_v2.loneliness_score
            intervention_level = result_v2.intervention_level
        except Exception:
            pass  # V2 不可用时忽略
        
        return AffinityState(
            user_id=user_id,
            score=result.new_score,  # 0~1，兼容现有
            score_100=int(result.new_score * 100),  # 新增：0~100
            state=result.state,
            state_v2=result.state if result.state != "best_friend" else "close_friend",  # V2 没有 best_friend
            status="ready",
            updated_at=datetime.now(),
            health_state=health_state,
            loneliness_score=loneliness_score,
            intervention_level=intervention_level
        )
    except Exception as e:
        import logging
        logging.error(f"Failed to get affinity: {e}")
        # 返回默认值
        return AffinityState(
            user_id=user_id,
            score=0.5,
            score_100=50,
            state="acquaintance",
            status="computing",
            updated_at=datetime.now()
        )


@router.get("/history", response_model=List[AffinityHistory])
async def get_affinity_history(
    days: int = Query(30, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取好感度变化历史（所有分数归一化为 0~1）"""
    user_id = current_user["user_id"]
    
    try:
        affinity_service = AffinityService(db_session=db)
        history = await affinity_service.get_affinity_history(user_id, days)
        
        return [
            AffinityHistory(
                old_score=h.old_score,  # 已归一化为 0~1
                new_score=h.new_score,  # 已归一化为 0~1
                old_score_100=int(h.old_score * 100),  # 新增：0~100
                new_score_100=int(h.new_score * 100),  # 新增：0~100
                delta=h.delta,
                trigger_event=h.trigger_event,
                signals={
                    "user_initiated": h.signals.user_initiated,
                    "emotion_valence": h.signals.emotion_valence,
                    "memory_confirmation": h.signals.memory_confirmation,
                    "correction": h.signals.correction,
                    "silence_days": h.signals.silence_days
                }
            )
            for h in history
        ]
    except Exception as e:
        import logging
        logging.error(f"Failed to get affinity history: {e}")
        return []


@router.post("/update", response_model=AffinityState)
async def update_affinity(
    signals: AffinitySignals,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新好感度（内部使用）
    
    通常由对话服务自动调用，此端点用于测试
    """
    user_id = current_user["user_id"]
    
    try:
        affinity_service = AffinityService(db_session=db)
        service_signals = ServiceSignals(
            user_initiated=signals.user_initiated,
            emotion_valence=signals.emotion_valence,
            memory_confirmation=signals.memory_confirmation,
            correction=signals.correction,
            silence_days=signals.silence_days
        )
        result = await affinity_service.update_affinity(user_id, service_signals)
        
        return AffinityState(
            user_id=user_id,
            score=result.new_score,
            state=result.state,
            status="ready",
            updated_at=datetime.now()
        )
    except Exception as e:
        import logging
        logging.error(f"Failed to update affinity: {e}")
        return AffinityState(
            user_id=user_id,
            score=0.5,
            state="acquaintance",
            status="error",
            updated_at=datetime.now()
        )


@router.post("/feedback")
async def submit_explicit_feedback(
    request: ExplicitFeedbackRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user_id = current_user["user_id"]

    action = (request.action or "").strip().lower()
    if action not in {"liked", "disliked", "saved", "favorited"}:
        return {"success": False, "message": "Invalid action"}

    try:
        from app.services.affinity_service_v2 import AffinityServiceV2
        affinity_v2 = AffinityServiceV2(db_session=db)
        affinity = await affinity_v2.get_affinity(user_id)
        score = affinity.new_score
    except Exception:
        score = 0.5

    signals = {
        "liked": 1 if action == "liked" else 0,
        "disliked": 1 if action == "disliked" else 0,
        "saved": 1 if action == "saved" else 0,
        "favorited": 1 if action == "favorited" else 0
    }
    if request.message_id:
        signals["message_id"] = request.message_id
    if request.memory_id:
        signals["memory_id"] = request.memory_id

    await db.execute(
        text("""
            INSERT INTO affinity_history (user_id, old_score, new_score, delta, trigger_event, signals)
            VALUES (:user_id, :old_score, :new_score, 0, 'explicit_feedback', :signals::jsonb)
        """),
        {
            "user_id": user_id,
            "old_score": score,
            "new_score": score,
            "signals": json.dumps(signals, ensure_ascii=False)
        }
    )
    await db.commit()

    return {"success": True}


@router.get("/state-mapping")
async def get_state_mapping():
    """获取好感度状态映射规则（更新为 0~1 尺度）"""
    return {
        "storage_scale": "0-1",
        "display_scale": "0-100",
        "legacy_states": {
            "stranger": {"min": 0.0, "max": 0.2, "display_min": 0, "display_max": 20},
            "acquaintance": {"min": 0.2, "max": 0.4, "display_min": 20, "display_max": 40},
            "friend": {"min": 0.4, "max": 0.6, "display_min": 40, "display_max": 60},
            "close_friend": {"min": 0.6, "max": 0.8, "display_min": 60, "display_max": 80},
            "best_friend": {"min": 0.8, "max": 1.0, "display_min": 80, "display_max": 100}
        },
        "v2_states": {
            "stranger": {"min": 0, "max": 20},
            "acquaintance": {"min": 21, "max": 50},
            "friend": {"min": 51, "max": 80},
            "close_friend": {"min": 81, "max": 100}
        }
    }


@router.get("/dashboard")
async def get_dashboard(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户关系仪表盘数据
    
    返回内容：
    - relationship: 关系状态、分数、心形显示
    - days_known: 认识天数
    - memories: 记忆数量
    - top_topics: 最常聊的话题 TOP 3
    - emotion_trend: 最近30天情绪趋势
    - feedback: 反馈统计
    - health_reminder: 健康提醒（仅当孤独指数>30时）
    """
    import logging
    user_id = current_user["user_id"]
    
    try:
        from app.services.affinity_service_v2 import AffinityServiceV2
        affinity_v2 = AffinityServiceV2(db_session=db)
        dashboard = await affinity_v2.get_user_dashboard(user_id)
        return dashboard
    except Exception as e:
        logging.error(f"Failed to get dashboard: {e}")
        # 返回基础数据
        return {
            "relationship": {
                "state": "acquaintance",
                "state_display": "熟人",
                "score": 50,
                "hearts": "❤️🤍🤍"
            },
            "days_known": 0,
            "memories": {"count": 0, "can_view_details": True},
            "top_topics": [],
            "emotion_trend": [],
            "feedback": {"likes": 0, "dislikes": 0, "saves": 0},
            "health_reminder": None
        }
