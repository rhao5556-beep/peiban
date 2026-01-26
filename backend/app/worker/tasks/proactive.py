"""
主动消息定时任务

由 Celery Beat 调度，定期检查并发送主动消息
"""
import logging
from datetime import datetime
from celery import shared_task
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.proactive_service import ProactiveService, UserPreference
from app.services.affinity_service_v2 import AffinityServiceV2

logger = logging.getLogger(__name__)


@shared_task(name="proactive.check_and_send")
def check_and_send_proactive_messages():
    """
    检查并发送主动消息
    
    调度频率：每小时执行一次
    """
    import asyncio
    asyncio.run(_check_and_send_async())


async def _check_and_send_async():
    """异步执行主动消息检查"""
    logger.info("Starting proactive message check...")
    
    async with AsyncSessionLocal() as db:
        proactive_service = ProactiveService(db)
        affinity_service = AffinityServiceV2(db)
        
        # 获取所有活跃用户
        users = await _get_active_users(db)
        
        sent_count = 0
        for user_id in users:
            try:
                # 获取用户好感度状态
                affinity = await affinity_service.get_affinity(user_id)
                
                # 获取用户偏好
                preference = await proactive_service.get_user_preference(user_id)
                
                # 处理主动消息
                message = await proactive_service.process_user(
                    user_id=user_id,
                    affinity_state=affinity.state,
                    user_preference=preference
                )
                
                if message:
                    sent_count += 1
                    logger.info(f"Sent proactive message to {user_id}: {message.trigger_type}")
                    
            except Exception as e:
                logger.error(f"Failed to process user {user_id}: {e}")
                continue
        
        logger.info(f"Proactive message check completed. Sent {sent_count} messages.")


async def _get_active_users(db) -> list:
    """获取活跃用户列表（30天内有互动）"""
    try:
        result = await db.execute(
            text("""
                SELECT DISTINCT user_id FROM affinity_history
                WHERE created_at > NOW() - INTERVAL '30 days'
                  AND trigger_event = 'conversation'
            """)
        )
        return [str(row[0]) for row in result.fetchall()]
    except Exception as e:
        logger.error(f"Failed to get active users: {e}")
        return []


@shared_task(name="proactive.morning_greeting")
def send_morning_greetings():
    """
    发送早安问候
    
    调度时间：每天 8:00
    """
    import asyncio
    asyncio.run(_send_greetings_async("morning"))


@shared_task(name="proactive.evening_greeting")
def send_evening_greetings():
    """
    发送晚安问候
    
    调度时间：每天 22:00
    """
    import asyncio
    asyncio.run(_send_greetings_async("evening"))


async def _send_greetings_async(greeting_type: str):
    """发送问候消息"""
    logger.info(f"Starting {greeting_type} greeting task...")
    
    async with AsyncSessionLocal() as db:
        proactive_service = ProactiveService(db)
        affinity_service = AffinityServiceV2(db)
        
        # 获取启用了问候的用户
        users = await _get_greeting_enabled_users(db, greeting_type)
        
        sent_count = 0
        for user_id in users:
            try:
                affinity = await affinity_service.get_affinity(user_id)
                
                # 生成问候消息
                action = f"{greeting_type}_greeting"
                content = proactive_service.message_generator.generate(
                    action=action,
                    affinity_state=affinity.state
                )
                
                if content:
                    message = await proactive_service.delivery_manager.schedule_message(
                        user_id=user_id,
                        trigger_type="time",
                        content=content,
                        metadata={"greeting_type": greeting_type}
                    )
                    await proactive_service.delivery_manager.send_message(message)
                    sent_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to send {greeting_type} greeting to {user_id}: {e}")
                continue
        
        logger.info(f"{greeting_type.capitalize()} greeting task completed. Sent {sent_count} messages.")


async def _get_greeting_enabled_users(db, greeting_type: str) -> list:
    """获取启用了问候的用户"""
    column = f"{greeting_type}_greeting"
    
    try:
        result = await db.execute(
            text(f"""
                SELECT user_id FROM user_proactive_preferences
                WHERE proactive_enabled = TRUE
                  AND {column} = TRUE
            """)
        )
        return [str(row[0]) for row in result.fetchall()]
    except Exception as e:
        logger.error(f"Failed to get greeting enabled users: {e}")
        return []


@shared_task(name="proactive.check_silence")
def check_silence_users():
    """
    检查沉默用户并发送关怀消息
    
    调度频率：每天执行一次
    """
    import asyncio
    asyncio.run(_check_silence_async())


async def _check_silence_async():
    """检查沉默用户"""
    logger.info("Starting silence check task...")
    
    async with AsyncSessionLocal() as db:
        proactive_service = ProactiveService(db)
        affinity_service = AffinityServiceV2(db)
        
        # 获取3天以上未互动的用户
        users = await _get_silent_users(db, days=3)
        
        sent_count = 0
        for user_id, days_silent in users:
            try:
                affinity = await affinity_service.get_affinity(user_id)
                preference = await proactive_service.get_user_preference(user_id)
                
                if not preference.silence_reminder:
                    continue
                
                # 根据沉默天数选择消息类型
                if days_silent >= 7:
                    action = "care_message"
                else:
                    action = "gentle_checkin"
                
                content = proactive_service.message_generator.generate(
                    action=action,
                    affinity_state=affinity.state
                )
                
                if content:
                    message = await proactive_service.delivery_manager.schedule_message(
                        user_id=user_id,
                        trigger_type="silence",
                        content=content,
                        metadata={"days_silent": days_silent}
                    )
                    await proactive_service.delivery_manager.send_message(message)
                    sent_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to send silence reminder to {user_id}: {e}")
                continue
        
        logger.info(f"Silence check completed. Sent {sent_count} messages.")


async def _get_silent_users(db, days: int) -> list:
    """获取沉默用户列表"""
    try:
        result = await db.execute(
            text("""
                WITH last_interaction AS (
                    SELECT user_id, MAX(created_at) as last_at
                    FROM affinity_history
                    WHERE trigger_event = 'conversation'
                    GROUP BY user_id
                )
                SELECT li.user_id, EXTRACT(DAY FROM NOW() - li.last_at)::int as days_silent
                FROM last_interaction li
                JOIN user_proactive_preferences upp ON li.user_id = upp.user_id
                WHERE li.last_at < NOW() - INTERVAL :days DAY
                  AND upp.proactive_enabled = TRUE
                  AND upp.silence_reminder = TRUE
            """),
            {"days": f"{days} days"}
        )
        return [(str(row[0]), row[1]) for row in result.fetchall()]
    except Exception as e:
        logger.error(f"Failed to get silent users: {e}")
        return []
