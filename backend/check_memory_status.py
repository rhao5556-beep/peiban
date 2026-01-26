"""检查记忆和 Outbox 状态"""
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)

with engine.connect() as conn:
    # 检查最近的记忆状态
    result = conn.execute(text("""
        SELECT id, status, created_at, committed_at 
        FROM memories 
        ORDER BY created_at DESC 
        LIMIT 10
    """))
    
    print("=== Recent Memories ===")
    for row in result:
        print(f"ID: {row[0]}")
        print(f"  Status: {row[1]}")
        print(f"  Created: {row[2]}")
        print(f"  Committed: {row[3]}")
        print()
    
    # 检查最近的 Outbox 事件
    result2 = conn.execute(text("""
        SELECT event_id, status, memory_id, created_at, processed_at, error_message 
        FROM outbox_events 
        ORDER BY created_at DESC 
        LIMIT 10
    """))
    
    print("\n=== Recent Outbox Events ===")
    for row in result2:
        print(f"Event ID: {row[0]}")
        print(f"  Status: {row[1]}")
        print(f"  Memory ID: {row[2]}")
        print(f"  Created: {row[3]}")
        print(f"  Processed: {row[4]}")
        if row[5]:
            print(f"  Error: {row[5][:100]}")
        print()
    
    # 统计各状态的数量
    result3 = conn.execute(text("""
        SELECT status, COUNT(*) 
        FROM memories 
        GROUP BY status
    """))
    
    print("\n=== Memory Status Summary ===")
    for row in result3:
        print(f"{row[0]}: {row[1]}")
    
    result4 = conn.execute(text("""
        SELECT status, COUNT(*) 
        FROM outbox_events 
        GROUP BY status
    """))
    
    print("\n=== Outbox Status Summary ===")
    for row in result4:
        print(f"{row[0]}: {row[1]}")
