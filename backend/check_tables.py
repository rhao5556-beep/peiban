from sqlalchemy import create_engine, text

engine = create_engine('postgresql://affinity:affinity_secret@localhost:5432/affinity')
conn = engine.connect()
print('Connected')
result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
tables = [row[0] for row in result]
print("Tables:", tables)

required_tables = ['user_content_preference', 'recommendation_history', 'content_library']
for table in required_tables:
    if table not in tables:
        print(f"MISSING TABLE: {table}")
    else:
        print(f"Found table: {table}")
conn.close()
