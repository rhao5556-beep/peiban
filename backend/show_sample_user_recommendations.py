"""
显示一个有推荐的用户的完整信息
用于前端测试
"""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://affinity:affinity_secret@affinity-postgres:5432/affinity"

async def main():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # 获取一个有推荐的用户
        result = await db.execute(
            text("""
                SELECT DISTINCT user_id
                FROM recommendation_history
                WHERE DATE(recommended_at) = CURRENT_DATE
                LIMIT 1
            """)
        )
        
        user_id = result.scalar_one()
        
        print("=" * 60)
        print("示例用户信息（用于前端测试）")
        print("=" * 60)
        print(f"\n📋 User ID: {user_id}")
        print(f"\n💡 使用方法：")
        print(f"1. 打开浏览器开发者工具（F12）")
        print(f"2. 进入 Console 标签页")
        print(f"3. 执行以下命令：")
        print(f"\n   localStorage.setItem('affinity_user_id', '{user_id}')")
        print(f"\n4. 刷新页面")
        
        # 获取该用户的推荐
        rec_result = await db.execute(
            text("""
                SELECT c.source, c.title, c.content_url, rh.match_score, rh.rank_position
                FROM recommendation_history rh
                JOIN content_library c ON rh.content_id = c.id
                WHERE rh.user_id = :user_id
                  AND DATE(rh.recommended_at) = CURRENT_DATE
                ORDER BY rh.rank_position
            """),
            {"user_id": str(user_id)}
        )
        
        recommendations = rec_result.fetchall()
        
        print(f"\n📰 该用户的推荐内容（{len(recommendations)} 条）：")
        for rec in recommendations:
            print(f"\n{rec[4]}. [{rec[0]}] {rec[1]}")
            print(f"   URL: {rec[2]}")
            print(f"   匹配度: {rec[3]:.0%}")
        
        print("\n" + "=" * 60)
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
