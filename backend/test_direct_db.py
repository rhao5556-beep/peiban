"""直接测试数据库查询"""
import asyncio
from sqlalchemy import text
from app.core.database import get_db

async def test_query():
    async for db in get_db():
        # 测试查询今日内容
        result = await db.execute(
            text("""
                SELECT id, source, title, summary, content_url, tags, published_at, quality_score
                FROM content_library
                WHERE DATE(published_at) = CURRENT_DATE
                ORDER BY quality_score DESC, published_at DESC
                LIMIT 3
            """)
        )
        
        contents = result.fetchall()
        print(f"找到 {len(contents)} 条今日内容:")
        
        for content in contents:
            print(f"\n  ID: {content[0]}")
            print(f"  来源: {content[1]}")
            print(f"  标题: {content[2]}")
            print(f"  质量分: {content[7]}")
        
        break

asyncio.run(test_query())
