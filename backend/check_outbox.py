"""检查 outbox 事件状态"""
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)

with engine.connect() as conn:
    # 查询最近的 outbox 事件
    result = conn.execute(text("""
        SELECT 
            event_id,
            status,
            error_message,
            created_at,
            processed_at,
            payload::json->>'content' as content
        FROM outbox_events
        ORDER BY created_at DESC
        LIMIT 10
    """))
    
    print("最近 10 个 Outbox 事件:\n")
    for row in result:
        print(f"事件 ID: {row.event_id[:8]}...")
        print(f"状态: {row.status}")
        print(f"内容: {row.content[:50] if row.content else 'N/A'}...")
        if row.error_message:
            print(f"错误: {row.error_message[:100]}")
        print(f"创建时间: {row.created_at}")
        print(f"处理时间: {row.processed_at}")
        print("-" * 60)
