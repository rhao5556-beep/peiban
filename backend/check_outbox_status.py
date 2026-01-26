import psycopg2

conn = psycopg2.connect('postgresql://affinity:affinity_secret@localhost:5432/affinity')
cur = conn.cursor()

print("\n📊 Outbox 事件状态：")
cur.execute("SELECT status, COUNT(*) FROM outbox_events GROUP BY status")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n📋 最近 5 条 pending 事件：")
cur.execute("""
    SELECT event_id, memory_id, created_at 
    FROM outbox_events 
    WHERE status = 'pending' 
    ORDER BY created_at DESC 
    LIMIT 5
""")
for row in cur.fetchall():
    print(f"  {row[0][:30]}... | {row[2]}")

conn.close()
