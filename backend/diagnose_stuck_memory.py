"""诊断卡住的记忆"""
from sqlalchemy import create_engine, text
from app.core.config import settings
import json

engine = create_engine(settings.DATABASE_URL)

with engine.connect() as conn:
    # 查找 pending 状态的记忆
    result = conn.execute(text("""
        SELECT m.id, m.content, m.created_at, m.status,
               o.event_id, o.status as outbox_status, o.error_message
        FROM memories m
        LEFT JOIN outbox_events o ON m.id = o.memory_id
        WHERE m.status = 'pending'
        ORDER BY m.created_at DESC
    """))
    
    print("=== Pending Memories with Outbox Status ===\n")
    for row in result:
        print(f"Memory ID: {row[0]}")
        print(f"Content: {row[1][:100]}")
        print(f"Created: {row[2]}")
        print(f"Memory Status: {row[3]}")
        print(f"Outbox Event ID: {row[4]}")
        print(f"Outbox Status: {row[5]}")
        if row[6]:
            print(f"Error Message: {row[6]}")
        print("-" * 80)
        print()
    
    # 检查 DLQ 中的完整错误信息
    result2 = conn.execute(text("""
        SELECT event_id, memory_id, error_message, payload
        FROM outbox_events
        WHERE status = 'dlq'
        ORDER BY created_at DESC
        LIMIT 3
    """))
    
    print("\n=== DLQ Events Detail ===\n")
    for row in result2:
        print(f"Event ID: {row[0]}")
        print(f"Memory ID: {row[1]}")
        print(f"Error: {row[2]}")
        print(f"Payload: {json.dumps(json.loads(row[3]) if isinstance(row[3], str) else row[3], indent=2, ensure_ascii=False)[:500]}")
        print("-" * 80)
        print()
