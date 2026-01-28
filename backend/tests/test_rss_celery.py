"""
测试Celery RSS抓取功能

验证：
1. Celery Worker是否正常运行
2. RSS抓取任务是否可以执行
3. 内容是否成功保存到数据库
"""
import asyncio
import sys
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def test_rss_fetch():
    """测试RSS抓取功能"""
    print("=" * 60)
    print("测试Celery RSS抓取功能")
    print("=" * 60)
    
    # 1. 检查当前内容数量
    print("\n1. 检查当前内容数量...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT COUNT(*) as total,
                       COUNT(DISTINCT source) as sources
                FROM content_library
                WHERE DATE(fetched_at) = CURRENT_DATE
            """)
        )
        row = result.fetchone()
        print(f"   今日内容: {row[0]} 条")
        print(f"   来源数量: {row[1]} 个")
        
        before_count = row[0]
    
    # 2. 触发Celery任务
    print("\n2. 触发Celery任务...")
    print("   请手动执行以下命令：")
    print("   docker exec affinity-celery-worker celery -A app.worker call content.test_fetch")
    print("\n   等待任务完成（约10-30秒）...")
    print("   按Enter继续...")
    input()
    
    # 3. 检查更新后的内容数量
    print("\n3. 检查更新后的内容数量...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT COUNT(*) as total,
                       COUNT(DISTINCT source) as sources
                FROM content_library
                WHERE DATE(fetched_at) = CURRENT_DATE
            """)
        )
        row = result.fetchone()
        print(f"   今日内容: {row[0]} 条")
        print(f"   来源数量: {row[1]} 个")
        
        after_count = row[0]
        new_count = after_count - before_count
        
        if new_count > 0:
            print(f"\n   ✅ 成功抓取 {new_count} 条新内容！")
        else:
            print(f"\n   ⚠️  没有新内容，可能原因：")
            print("      - RSS源返回的内容已存在（去重）")
            print("      - RSS源无法访问")
            print("      - 任务执行失败")
    
    # 4. 显示最新内容
    print("\n4. 显示最新5条内容...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT source, title, content_url, fetched_at
                FROM content_library
                ORDER BY fetched_at DESC
                LIMIT 5
            """)
        )
        
        rows = result.fetchall()
        for i, row in enumerate(rows, 1):
            print(f"\n   {i}. [{row[0]}] {row[1]}")
            print(f"      URL: {row[2]}")
            print(f"      时间: {row[3]}")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_rss_fetch())
