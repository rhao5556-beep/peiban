"""诊断图谱同步问题"""
import psycopg2

conn = psycopg2.connect('postgresql://affinity:affinity_secret@localhost:5432/affinity')
cur = conn.cursor()

# 检查记忆数量
cur.execute('SELECT COUNT(*) FROM memories')
memory_count = cur.fetchone()[0]
print(f'✅ PostgreSQL memories: {memory_count}')

# 检查 outbox 状态
cur.execute("SELECT status, COUNT(*) FROM outbox_events GROUP BY status")
outbox_stats = cur.fetchall()
print(f'\n📦 Outbox events:')
for status, count in outbox_stats:
    print(f'  {status}: {count}')

# 检查最近的 outbox 事件
cur.execute("""
    SELECT id, event_type, status, created_at, processed_at, error_message
    FROM outbox_events
    ORDER BY created_at DESC
    LIMIT 5
""")
recent_events = cur.fetchall()
print(f'\n🕐 Recent outbox events:')
for event in recent_events:
    event_id, event_type, status, created_at, processed_at, error = event
    print(f'  [{status}] {event_type} - {created_at}')
    if error:
        print(f'    Error: {error[:100]}')

conn.close()
