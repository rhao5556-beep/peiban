#!/usr/bin/env python3
"""为 pending 记忆创建缺失的 outbox 事件"""

import sys
from sqlalchemy import create_engine, text
from app.core.config import settings

def create_outbox_events():
    """为所有 pending 记忆创建 outbox 事件"""
    
    engine = create_engine(settings.DATABASE_URL, isolation_level="AUTOCOMMIT")
    
    with engine.connect() as conn:
        # 检查有多少 pending 记忆没有 outbox 事件
        result = conn.execute(text("""
            SELECT COUNT(*)
            FROM memories m
            WHERE m.status = 'pending'
            AND NOT EXISTS (
                SELECT 1 FROM outbox_events o
                WHERE o.memory_id = m.id
                AND o.status = 'pending'
            )
        """))
        
        missing_count = result.scalar()
        
        print(f"\n📊 发现 {missing_count} 条 pending 记忆缺少 outbox 事件")
        
        if missing_count == 0:
            print("✅ 所有记忆都有对应的 outbox 事件")
            return
        
        # 为这些记忆创建 outbox 事件
        result = conn.execute(text("""
            INSERT INTO outbox_events (event_id, memory_id, payload, status, created_at)
            SELECT 
                'memory_created_' || m.id::text,
                m.id,
                jsonb_build_object(
                    'memory_id', m.id,
                    'user_id', m.user_id,
                    'content', m.content,
                    'created_at', m.created_at::text
                ),
                'pending',
                NOW()
            FROM memories m
            WHERE m.status = 'pending'
            AND NOT EXISTS (
                SELECT 1 FROM outbox_events o
                WHERE o.memory_id = m.id
                AND o.status = 'pending'
            )
        """))
        
        created_count = result.rowcount
        print(f"✅ 成功创建 {created_count} 条 outbox 事件")
        print(f"\n🎉 完成！Celery worker 将在几秒内开始处理")
        print(f"   预计处理时间: {created_count * 2} 秒")
        print(f"\n💡 监控命令：")
        print(f"   docker logs affinity-celery-worker -f --tail 50")

if __name__ == "__main__":
    try:
        create_outbox_events()
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
