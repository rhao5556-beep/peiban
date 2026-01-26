"""检查数据库约束"""
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT conname, pg_get_constraintdef(oid) 
        FROM pg_constraint 
        WHERE conrelid = 'outbox_events'::regclass AND contype = 'c'
    """))
    
    print("=== Outbox Events Check Constraints ===")
    for row in result:
        print(f"{row[0]}:")
        print(f"  {row[1]}")
        print()
