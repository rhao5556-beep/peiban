"""
测试表情包前端集成

验证：
1. 获取表情包偏好设置
2. 更新表情包偏好设置
3. 提交表情包反馈
"""
import asyncio
import sys
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.models.user_meme_preference import UserMemePreference
from app.models.meme import Meme
from app.services.meme_usage_history_service import MemeUsageHistoryService


async def test_meme_preferences():
    """测试表情包偏好设置"""
    print("\n" + "="*60)
    print("测试 1: 表情包偏好设置")
    print("="*60)
    
    async with AsyncSessionLocal() as db:
        # 1. 创建测试用户
        test_user = User(id=uuid4())
        db.add(test_user)
        await db.commit()
        await db.refresh(test_user)
        print(f"✓ 创建测试用户: {test_user.id}")
        
        # 2. 创建默认偏好
        preference = UserMemePreference(
            user_id=test_user.id,
            meme_enabled=True
        )
        db.add(preference)
        await db.commit()
        await db.refresh(preference)
        print(f"✓ 创建默认偏好: meme_enabled={preference.meme_enabled}")
        
        # 3. 更新偏好
        preference.meme_enabled = False
        await db.commit()
        await db.refresh(preference)
        print(f"✓ 更新偏好: meme_enabled={preference.meme_enabled}")
        
        # 4. 查询偏好
        result = await db.execute(
            select(UserMemePreference).where(
                UserMemePreference.user_id == test_user.id
            )
        )
        fetched_pref = result.scalar_one_or_none()
        assert fetched_pref is not None
        assert fetched_pref.meme_enabled == False
        print(f"✓ 查询偏好成功: meme_enabled={fetched_pref.meme_enabled}")
        
        print("\n✅ 表情包偏好设置测试通过")
        return test_user.id


async def test_meme_feedback(user_id):
    """测试表情包反馈"""
    print("\n" + "="*60)
    print("测试 2: 表情包反馈")
    print("="*60)
    
    async with AsyncSessionLocal() as db:
        # 1. 创建测试表情包
        import hashlib
        content = "测试表情包 yyds"
        content_hash = hashlib.md5(content.encode()).hexdigest()
        
        test_meme = Meme(
            id=uuid4(),
            text_description=content,
            source_platform="weibo",
            content_hash=content_hash,
            status="approved",
            safety_status="approved",
            trend_level="hot",
            trend_score=85.5
        )
        db.add(test_meme)
        await db.commit()
        await db.refresh(test_meme)
        print(f"✓ 创建测试表情包: {test_meme.text_description}")
        
        # 2. 初始化服务
        usage_service = MemeUsageHistoryService(db)
        
        # 3. 记录使用
        conversation_id = uuid4()
        usage_id = await usage_service.record_usage(
            user_id=user_id,
            meme_id=test_meme.id,
            conversation_id=conversation_id
        )
        print(f"✓ 记录使用: usage_id={usage_id}")
        
        # 4. 提交反馈
        success = await usage_service.record_feedback(
            usage_id=usage_id,
            reaction="liked"
        )
        assert success
        print(f"✓ 提交反馈成功: reaction=liked")
        
        # 5. 验证反馈
        history = await usage_service.get_user_history(
            user_id=user_id,
            limit=1
        )
        assert len(history) == 1
        assert history[0].user_reaction == "liked"
        print(f"✓ 验证反馈: user_reaction={history[0].user_reaction}")
        
        print("\n✅ 表情包反馈测试通过")


async def test_meme_display_in_conversation():
    """测试对话中的表情包显示"""
    print("\n" + "="*60)
    print("测试 3: 对话中的表情包显示")
    print("="*60)
    
    async with AsyncSessionLocal() as db:
        # 1. 查询热门表情包
        result = await db.execute(
            select(Meme).where(
                Meme.status == "approved",
                Meme.safety_status == "approved",
                Meme.trend_level.in_(["hot", "peak"])
            ).limit(5)
        )
        memes = result.scalars().all()
        
        if memes:
            print(f"✓ 找到 {len(memes)} 个热门表情包:")
            for meme in memes:
                print(f"  - {meme.text_description} (trend_score={meme.trend_score})")
        else:
            print("⚠️  没有找到热门表情包，需要运行聚合任务")
            print("   运行命令: docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.meme_aggregation.aggregate_trending_memes")
        
        print("\n✅ 表情包显示测试完成")


async def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("表情包前端集成测试")
    print("="*60)
    
    try:
        # 测试 1: 偏好设置
        user_id = await test_meme_preferences()
        
        # 测试 2: 反馈
        await test_meme_feedback(user_id)
        
        # 测试 3: 显示
        await test_meme_display_in_conversation()
        
        print("\n" + "="*60)
        print("✅ 所有测试通过！")
        print("="*60)
        print("\n前端集成验证步骤:")
        print("1. 启动前端: cd frontend && npm run dev")
        print("2. 打开浏览器: http://localhost:5173")
        print("3. 进入内容推荐页面，查看表情包设置")
        print("4. 在对话中发送消息，观察是否有表情包显示")
        print("5. 点击表情包的反馈按钮（喜欢/不喜欢/忽略）")
        print("\n")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
