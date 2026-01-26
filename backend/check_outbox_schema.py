import psycopg2

conn = psycopg2.connect('postgresql://affinity:affinity_secret@localhost:5432/affinity')
cur = conn.cursor()

cur.execute("""
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_name='outbox_events'
    ORDER BY ordinal_position
""")

print("outbox_events 表结构：\n")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} (nullable={row[2]}, default={row[3]})")

conn.close()
