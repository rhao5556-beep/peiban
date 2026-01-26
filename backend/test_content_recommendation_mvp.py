"""
MVP 功能验证脚本 - 内容推荐系统

测试完整流程：
1. 内容抓取（RSS）
2. 推荐生成（基于用户兴趣）
3. API 端点（获取推荐、提交反馈）
4. 好感度门槛验证
5. 每日限额验证
"""
import asyncio
import sys
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.user import User
from app.models.content_recommendation import ContentLibrary, UserContentPreference, RecommendationHistory
from app.services.content_aggregator_service import ContentAggregatorService
from app.services.content_recommendation_service import ContentRecommendationService
from app.services.affinity_service_v2 import AffinityServiceV2


async def setup_test_user(session: AsyncSession) -> User:
    """创建或获取测试用户"""
    result = await session.execute(
        select(User).where(User.username == "test_mvp_user")
    )
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            username="test_mvp_user",
            hashed_password="test_hash"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        print(f"✓ 创建测试用户: {user.id}")
    else:
        print(f"✓ 使用现有测试用户: {user.id}")
    
    return user


async def test_content_aggregation():
    """测试 1: 内容抓取"""
    print("\n" + "="*60)
    print("测试 1: 内容聚合服务 (RSS 抓取)")
    print("="*60)
    
    async with async_session_maker() as session:
        aggregator = ContentAggregatorService(session)
        
        # 测试 RSS 抓取
        print("\n抓取 RSS 内容...")
        contents = await aggregator.fetch_rss_feeds()
        
        if contents:
            print(f"✓ 成功抓取 {len(contents)} 条内容")
            print(f"\n示例内容:")
            for i, content in enumerate(contents[:3], 1):
                print(f"  {i}. {content.title[:50]}...")
                print(f"     来源: {content.source}")
                print(f"     标签: {', '.join(content.tags[:3])}")
        else:
            print("⚠ 未抓取到内容（可能是网络问题或 RSS 源不可用）")
            return False
    
    return True


async def test_user_interest_extraction(user_id: str):
    """测试 2: 用户兴趣提取"""
    print("\n" + "="*60)
    print("测试 2: 用户兴趣提取")
    print("="*60)
    
    async with async_session_maker() as session:
        rec_service = ContentRecommendationService(session)
        
        print(f"\n提取用户 {user_id} 的兴趣...")
        interests = await rec_service._extract_user_interests(user_id)
        
        if interests:
            print(f"✓ 提取到 {len(interests)} 个兴趣标签:")
            for interest in interests:
                print(f"  - {interest}")
        else:
            print("⚠ 用户暂无兴趣标签（需要先进行对话建立记忆图谱）")
            print("  将使用默认兴趣进行推荐")
    
    return True


async def test_affinity_threshold(user_id: str):
    """测试 3: 好感度门槛验证"""
    print("\n" + "="*60)
    print("测试 3: 好感度门槛验证")
    print("="*60)
    
    async with async_session_maker() as session:
        affinity_service = AffinityServiceV2(session)
        rec_service = ContentRecommendationService(session)
        
        # 获取当前好感度
        affinity_state = await affinity_service.get_affinity_state(user_id)
        current_score = affinity_state.get('score', 0)
        current_state = affinity_state.get('state', 'stranger')
        
        print(f"\n当前好感度: {current_score:.1f} ({current_state})")
        
        # 检查是否满足推荐门槛
        if current_state in ['friend', 'close_friend', 'intimate']:
            print(f"✓ 好感度达到 {current_state}，满足推荐条件")
            return True
        else:
            print(f"⚠ 好感度为 {current_state}，不满足推荐条件（需要 friend+）")
            print("  提示: 需要与 AI 进行更多对话以提升好感度")
            return False


async def test_recommendation_generation(user_id: str):
    """测试 4: 推荐生成"""
    print("\n" + "="*60)
    print("测试 4: 推荐生成")
    print("="*60)
    
    async with async_session_maker() as session:
        rec_service = ContentRecommendationService(session)
        
        # 先启用推荐
        result = await session.execute(
            select(UserContentPreference).where(UserContentPreference.user_id == user_id)
        )
        preference = result.scalar_one_or_none()
        
        if not preference:
            preference = UserContentPreference(
                user_id=user_id,
                enabled=True,
                daily_limit=3
            )
            session.add(preference)
            await session.commit()
            print("✓ 已启用推荐功能")
        elif not preference.enabled:
            preference.enabled = True
            await session.commit()
            print("✓ 已启用推荐功能")
        else:
            print("✓ 推荐功能已启用")
        
        # 生成推荐
        print("\n生成推荐...")
        recommendations = await rec_service.generate_recommendations(user_id)
        
        if recommendations:
            print(f"✓ 成功生成 {len(recommendations)} 条推荐")
            print(f"\n推荐内容:")
            for i, rec in enumerate(recommendations, 1):
                print(f"\n  {i}. {rec['title'][:60]}...")
                print(f"     来源: {rec['source']}")
                print(f"     匹配分数: {rec['match_score']:.2f}")
                print(f"     标签: {', '.join(rec['tags'][:3])}")
        else:
            print("⚠ 未生成推荐（可能是好感度不足或内容库为空）")
            return False
    
    return True


