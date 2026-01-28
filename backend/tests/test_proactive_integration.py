"""
测试主动消息系统集成
"""
import asyncio
import sys
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# 添加项目路径
sys.path.insert(0, '.')

from app.core.config import settings
from app.models.outbox import ProactiveMessage, UserProactivePreference
from app.models.user import User


async def test_proactive_system():
    """测试主动消息系统"""
    
    # 创建异步引擎
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        print("\n" + "="*60)
        print("🧪 测试主动消息系统")
        print("="*60)
        
        # 1. 检查用户
        result = await session.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        
        if not user:
            print("❌ 没有找到用户，请先创建用户")
            return
        
        print(f"\n✅ 找到用户: {user.id}")
        
        # 2. 创建测试主动消息
        test_message = ProactiveMessage(
            user_id=user.id,
            trigger_type="time",
            content="这是一条测试主动消息！AI 正在测试推送功能。",
            status="pending",
            scheduled_at=datetime.utcnow(),
            metadata={"test": True, "source": "integration_test"}
        )
        
        session.add(test_message)
        await session.commit()
        await session.refresh(test_message)
        
        print(f"\n✅ 创建测试消息: {test_message.id}")
        print(f"   内容: {test_message.content}")
        print(f"   状态: {test_message.status}")
        
        # 3. 检查用户偏好
        pref_result = await session.execute(
            select(UserProactivePreference).where(
                UserProactivePreference.user_id == user.id
            )
        )
        preference = pref_result.scalar_one_or_none()
        
        if not preference:
            print("\n⚠️  用户偏好不存在，创建默认偏好")
            preference = UserProactivePreference(
                user_id=user.id,
                proactive_enabled="true",
                morning_greeting_enabled="true",
                evening_greeting_enabled="true",
                silence_reminder_enabled="true"
            )
            session.add(preference)
            await session.commit()
            await session.refresh(preference)
        
        print(f"\n✅ 用户偏好:")
        print(f"   主动消息启用: {preference.proactive_enabled}")
        print(f"   早安问候: {preference.morning_greeting_enabled}")
        print(f"   晚安问候: {preference.evening_greeting_enabled}")
        
        # 4. 查询所有待处理消息
        pending_result = await session.execute(
            select(ProactiveMessage).where(
                ProactiveMessage.user_id == user.id,
                ProactiveMessage.status == "pending"
            ).order_by(ProactiveMessage.created_at.desc())
        )
        pending_messages = pending_result.scalars().all()
        
        print(f"\n✅ 待处理消息数量: {len(pending_messages)}")
        for msg in pending_messages[:3]:  # 只显示前3条
            print(f"   - [{msg.trigger_type}] {msg.content[:50]}...")
        
        print("\n" + "="*60)
        print("✅ 测试完成！")
        print("="*60)
        print("\n📋 下一步:")
        print("1. 启动前端: cd frontend && npm run dev")
        print("2. 访问 http://localhost:5173")
        print("3. 等待 30 秒，查看主动消息弹窗")
        print("4. 或者手动调用 API:")
        print("   GET http://localhost:8000/api/v1/proactive/messages?status=pending")
        print()
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_proactive_system())
