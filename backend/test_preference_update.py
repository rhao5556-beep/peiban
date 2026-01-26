"""测试内容推荐偏好更新"""
import asyncio
from datetime import time as time_type
from sqlalchemy import text
from app.core.database import get_db_session

async def test_update():
    async with get_db_session() as db:
        user_id = '6e7ac151-100a-4427-a6ee-a5ac5b3c745e'
        
        # 测试更新
        updates = []
        params = {"user_id": user_id}
        
        # 启用推荐
        updates.append("content_recommendation_enabled = :enabled")
        params["enabled"] = True
        
        # 设置数量
        updates.append("max_daily_recommendations = :max_daily")
        params["max_daily"] = 5
        
        # 设置来源
        updates.append("preferred_sources = :sources")
        params["sources"] = ["rss", "weibo"]
        
        # 设置时间
        updates.append("quiet_hours_start = :start")
        params["start"] = time_type(22, 0)
        
        updates.append("quiet_hours_end = :end")
        params["end"] = time_type(8, 0)
        
        updates.append("updated_at = NOW()")
        
        query = f"""
            UPDATE user_content_preference
            SET {', '.join(updates)}
            WHERE user_id = :user_id
        """
        
        print("Query:", query)
        print("Params:", params)
        
        try:
            await db.execute(text(query), params)
            await db.commit()
            print("✅ Update successful!")
            
            # 验证更新
            result = await db.execute(
                text("""
                    SELECT content_recommendation_enabled, max_daily_recommendations,
                           preferred_sources, quiet_hours_start, quiet_hours_end
                    FROM user_content_preference
                    WHERE user_id = :user_id
                """),
                {"user_id": user_id}
            )
            row = result.fetchone()
            if row:
                print(f"✅ Verified: enabled={row[0]}, daily={row[1]}, sources={row[2]}, start={row[3]}, end={row[4]}")
            else:
                print("❌ No data found")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(test_update())
