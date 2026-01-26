"""
为当前登录的用户生成推荐
"""
import asyncio
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://affinity:affinity_secret@affinity-postgres:5432/affinity"

async def main():
    print("=" * 60)
    print("为所有用户生成今日推荐...")
    print("=" * 60)
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # 获取所有用户（不限制是否启用推荐）
        result = await db.execute(
            text("SELECT DISTINCT id FROM users")
        )
        users = result.fetchall()
        
        print(f"📊 找到 {len(users)} 个用户")
        
        # 获取今日内容
        content_result = await db.execute(
            text("""
                SELECT id, source, title, summary, content_url, tags, published_at, quality_score
                FROM content_library
                WHERE DATE(published_at) = CURRENT_DATE
                ORDER BY quality_score DESC, published_at DESC
                LIMIT 5
            """)
        )
        
        contents = content_result.fetchall()
        
        if not contents:
            print("❌ 没有今日内容")
            return
        
        print(f"📰 找到 {len(contents)} 条今日内容")
        
        total_inserted = 0
        
        for user_row in users:
            user_id = str(user_row[0])
            
            # 检查是否已有推荐
            check_result = await db.execute(
                text("""
                    SELECT COUNT(*) FROM recommendation_history
                    WHERE user_id = :user_id AND DATE(recommended_at) = CURRENT_DATE
                """),
                {"user_id": user_id}
            )
            
            existing_count = check_result.scalar()
            
            if existing_count > 0:
                print(f"⏭️  用户 {user_id[:8]}... 已有 {existing_count} 条推荐")
                continue
            
            # 插入推荐记录（取前3条）
            inserted_count = 0
            for rank, content_row in enumerate(contents[:3], 1):
                content_id = str(content_row[0])
                
                try:
                    await db.execute(
                        text("""
                            INSERT INTO recommendation_history (
                                user_id, content_id, match_score, rank_position, recommended_at
                            ) VALUES (
                                :user_id, :content_id, :match_score, :rank_position, NOW()
                            )
                        """),
                        {
                            "user_id": user_id,
                            "content_id": content_id,
                            "match_score": float(content_row[7]),  # quality_score
                            "rank_position": rank,
                        }
                    )
                    inserted_count += 1
                except Exception as e:
                    print(f"  ⚠️  插入失败: {e}")
                    continue
            
            if inserted_count > 0:
                await db.commit()
                total_inserted += inserted_count
                print(f"✅ 用户 {user_id[:8]}... 生成 {inserted_count} 条推荐")
        
        print("\n" + "=" * 60)
        print(f"✅ 完成！共生成 {total_inserted} 条新推荐")
        print("=" * 60)
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