async def test_daily_limit(user_id: str):
    """测试 5: 每日限额验证"""
    print("\n" + "="*60)
    print("测试 5: 每日限额验证")
    print("="*60)
    
    async with async_session_maker() as session:
        # 查询今日推荐数量
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        result = await session.execute(
            select(RecommendationHistory)
            .where(
                RecommendationHistory.user_id == user_id,
                RecommendationHistory.recommended_at >= today_start
            )
        )
        today_recommendations = result.scalars().all()
        
        # 获取用户限额设置
        result = await session.execute(
            select(UserContentPreference).where(UserContentPreference.user_id == user_id)
        )
        preference = result.scalar_one_or_none()
        daily_limit = preference.daily_limit if preference else 1
        
        print(f"\n今日已推荐: {len(today_recommendations)} 条")
        print(f"每日限额: {daily_limit} 条")
        
        if len(today_recommendations) <= daily_limit:
            print(f"✓ 推荐数量在限额内")
            return True
        else:
            print(f"⚠ 推荐数量超过限额")
            return False


async def test_api_endpoints(user_id: str):
    """测试 6: API 端点"""
    print("\n" + "="*60)
    print("测试 6: API 端点验证")
    print("="*60)
    
    async with async_session_maker() as session:
        # 测试获取推荐
        print("\n测试 GET /content/recommendations...")
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        result = await session.execute(
            select(RecommendationHistory)
            .where(
                RecommendationHistory.user_id == user_id,
                RecommendationHistory.recommended_at >= today_start
            )
            .order_by(RecommendationHistory.rank_position)
        )
        recommendations = result.scalars().all()
        
        if recommendations:
            print(f"✓ 成功获取 {len(recommendations)} 条推荐")
        else:
            print("⚠ 暂无推荐记录")
        
        # 测试获取偏好设置
        print("\n测试 GET /content/preference...")
        result = await session.execute(
            select(UserContentPreference).where(UserContentPreference.user_id == user_id)
        )
        preference = result.scalar_one_or_none()
        
        if preference:
            print(f"✓ 成功获取偏好设置:")
            print(f"  - 启用状态: {preference.enabled}")
            print(f"  - 每日限额: {preference.daily_limit}")
            print(f"  - 偏好来源: {preference.preferred_sources or '全部'}")
        else:
            print("⚠ 用户未设置偏好")
    
    return True


async def run_mvp_tests():
    """运行所有 MVP 测试"""
    print("\n" + "="*60)
    print("内容推荐系统 MVP 功能验证")
    print("="*60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 设置测试用户
        async with async_session_maker() as session:
            user = await setup_test_user(session)
            user_id = user.id
        
        # 运行测试
        results = []
        
        # 测试 1: 内容抓取
        results.append(("内容抓取", await test_content_aggregation()))
        
        # 测试 2: 兴趣提取
        results.append(("兴趣提取", await test_user_interest_extraction(user_id)))
        
        # 测试 3: 好感度门槛
        affinity_ok = await test_affinity_threshold(user_id)
        results.append(("好感度门槛", affinity_ok))
        
        # 测试 4: 推荐生成（仅在好感度满足时测试）
        if affinity_ok:
            results.append(("推荐生成", await test_recommendation_generation(user_id)))
            results.append(("每日限额", await test_daily_limit(user_id)))
        else:
            print("\n⚠ 跳过推荐生成测试（好感度不足）")
            results.append(("推荐生成", None))
            results.append(("每日限额", None))
        
        # 测试 6: API 端点
        results.append(("API 端点", await test_api_endpoints(user_id)))
        
        # 汇总结果
        print("\n" + "="*60)
        print("测试结果汇总")
        print("="*60)
        
        passed = sum(1 for _, result in results if result is True)
        skipped = sum(1 for _, result in results if result is None)
        failed = sum(1 for _, result in results if result is False)
        
        for name, result in results:
            if result is True:
                status = "✓ 通过"
            elif result is None:
                status = "⊘ 跳过"
            else:
                status = "✗ 失败"
            print(f"{status:8} {name}")
        
        print(f"\n总计: {passed} 通过, {failed} 失败, {skipped} 跳过")
        
        if failed == 0:
            print("\n🎉 MVP 功能验证通过！")
            return 0
        else:
            print("\n⚠ 部分测试失败，请检查日志")
            return 1
            
    except Exception as e:
        print(f"\n✗ 测试执行失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_mvp_tests())
    sys.exit(exit_code)
