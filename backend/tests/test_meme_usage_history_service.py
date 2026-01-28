"""
简单测试：验证MemeUsageHistoryService基本功能

这是一个快速验证脚本，用于测试服务的核心功能。
"""
import asyncio
import sys
from uuid import uuid4
from datetime import datetime, timedelta

# 添加backend到路径
sys.path.insert(0, '/workspaces/affinity/backend')

from app.core.database import AsyncSessionLocal
from app.services.meme_usage_history_service import MemeUsageHistoryService
from app.services.content_pool_manager_service import ContentPoolManagerService
from app.models.user import User
from app.models.session import Session


async def test_meme_usage_history_service():
    """测试MemeUsageHistoryService的基本功能"""
    
    async with AsyncSessionLocal() as db:
        try:
            print("=" * 60)
            print("测试 MemeUsageHistoryService")
            print("=" * 60)
            
            # 初始化服务
            usage_service = MemeUsageHistoryService(db)
            pool_service = ContentPoolManagerService(db)
            
            # 1. 创建测试数据：用户、会话、表情包
            print("\n1. 创建测试数据...")
            
            # 创建测试用户（如果不存在）
            from sqlalchemy import select
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            
            if not user:
                user = User(
                    id=uuid4(),
                    username=f"test_user_{uuid4().hex[:8]}",
                    email=f"test_{uuid4().hex[:8]}@example.com",
                    hashed_password="test_hash"
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)
            
            print(f"   ✓ 用户: {user.id}")
            
            # 创建测试会话
            session = Session(
                id=uuid4(),
                user_id=user.id
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            print(f"   ✓ 会话: {session.id}")
            
            # 创建测试表情包
            meme = await pool_service.create_meme_candidate(
                text_description="测试表情包 😊",
                source_platform="weibo",
                content_hash=f"test_hash_{uuid4().hex}"
            )
            print(f"   ✓ 表情包: {meme.id}")
            
            # 2. 测试记录使用
            print("\n2. 测试记录使用...")
            usage = await usage_service.record_usage(
                user_id=user.id,
                meme_id=meme.id,
                conversation_id=session.id
            )
            print(f"   ✓ 使用记录ID: {usage.id}")
            print(f"   ✓ 使用时间: {usage.used_at}")
            print(f"   ✓ 初始反应: {usage.user_reaction}")
            
            # 3. 测试记录反馈
            print("\n3. 测试记录反馈...")
            success = await usage_service.record_feedback(
                usage_id=usage.id,
                reaction="liked"
            )
            print(f"   ✓ 反馈记录成功: {success}")
            
            # 验证反馈已更新
            updated_usage = await usage_service.get_usage_by_id(usage.id)
            print(f"   ✓ 更新后反应: {updated_usage.user_reaction}")
            
            # 4. 测试获取最近使用
            print("\n4. 测试获取最近使用...")
            recent_usage = await usage_service.get_recent_usage(
                user_id=user.id,
                hours=24
            )
            print(f"   ✓ 最近24小时使用次数: {len(recent_usage)}")
            
            # 5. 测试计算接受率
            print("\n5. 测试计算接受率...")
            
            # 创建更多测试数据
            for i in range(3):
                meme2 = await pool_service.create_meme_candidate(
                    text_description=f"测试表情包 {i}",
                    source_platform="weibo",
                    content_hash=f"test_hash_{uuid4().hex}"
                )
                usage2 = await usage_service.record_usage(
                    user_id=user.id,
                    meme_id=meme2.id,
                    conversation_id=session.id
                )
                # 不同的反应
                reactions = ["liked", "ignored", "disliked"]
                await usage_service.record_feedback(usage2.id, reactions[i])
            
            acceptance_rate = await usage_service.calculate_acceptance_rate()
            print(f"   ✓ 接受率: {acceptance_rate:.2%}")
            
            # 6. 测试用户反应统计
            print("\n6. 测试用户反应统计...")
            stats = await usage_service.get_user_reaction_stats(user_id=user.id)
            print(f"   ✓ 总反应数: {stats['total']}")
            print(f"   ✓ 喜欢: {stats['liked']} ({stats['liked_percentage']}%)")
            print(f"   ✓ 忽略: {stats['ignored']} ({stats['ignored_percentage']}%)")
            print(f"   ✓ 不喜欢: {stats['disliked']} ({stats['disliked_percentage']}%)")
            
            # 7. 测试表情包使用次数
            print("\n7. 测试表情包使用次数...")
            usage_count = await usage_service.get_meme_usage_count(meme.id)
            print(f"   ✓ 表情包 {meme.id} 使用次数: {usage_count}")
            
            print("\n" + "=" * 60)
            print("✅ 所有测试通过！")
            print("=" * 60)
            
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    asyncio.run(test_meme_usage_history_service())
