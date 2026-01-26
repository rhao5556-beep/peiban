#!/usr/bin/env python3
"""
重新同步记忆到 Neo4j
用于 Neo4j 重建后恢复图数据
"""

import sys
from sqlalchemy import create_engine, text
from app.core.config import settings

def resync_memories():
    """将所有已提交的记忆重新标记为 pending，让 Celery 重新处理"""
    
    # 添加 isolation_level 避免自动事务
    engine = create_engine(settings.DATABASE_URL, isolation_level="AUTOCOMMIT")
    
    with engine.connect() as conn:
        # 检查当前状态
        result = conn.execute(text("""
            SELECT 
                COUNT(*) FILTER (WHERE status = 'committed') as committed_count,
                COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
                COUNT(*) as total_count
            FROM memories
        """))
        
        stats = result.fetchone()
        
        print(f"\n📊 当前记忆状态：")
        print(f"  总计: {stats.total_count}")
        print(f"  已提交 (committed): {stats.committed_count}")
        print(f"  待处理 (pending): {stats.pending_count}")
        
        if stats.committed_count == 0:
            print("\n✅ 没有需要重新同步的记忆")
            return
        
        # 询问用户是否继续
        print(f"\n⚠️  将重新处理 {stats.committed_count} 条记忆到 Neo4j")
        print("   这将：")
        print("   1. 将记忆状态改为 pending")
        print("   2. 创建新的 outbox 事件")
        print("   3. Celery worker 会自动处理并同步到 Neo4j")
        
        response = input("\n是否继续？(y/n): ")
        if response.lower() != 'y':
            print("❌ 取消操作")
            return
        
        # 1. 将所有 committed 记忆改为 pending
        result = conn.execute(text("""
            UPDATE memories
            SET status = 'pending', committed_at = NULL
            WHERE status = 'committed'
        """))
        
        updated_memories = result.rowcount
        print(f"\n✅ 已将 {updated_memories} 条记忆标记为 pending")
        
        # 2. 为这些记忆创建新的 outbox 事件
        result = conn.execute(text("""
            INSERT INTO outbox_events (event_id, memory_id, payload, status, created_at)
            SELECT 
                'memory_created_' || id::text,
                id,
                jsonb_build_object(
                    'memory_id', id,
                    'user_id', user_id,
                    'content', content,
                    'created_at', created_at::text
                ),
                'pending',
                NOW()
            FROM memories
            WHERE status = 'pending'
        """))
        
        created_events = result.rowcount
        print(f"✅ 已创建 {created_events} 条新的 outbox 事件")
        
        print(f"\n🎉 重新同步完成！")
        print(f"   Celery worker 将在几秒内开始处理这些记忆")
        print(f"   预计处理时间: {updated_memories * 2} 秒 (假设每条 2 秒)")
        print(f"\n💡 提示：")
        print(f"   - 查看处理进度: docker logs affinity-celery-worker -f")
        print(f"   - 检查图谱: python check_graph.py")

if __name__ == "__main__":
    try:
        resync_memories()
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        sys.exit(1)
