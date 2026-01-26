"""
重置用户好感度为 0 的脚本
"""
import asyncio
import sys
from sqlalchemy import text
from app.core.database import get_async_session

async def reset_affinity(user_id: str):
    """将指定用户的好感度重置为 0"""
    async for session in get_async_session():
        try:
            # 插入一条新的好感度记录，将分数设为 0
            await session.execute(
                text("""
                    INSERT INTO affinity_history 
                    (user_id, old_score, new_score, delta, trigger_event, signals, created_at)
                    VALUES (:user_id, 
                            (SELECT new_score FROM affinity_history WHERE user_id = :user_id ORDER BY created_at DESC LIMIT 1),
                            0, 
                            -100, 
                            'manual_reset', 
                            '{"reason": "manual_reset"}'::jsonb,
                            NOW())
                """),
                {"user_id": user_id}
            )
            await session.commit()
            print(f"✅ 用户 {user_id} 的好感度已重置为 0")
            
        except Exception as e:
            print(f"❌ 重置失败: {e}")
            await session.rollback()
        finally:
            break

if __name__ == "__main__":
    user_id = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"  # 测试用户 ID
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
    
    asyncio.run(reset_affinity(user_id))
