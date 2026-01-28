"""
综合系统集成测试

测试以下系统：
1. 冲突解决系统
2. 内容推荐系统
3. 主动消息系统
4. 表情包系统
"""
import asyncio
import sys
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.models.memory import Memory
from app.models.session import Session
from app.models.user_meme_preference import UserMemePreference
from app.models.outbox import ProactiveMessage, UserProactivePreference
from app.services.conflict_detector_service import ConflictDetector
from app.services.conflict_resolution_service import ConflictResolutionService
from app.services.content_recommendation_service import ContentRecommendationService
from app.services.proactive_service import ProactiveService


def print_section(title: str):
    """打印测试章节标题"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def print_test(name: str):
    """打印测试名称"""
    print(f"\n📋 测试: {name}")


def print_success(message: str):
    """打印成功消息"""
    print(f"  ✅ {message}")


def print_error(message: str):
    """打印错误消息"""
    print(f"  ❌ {message}")


def print_info(message: str):
    """打印信息"""
    print(f"  ℹ️  {message}")


async def test_conflict_resolution_system():
    """测试冲突解决系统"""
    print_section("1. 冲突解决系统测试")
    
    async with AsyncSessionLocal() as db:
        # 创建测试用户
        user = User(id=uuid4())
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print_success(f"创建测试用户: {user.id}")
        
        # 测试 1: 冲突检测服务初始化
        print_test("冲突检测服务初始化")
        
        try:
            detector = ConflictDetector(db)
            print_success("冲突检测服务初始化成功")
        except Exception as e:
            print_error(f"服务初始化失败: {e}")
            return False
        
        # 测试 2: 冲突解决服务初始化
        print_test("冲突解决服务初始化")
        
        try:
            resolver = ConflictResolutionService(db)
            print_success("冲突解决服务初始化成功")
        except Exception as e:
            print_error(f"服务初始化失败: {e}")
            return False
        
        # 测试 3: 检查数据库表
        print_test("检查冲突相关数据库表")
        
        try:
            from app.models.memory import Memory
            result = await db.execute(select(Memory).limit(1))
            print_success("Memory 表可访问")
            
            print_info("冲突检测需要实际的记忆数据和 LLM 调用")
            print_info("服务已就绪，可在实际对话中触发")
        except Exception as e:
            print_error(f"数据库检查失败: {e}")
            return False
        
        return True


async def test_content_recommendation_system():
    """测试内容推荐系统"""
    print_section("2. 内容推荐系统测试")
    
    async with AsyncSessionLocal() as db:
        # 创建测试用户
        user = User(id=uuid4())
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print_success(f"创建测试用户: {user.id}")
        
        # 测试 1: 内容推荐服务初始化
        print_test("内容推荐服务初始化")
        
        try:
            service = ContentRecommendationService(db)
            print_success("内容推荐服务初始化成功")
        except Exception as e:
            print_error(f"服务初始化失败: {e}")
            return False
        
        # 测试 2: 获取推荐（可能为空）
        print_test("获取今日推荐")
        
        try:
            recommendations = await service.get_today_recommendations(user.id)
            if recommendations:
                print_success(f"获取到 {len(recommendations)} 条推荐")
                for rec in recommendations[:3]:  # 只显示前3条
                    print_info(f"  - {rec.get('title', 'N/A')}")
            else:
                print_info("暂无推荐内容（需要运行聚合任务）")
                print_info("运行: docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.content_aggregation.aggregate_content")
        except Exception as e:
            print_error(f"获取推荐失败: {e}")
            return False
        
        # 测试 3: 用户偏好设置
        print_test("用户偏好设置")
        
        try:
            # 获取偏好
            prefs = await service.get_user_preference(user.id)
            print_success(f"获取用户偏好: enabled={prefs.get('enabled', False)}")
            
            # 更新偏好
            await service.update_user_preference(
                user_id=user.id,
                enabled=True,
                daily_limit=3
            )
            print_success("更新用户偏好成功")
        except Exception as e:
            print_error(f"偏好设置失败: {e}")
            return False
        
        return True


async def test_proactive_message_system():
    """测试主动消息系统"""
    print_section("3. 主动消息系统测试")
    
    async with AsyncSessionLocal() as db:
        # 创建测试用户
        user = User(id=uuid4())
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print_success(f"创建测试用户: {user.id}")
        
        # 测试 1: 创建主动消息
        print_test("创建主动消息")
        
        message = ProactiveMessage(
            id=uuid4(),
            user_id=user.id,
            trigger_type="test",
            content="这是一条测试主动消息",
            status="pending"
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        print_success(f"创建主动消息: {message.id}")
        
        # 测试 2: 查询待发送消息
        print_test("查询待发送消息")
        
        result = await db.execute(
            select(ProactiveMessage).where(
                ProactiveMessage.user_id == user.id,
                ProactiveMessage.status == "pending"
            )
        )
        messages = result.scalars().all()
        print_success(f"找到 {len(messages)} 条待发送消息")
        
        # 测试 3: 用户偏好设置
        print_test("用户偏好设置")
        
        preference = UserProactivePreference(
            id=uuid4(),
            user_id=user.id,
            proactive_enabled="true",
            morning_greeting_enabled="true",
            max_messages_per_day=3
        )
        db.add(preference)
        await db.commit()
        print_success("创建用户偏好设置")
        
        # 测试 4: 主动消息服务
        print_test("主动消息服务")
        
        try:
            service = ProactiveService(db)
            print_success("主动消息服务初始化成功")
            
            # 获取用户偏好
            prefs = await service.get_user_preferences(user.id)
            print_success(f"获取用户偏好: proactive_enabled={prefs.get('proactive_enabled', 'false')}")
        except Exception as e:
            print_error(f"服务测试失败: {e}")
            return False
        
        return True


async def test_meme_system():
    """测试表情包系统"""
    print_section("4. 表情包系统测试")
    
    async with AsyncSessionLocal() as db:
        # 创建测试用户
        user = User(id=uuid4())
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print_success(f"创建测试用户: {user.id}")
        
        # 测试 1: 用户偏好设置
        print_test("用户偏好设置")
        
        preference = UserMemePreference(
            user_id=user.id,
            meme_enabled=True
        )
        db.add(preference)
        await db.commit()
        await db.refresh(preference)
        print_success(f"创建表情包偏好: meme_enabled={preference.meme_enabled}")
        
        # 测试 2: 查询偏好
        print_test("查询用户偏好")
        
        result = await db.execute(
            select(UserMemePreference).where(
                UserMemePreference.user_id == user.id
            )
        )
        pref = result.scalar_one_or_none()
        if pref:
            print_success(f"查询成功: meme_enabled={pref.meme_enabled}")
        else:
            print_error("查询失败")
            return False
        
        # 测试 3: 更新偏好
        print_test("更新用户偏好")
        
        pref.meme_enabled = False
        await db.commit()
        await db.refresh(pref)
        print_success(f"更新成功: meme_enabled={pref.meme_enabled}")
        
        # 测试 4: 表情包数据检查
        print_test("检查表情包数据")
        
        from app.models.meme import Meme
        result = await db.execute(
            select(Meme).where(
                Meme.status == "approved",
                Meme.safety_status == "approved"
            ).limit(5)
        )
        memes = result.scalars().all()
        
        if memes:
            print_success(f"找到 {len(memes)} 个已批准的表情包")
            for meme in memes[:3]:
                print_info(f"  - {meme.text_description}")
        else:
            print_info("暂无表情包数据（需要运行聚合任务）")
            print_info("运行: docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.meme_aggregation.aggregate_trending_memes")
        
        return True


async def main():
    """运行所有测试"""
    print("\n" + "="*70)
    print("  🚀 综合系统集成测试")
    print("="*70)
    print(f"\n开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    try:
        # 测试 1: 冲突解决系统
        results['conflict_resolution'] = await test_conflict_resolution_system()
        
        # 测试 2: 内容推荐系统
        results['content_recommendation'] = await test_content_recommendation_system()
        
        # 测试 3: 主动消息系统
        results['proactive_message'] = await test_proactive_message_system()
        
        # 测试 4: 表情包系统
        results['meme'] = await test_meme_system()
        
    except Exception as e:
        print_error(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 打印测试总结
    print_section("测试总结")
    
    print("\n系统状态:")
    print(f"  {'系统名称':<30} {'状态':<10}")
    print("  " + "-"*40)
    
    systems = {
        'conflict_resolution': '冲突解决系统',
        'content_recommendation': '内容推荐系统',
        'proactive_message': '主动消息系统',
        'meme': '表情包系统'
    }
    
    all_passed = True
    for key, name in systems.items():
        status = "✅ 通过" if results.get(key, False) else "❌ 失败"
        print(f"  {name:<30} {status:<10}")
        if not results.get(key, False):
            all_passed = False
    
    print("\n" + "="*70)
    if all_passed:
        print("  🎉 所有系统测试通过！")
    else:
        print("  ⚠️  部分系统测试失败，请检查日志")
    print("="*70)
    
    print(f"\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 打印后续步骤
    print("\n📝 后续步骤:")
    print("  1. 启动后端服务: docker-compose up -d")
    print("  2. 运行内容聚合任务:")
    print("     docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.content_aggregation.aggregate_content")
    print("  3. 运行表情包聚合任务:")
    print("     docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.meme_aggregation.aggregate_trending_memes")
    print("  4. 启动前端: cd frontend && npm run dev")
    print("  5. 访问: http://localhost:5173")
    print()
    
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
