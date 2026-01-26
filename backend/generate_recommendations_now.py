"""
直接生成今日推荐（绕过 Celery）
"""
import asyncio
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://affinity:affinity_secret@affinity-postgres:5432/affinity"

async def main():
    print("=" * 60)
    print("开始生成今日推荐...")
    print("=" * 60)
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # 获取所有用户
        result = await db.execute(
            text("SELECT user_id FROM user_content_preference WHERE content_recommendation_enabled = true")
        )
        users = result.fetchall()
        
        if not users:
            print("❌ 没有启用推荐的用户")
            return
        
        print(f"📊 找到 {len(users)} 个启用推荐的用户")
        
        for user_row in users:
            user_id = str(user_row[0])
            print(f"\n👤 为用户 {user_id[:8]}... 生成推荐")
            
            # 获取用户偏好
            pref_result = await db.execute(
                text("""
                    SELECT preferred_sources, max_daily_recommendations
                    FROM user_content_preference
                    WHERE user_id = :user_id
                """),
                {"user_id": user_id}
            )
            pref_row = pref_result.fetchone()
            
            preferred_sources = pref_row[0] if pref_row[0] else []
            max_daily = pref_row[1] if pref_row else 5
            
            # 构建查询条件
            source_filter = ""
            if preferred_sources:
                sources_str = "', '".join(preferred_sources)
                source_filter = f"AND source IN ('{sources_str}')"
            
            # 获取今日内容（按质量分数排序）
            content_result = await db.execute(
                text(f"""
                    SELECT id, source, title, summary, content_url, tags, published_at, quality_score
                    FROM content_library
                    WHERE DATE(published_at) = CURRENT_DATE
                    {source_filter}
                    ORDER BY quality_score DESC, published_at DESC
                    LIMIT :limit
                """),
                {"limit": max_daily}
            )
            
            contents = content_result.fetchall()
            
            if not contents:
                print(f"  ⚠️  没有找到符合条件的内容")
                continue
            
            # 插入推荐记录
            inserted_count = 0
            for rank, content_row in enumerate(contents, 1):
                content_id = str(content_row[0])
                
                # 检查是否已推荐过
                check_result = await db.execute(
                    text("""
                        SELECT id FROM recommendation_history
                        WHERE user_id = :user_id AND content_id = :content_id
                        AND DATE(recommended_at) = CURRENT_DATE
                    """),
                    {"user_id": user_id, "content_id": content_id}
                )
                
                if check_result.scalar_one_or_none():
                    continue
                
                # 插入推荐
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
                print(f"  ✅ [{content_row[1]}] {content_row[2]}")
            
            await db.commit()
            print(f"  📊 成功生成 {inserted_count} 条推荐")
        
        print("\n" + "=" * 60)
        print("✅ 推荐生成完成！")
        print("=" * 60)
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
