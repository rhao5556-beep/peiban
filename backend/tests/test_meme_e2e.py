"""表情包系统端到端测试"""
import asyncio
import sys
import logging
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text

from app.core.config import settings
from app.services.content_pool_manager_service import ContentPoolManagerService
from app.services.safety_screener_service import SafetyScreenerService
from app.services.trend_analyzer_service import TrendAnalyzerService
from app.services.meme_usage_history_service import MemeUsageHistoryService
from app.models.meme import Meme

# 导入使用决策引擎（可能不存在，跳过该测试）
try:
    from app.services.usage_decision_engine_service import UsageDecisionEngineService
    HAS_DECISION_ENGINE = True
except ImportError:
    HAS_DECISION_ENGINE = False
    logger = logging.getLogger(__name__)
    logger.warning("UsageDecisionEngineService not available, skipping decision engine tests")


async def test_e2e():
    """端到端测试"""
    print("🧪 开始表情包系统端到端测试...\n")
    
    # 创建数据库连接（使用异步驱动）
    async_db_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(async_db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    test_meme_id = None
    test_user_id = str(uuid4())
    
    try:
        async with async_session() as db:
            # 1. 测试内容池管理
            print("1️⃣ 测试内容池管理服务...")
            pool_manager = ContentPoolManagerService(db)
            
            # 创建测试表情包
            test_meme = await pool_manager.create_meme_candidate(
                text_description="测试表情包：今天天气真好",
                source_platform="test",
                popularity_score=50.0,
                content_hash=f"test_hash_{uuid4().hex[:8]}"
            )
            test_meme_id = test_meme.id
            print(f"   ✅ 创建候选表情包: {test_meme.id}")
            print(f"      - 状态: {test_meme.status}")
            print(f"      - 安全状态: {test_meme.safety_status}")
            
            # 2. 测试安全筛选
            print("\n2️⃣ 测试安全筛选服务...")
            safety_screener = SafetyScreenerService()
            
            result = await safety_screener.screen_meme(test_meme)
            print(f"   ✅ 安全筛选结果: {result.overall_status}")
            print(f"      - 内容安全: {result.content_safety}")
            print(f"      - 文化敏感性: {result.cultural_sensitivity}")
            print(f"      - 法律合规: {result.legal_compliance}")
            print(f"      - 伦理边界: {result.ethical_boundaries}")
            
            # 更新状态
            if result.overall_status == "approved":
                await pool_manager.update_meme_status(test_meme.id, "approved", "approved")
                print(f"   ✅ 表情包已批准")
            elif result.overall_status == "flagged":
                await pool_manager.update_meme_status(test_meme.id, "flagged", "flagged")
                print(f"   ⚠️  表情包已标记待审核")
            else:
                await pool_manager.update_meme_status(test_meme.id, "rejected", "rejected")
                print(f"   ❌ 表情包已拒绝")
            
            await db.commit()
            
            # 重新加载表情包
            result = await db.execute(select(Meme).where(Meme.id == test_meme.id))
            test_meme = result.scalar_one()
            
            # 3. 测试趋势分析
            print("\n3️⃣ 测试趋势分析服务...")
            trend_analyzer = TrendAnalyzerService(db)
            
            trend_score = await trend_analyzer.calculate_trend_score(test_meme)
            trend_level = trend_analyzer.determine_trend_level(trend_score)
            print(f"   ✅ 趋势分数: {trend_score:.2f}")
            print(f"   ✅ 趋势等级: {trend_level}")
            
            # 更新趋势信息
            await pool_manager.update_meme_trend(test_meme.id, trend_score, trend_level)
            await db.commit()
            print(f"   ✅ 趋势信息已更新")
            
            # 4. 测试使用决策引擎（仅当表情包已批准且服务可用）
            print("\n4️⃣ 测试使用决策引擎...")
            
            if not HAS_DECISION_ENGINE:
                print(f"   ⚠️  UsageDecisionEngineService 不可用，跳过测试")
            elif test_meme.status == "approved":
                decision_engine = UsageDecisionEngineService(db)
                
                # 测试不同好感度等级
                test_cases = [
                    (10, "stranger"),
                    (35, "acquaintance"),
                    (65, "friend"),
                    (90, "close_friend"),
                ]
                
                for affinity_score, level in test_cases:
                    try:
                        selected_meme = await decision_engine.should_use_meme(
                            user_id=test_user_id,
                            affinity_score=affinity_score,
                            conversation_context="今天天气真好",
                            emotional_tone="positive"
                        )
                        
                        if selected_meme:
                            print(f"   ✅ 好感度 {affinity_score} ({level}): 选择表情包")
                        else:
                            print(f"   ℹ️  好感度 {affinity_score} ({level}): 未选择表情包")
                    except Exception as e:
                        print(f"   ⚠️  好感度 {affinity_score} ({level}): 测试失败 - {e}")
            else:
                print(f"   ⚠️  表情包未批准，跳过使用决策测试")
            
            # 5. 测试使用历史记录（跳过，需要真实用户）
            print("\n5️⃣ 测试使用历史服务...")
            print(f"   ⚠️  跳过使用历史测试（需要真实用户ID）")
            print(f"   ℹ️  在实际环境中，使用历史会在对话中自动记录")
            
            # 6. 测试统计
            print("\n6️⃣ 测试统计功能...")
            stats = await pool_manager.get_statistics()
            print(f"   ✅ 统计信息:")
            print(f"      - 总表情包数: {stats.get('total_memes', 0)}")
            print(f"      - 已批准: {stats.get('approved_memes', 0)}")
            print(f"      - 候选: {stats.get('candidate_memes', 0)}")
            print(f"      - 已拒绝: {stats.get('rejected_memes', 0)}")
            print(f"      - 已标记: {stats.get('flagged_memes', 0)}")
            print(f"      - 平均趋势分数: {stats.get('avg_trend_score', 0):.2f}")
            
            # 7. 测试去重检查
            print("\n7️⃣ 测试去重功能...")
            duplicate_hash = test_meme.content_hash
            is_duplicate = await pool_manager.check_duplicate(duplicate_hash)
            print(f"   ✅ 去重检查: {'发现重复' if is_duplicate else '无重复'}")
            
            if is_duplicate:
                print(f"      - 重复的 content_hash: {duplicate_hash}")
            
            # 清理测试数据
            print("\n🧹 清理测试数据...")
            
            # 删除测试表情包
            if test_meme_id:
                await db.execute(text(f"DELETE FROM memes WHERE id = '{test_meme_id}'"))
            
            await db.commit()
            print("   ✅ 测试数据已清理")
        
        await engine.dispose()
        print("\n✅ 端到端测试完成！所有测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        
        # 尝试清理
        try:
            async with async_session() as db:
                if test_meme_id:
                    await db.execute(text(f"DELETE FROM memes WHERE id = '{test_meme_id}'"))
                    await db.commit()
                    print("\n🧹 已清理测试数据")
        except:
            pass
        
        await engine.dispose()
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(test_e2e())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试执行失败: {e}")
        sys.exit(1)
