#!/usr/bin/env python3
"""
临时修复脚本：将卡住的 pending 记忆标记为 committed
用于解决 LLM API 超时导致的记忆处理失败问题
"""

import sys
from sqlalchemy import create_engine, text
from app.core.config import settings

def fix_pending_memories():
    """将所有 pending 状态且 outbox 为 done 的记忆标记为 committed"""
    
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        # 查找所有 pending 记忆
        result = conn.execute(text("""
            SELECT m.id, m.user_id, m.created_at, o.status as outbox_status
            FROM memories m
            LEFT JOIN outbox_events o ON m.id = o.memory_id
            WHERE m.status = 'pending'
            ORDER BY m.created_at DESC
            LIMIT 20
        """))
        
        pending_memories = result.fetchall()
        
        if not pending_memories:
            print("✅ 没有 pending 状态的记忆")
            return
        
        print(f"\n📋 发现 {len(pending_memories)} 条 pending 记忆：\n")
        for mem in pending_memories:
            print(f"  - {str(mem.id)[:8]}... | outbox: {mem.outbox_status} | {mem.created_at}")
        
        # 询问用户是否继续
        response = input("\n是否将这些记忆标记为 committed？(y/n): ")
        if response.lower() != 'y':
            print("❌ 取消操作")
            return
        
        # 更新记忆状态
        result = conn.execute(text("""
            UPDATE memories
            SET status = 'committed', committed_at = NOW()
            WHERE status = 'pending'
        """))
        
        conn.commit()
        
        updated_count = result.rowcount
        print(f"\n✅ 成功更新 {updated_count} 条记忆状态为 committed")
        
        # 同时将对应的 outbox 事件标记为 done
        result = conn.execute(text("""
            UPDATE outbox_events
            SET status = 'done', processed_at = NOW()
            WHERE status IN ('pending', 'processing')
            AND memory_id IN (
                SELECT id FROM memories WHERE status = 'committed'
            )
        """))
        
        conn.commit()
        
        outbox_updated = result.rowcount
        print(f"✅ 成功更新 {outbox_updated} 条 outbox 事件状态为 done")

if __name__ == "__main__":
    try:
        fix_pending_memories()
    except Exception as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)
