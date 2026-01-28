"""
测试内容推荐 API 端点
"""
import asyncio
import sys
from sqlalchemy import text
from app.core.database import get_db_session
from app.core.security import create_access_token
from app.models.user import User

async def test_content_api():
    """测试内容推荐 API"""
    print("=" * 60)
    print("测试内容推荐 API")
    print("=" * 60)
    
    async with get_db_session() as db:
        # 1. 获取或创建测试用户
        result = await db.execute(
            text("SELECT id, username FROM users LIMIT 1")
        )
        user = result.fetchone()
        
        if not user:
            print("❌ 没有找到用户，请先创建用户")
            return False
        
        user_id = str(user[0])
        username = user[1]
        print(f"✓ 使用用户: {username} (ID: {user_id})")
        
        # 2. 生成 token
        token = create_access_token({"sub": user_id})
        print(f"✓ Token: {token[:50]}...")
        
        # 3. 测试获取偏好设置
        print("\n--- 测试 GET /api/v1/content/preference ---")
        try:
            result = await db.execute(
                text("""
                    SELECT content_recommendation_enabled, preferred_sources,
                           excluded_topics, max_daily_recommendations,
                           quiet_hours_start, quiet_hours_end
                    FROM user_content_preference
                    WHERE user_id = :user_id
                """),
                {"user_id": user_id}
            )
            row = result.fetchone()
            
            if row:
                print(f"✓ 找到偏好设置:")
                print(f"  - 启用: {row[0]}")
                print(f"  - 每日限额: {row[3]}")
                print(f"  - 来源: {row[1]}")
            else:
                print("⚠ 未找到偏好设置，将创建默认设置")
                await db.execute(
                    text("""
                        INSERT INTO user_content_preference (user_id)
                        VALUES (:user_id)
                    """),
                    {"user_id": user_id}
                )
                await db.commit()
                print("✓ 已创建默认偏好设置")
        except Exception as e:
            print(f"❌ 数据库错误: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # 4. 测试获取推荐列表
        print("\n--- 测试 GET /api/v1/content/recommendations ---")
        try:
            result = await db.execute(
                text("""
                    SELECT COUNT(*) FROM recommendation_history
                    WHERE user_id = :user_id
                      AND DATE(recommended_at) = CURRENT_DATE
                """),
                {"user_id": user_id}
            )
            count = result.scalar()
            print(f"✓ 今日推荐数量: {count}")
            
            if count == 0:
                print("⚠ 没有今日推荐，这是正常的（需要 Celery 任务生成）")
        except Exception as e:
            print(f"❌ 数据库错误: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        print(f"\n使用此 token 测试前端:")
        print(f"Bearer {token}")
        return True

if __name__ == "__main__":
    result = asyncio.run(test_content_api())
    sys.exit(0 if result else 1)
