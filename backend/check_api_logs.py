"""检查最近的 API 请求日志"""
import asyncio
import sys
sys.path.insert(0, '.')

from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def check_recent_requests():
    """检查最近的对话请求"""
    print("=" * 60)
    print("检查最近的对话记录")
    print("=" * 60)
    
    async with AsyncSessionLocal() as db:
        # 检查最近的对话轮次
        result = await db.execute(
            text("""
                SELECT session_id, role, content, created_at
                FROM conversation_turns
                ORDER BY created_at DESC
                LIMIT 10
            """)
        )
        rows = result.fetchall()
        
        if not rows:
            print("\n没有找到对话记录")
            return
        
        print(f"\n最近 {len(rows)} 条对话:")
        for row in rows:
            session_id, role, content, created_at = row
            print(f"\n[{created_at}] {role}")
            print(f"Session: {session_id[:8]}...")
            print(f"内容: {content[:100]}")


if __name__ == "__main__":
    asyncio.run(check_recent_requests())
