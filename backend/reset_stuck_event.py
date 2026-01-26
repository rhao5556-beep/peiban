"""重置卡住的 outbox 事件"""
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)

with engine.connect() as conn:
    # 重置卡在 processing 的事件
    result = conn.execute(text("""
        UPDATE outbox_events
        SET status = 'pending'
        WHERE event_id = '0cd7f4be-722a-4c45-ab88-4aa4b61a276f'
        RETURNING event_id, status
    """))
    conn.commit()
    
    row = result.fetchone()
    if row:
        print(f"✅ 事件 {row.event_id[:8]}... 已重置为 {row.status}")
    else:
        print("❌ 未找到事件")
