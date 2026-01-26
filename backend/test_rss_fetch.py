"""
测试RSS内容抓取功能

验证：
1. RSS源是否可访问
2. 内容解析是否正确
3. 数据库保存是否成功
"""
import asyncio
import sys
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.services.content_aggregator_service import ContentAggregatorService


async def test_rss_fetch():
    """测试RSS抓取"""
    print("=" * 60)
    print("RSS内容抓取测试")
    print("=" * 60)
    
    async with AsyncSessionLocal() as db:
        service = ContentAggregatorService(db)
        
        try:
            # 步骤1: 抓取RSS内容
            print("\n📡 步骤1: 抓取RSS内容...")
            contents = await service.fetch_rss_feeds()
            
            if not contents:
                print("❌ 未抓取到任何内容")
                return False
            
            print(f"✅ 成功抓取 {len(contents)} 条内容\n")
            
            # 显示前5条内容
            print("📋 内容预览（前5条）:")
            for i, content in enumerate(contents[:5], 1):
                print(f"\n{i}. {content.title}")
                print(f"   来源: {content.source}")
                print(f"   URL: {content.content_url}")
                print(f"   标签: {', '.join(content.tags[:3])}")
                print(f"   质量分: {content.quality_score}")
            
            # 步骤2: 保存到数据库
            print(f"\n💾 步骤2: 保存到数据库...")
            saved_count = await service.save_contents_batch(contents)
            
            print(f"✅ 成功保存 {saved_count}/{len(contents)} 条内容")
            
            # 步骤3: 验证数据库
            print(f"\n🔍 步骤3: 验证数据库...")
            from sqlalchemy import text
            
            result = await db.execute(
                text("""
                    SELECT COUNT(*) as total,
                           COUNT(DISTINCT source) as sources,
                           MAX(published_at) as latest
                    FROM content_library
                    WHERE DATE(published_at) >= CURRENT_DATE - INTERVAL '1 day'
                """)
            )
            
            row = result.fetchone()
            print(f"✅ 数据库统计:")
            print(f"   总内容数: {row[0]}")
            print(f"   来源数: {row[1]}")
            print(f"   最新时间: {row[2]}")
            
            # 显示各来源统计
            result = await db.execute(
                text("""
                    SELECT source, COUNT(*) as count
                    FROM content_library
                    WHERE DATE(published_at) >= CURRENT_DATE - INTERVAL '1 day'
                    GROUP BY source
                    ORDER BY count DESC
                """)
            )
            
            print(f"\n📊 各来源统计:")
            for row in result.fetchall():
                print(f"   {row[0]}: {row[1]} 条")
            
            print("\n" + "=" * 60)
            print("✅ RSS抓取测试通过！")
            print("=" * 60)
            
            return True
            
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
            
        finally:
            await service.close()


async def test_all_sources():
    """测试所有来源"""
    print("=" * 60)
    print("全源内容抓取测试")
    print("=" * 60)
    
    async with AsyncSessionLocal() as db:
        service = ContentAggregatorService(db)
        
        try:
            print("\n📡 抓取所有来源...")
            contents = await service.fetch_all_sources()
            
            print(f"✅ 总共抓取 {len(contents)} 条内容")
            
            # 按来源统计
            from collections import Counter
            source_counts = Counter(c.source for c in contents)
            
            print(f"\n📊 各来源抓取统计:")
            for source, count in source_counts.items():
                print(f"   {source}: {count} 条")
            
            # 保存到数据库
            print(f"\n💾 保存到数据库...")
            saved_count = await service.save_contents_batch(contents)
            
            print(f"✅ 成功保存 {saved_count}/{len(contents)} 条内容")
            
            return True
            
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
            
        finally:
            await service.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "all":
        # 测试所有来源
        success = asyncio.run(test_all_sources())
    else:
        # 只测试RSS
        success = asyncio.run(test_rss_fetch())
    
    sys.exit(0 if success else 1)
