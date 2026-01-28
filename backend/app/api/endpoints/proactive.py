"""
主动消息 API 端点
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime, time
import uuid

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

router = APIRouter()

def _parse_hhmm(value: Optional[str]) -> Optional[time]:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid time format: {value}") from e


_ACK_TRANSITIONS = {
    "pending": {"read", "ignore", "disable"},
    "sent": {"read", "ignore", "disable"},
    "delivered": {"read", "ignore", "disable"},
    "read": {"read"},
    "ignored": {"ignore"},
    "cancelled": {"disable"},
}


@router.get("/messages")
async def get_proactive_messages(
    status: Optional[str] = Query(None, description="过滤状态: pending, sent, read"),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户的主动消息列表
    """
    from app.models.outbox import ProactiveMessage
    
    query = select(ProactiveMessage).where(
        ProactiveMessage.user_id == current_user["user_id"]
    )
    
    if status:
        query = query.where(ProactiveMessage.status == status)
    
    query = query.order_by(ProactiveMessage.created_at.desc()).limit(limit)
    
    result = await db.execute(query)
    messages = result.scalars().all()
    
    return {
        "messages": [
            {
                "id": str(msg.id),
                "trigger_type": msg.trigger_type,
                "content": msg.content,
                "status": msg.status,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
                "read_at": msg.read_at.isoformat() if msg.read_at else None,
                "metadata": msg.message_metadata
            }
            for msg in messages
        ],
        "total": len(messages)
    }


@router.post("/messages/{message_id}/ack")
async def acknowledge_message(
    message_id: str,
    action: str = Query(..., description="用户操作: read, ignore, disable"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    确认收到主动消息并记录用户反馈
    """
    from app.models.outbox import ProactiveMessage
    
    try:
        message_uuid = uuid.UUID(message_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid message_id") from e

    # 查询消息
    result = await db.execute(
        select(ProactiveMessage).where(
            ProactiveMessage.id == message_uuid,
            ProactiveMessage.user_id == current_user["user_id"]
        )
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    
    # 更新状态
    now = datetime.utcnow()
    
    if action not in _ACK_TRANSITIONS.get(message.status, set()):
        raise HTTPException(status_code=409, detail="Invalid status transition")

    if action == "read":
        if message.status == "read":
            return {"success": True, "message_id": message_id, "action": action, "status": message.status}
        message.status = "read"
        message.read_at = now
        message.user_response = "replied"
    elif action == "ignore":
        if message.status == "ignored":
            return {"success": True, "message_id": message_id, "action": action, "status": message.status}
        message.status = "ignored"
        message.user_response = "ignored"
    elif action == "disable":
        if message.status == "cancelled":
            return {"success": True, "message_id": message_id, "action": action, "status": message.status}
        message.status = "cancelled"
        message.user_response = "disabled"
        
        # 同时禁用用户的主动消息偏好
        from app.models.outbox import UserProactivePreference
        pref_result = await db.execute(
            select(UserProactivePreference).where(
                UserProactivePreference.user_id == current_user["user_id"]
            )
        )
        preference = pref_result.scalar_one_or_none()
        
        if preference:
            preference.proactive_enabled = False
        else:
            # 创建偏好并禁用
            new_pref = UserProactivePreference(
                user_id=current_user["user_id"],
                proactive_enabled=False
            )
            db.add(new_pref)
    else:
        raise HTTPException(status_code=400, detail="无效的操作")
    
    await db.commit()
    
    return {
        "success": True,
        "message_id": message_id,
        "action": action,
        "status": message.status
    }


@router.get("/preferences")
async def get_proactive_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户的主动消息偏好设置
    """
    from app.models.outbox import UserProactivePreference
    
    result = await db.execute(
        select(UserProactivePreference).where(
            UserProactivePreference.user_id == current_user["user_id"]
        )
    )
    preference = result.scalar_one_or_none()
    
    if not preference:
        # 返回默认值
        return {
            "proactive_enabled": True,
            "morning_greeting_enabled": True,
            "evening_greeting_enabled": True,
            "silence_reminder_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00",
            "max_messages_per_day": 2,
            "preferred_morning_time": "08:00",
            "preferred_evening_time": "22:00",
            "timezone": "Asia/Shanghai"
        }
    
    return {
        "proactive_enabled": bool(preference.proactive_enabled),
        "morning_greeting_enabled": bool(preference.morning_greeting),
        "evening_greeting_enabled": bool(preference.evening_greeting),
        "silence_reminder_enabled": bool(preference.silence_reminder),
        "quiet_hours_start": preference.quiet_hours_start.strftime("%H:%M") if preference.quiet_hours_start else "22:00",
        "quiet_hours_end": preference.quiet_hours_end.strftime("%H:%M") if preference.quiet_hours_end else "08:00",
        "max_messages_per_day": preference.max_daily_messages or 2,
        "preferred_morning_time": "08:00",
        "preferred_evening_time": "22:00",
        "timezone": preference.timezone or "Asia/Shanghai"
    }


@router.put("/preferences")
async def update_proactive_preferences(
    proactive_enabled: Optional[bool] = None,
    morning_greeting_enabled: Optional[bool] = None,
    evening_greeting_enabled: Optional[bool] = None,
    silence_reminder_enabled: Optional[bool] = None,
    quiet_hours_start: Optional[str] = None,
    quiet_hours_end: Optional[str] = None,
    max_messages_per_day: Optional[int] = None,
    preferred_morning_time: Optional[str] = None,
    preferred_evening_time: Optional[str] = None,
    timezone: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新用户的主动消息偏好设置
    """
    from app.models.outbox import UserProactivePreference
    
    result = await db.execute(
        select(UserProactivePreference).where(
            UserProactivePreference.user_id == current_user["user_id"]
        )
    )
    preference = result.scalar_one_or_none()
    
    if not preference:
        # 创建新偏好
        preference = UserProactivePreference(user_id=current_user["user_id"])
        db.add(preference)
    
    # 更新字段
    if proactive_enabled is not None:
        preference.proactive_enabled = proactive_enabled
    if morning_greeting_enabled is not None:
        preference.morning_greeting = morning_greeting_enabled
    if evening_greeting_enabled is not None:
        preference.evening_greeting = evening_greeting_enabled
    if silence_reminder_enabled is not None:
        preference.silence_reminder = silence_reminder_enabled
    if quiet_hours_start is not None:
        preference.quiet_hours_start = _parse_hhmm(quiet_hours_start)
    if quiet_hours_end is not None:
        preference.quiet_hours_end = _parse_hhmm(quiet_hours_end)
    if max_messages_per_day is not None:
        preference.max_daily_messages = max_messages_per_day

    if timezone is not None:
        preference.timezone = timezone
    
    await db.commit()
    await db.refresh(preference)
    
    return {
        "success": True,
        "proactive_enabled": bool(preference.proactive_enabled),
        "morning_greeting_enabled": bool(preference.morning_greeting),
        "evening_greeting_enabled": bool(preference.evening_greeting),
        "silence_reminder_enabled": bool(preference.silence_reminder),
        "quiet_hours_start": preference.quiet_hours_start.strftime("%H:%M") if preference.quiet_hours_start else "22:00",
        "quiet_hours_end": preference.quiet_hours_end.strftime("%H:%M") if preference.quiet_hours_end else "08:00",
        "max_messages_per_day": preference.max_daily_messages or 2,
        "preferred_morning_time": "08:00",
        "preferred_evening_time": "22:00"
    }
