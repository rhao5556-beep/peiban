#!/usr/bin/env python3
"""图谱恢复进度报告"""

import psycopg2
import requests

# 1. 检查 Outbox 状态
conn = psycopg2.connect('postgresql://affinity:affinity_secret@localhost:5432/affinity')
cur = conn.cursor()

cur.execute("SELECT status, COUNT(*) FROM outbox_events GROUP BY status")
outbox_stats = {row[0]: row[1] for row in cur.fetchall()}

pending = outbox_stats.get('pending', 0)
processing = outbox_stats.get('processing', 0)
done = outbox_stats.get('done', 0)
total = pending + processing + done

progress = (done / total * 100) if total > 0 else 0

print("=" * 60)
print("📊 图谱恢复进度报告")
print("=" * 60)

print(f"\n🔄 Outbox 处理进度：")
print(f"  总计: {total} 条记忆")
print(f"  已完成: {done} 条 ({progress:.1f}%)")
print(f"  处理中: {processing} 条")
print(f"  待处理: {pending} 条")

# 2. 检查图谱数据
user_id = '9a9e9803-94d6-4ecd-8d09-66fb4745ef85'
r = requests.post('http://localhost:8000/api/v1/auth/token', json={'user_id': user_id})
token = r.json()['access_token']

g = requests.get('http://localhost:8000/api/v1/graph/', headers={'Authorization': f'Bearer {token}'})
graph_data = g.json()

nodes = graph_data['nodes']
edges = graph_data['edges']

print(f"\n📈 Neo4j 图谱数据：")
print(f"  节点数: {len(nodes)}")
print(f"  边数: {len(edges)}")

# 按类型统计节点
node_types = {}
for node in nodes:
    node_type = node['type']
    node_types[node_type] = node_types.get(node_type, 0) + 1

print(f"\n  节点类型分布：")
for node_type, count in sorted(node_types.items()):
    print(f"    {node_type}: {count}")

# 显示部分节点
print(f"\n  最近添加的节点（前 10 个）：")
for i, node in enumerate(nodes[:10]):
    print(f"    {i+1}. {node['name']} ({node['type']})")

# 3. 预估完成时间
if pending > 0:
    avg_time_per_memory = 2  # 秒
    estimated_seconds = pending * avg_time_per_memory
    estimated_minutes = estimated_seconds / 60
    
    print(f"\n⏱️  预计完成时间：")
    print(f"  剩余: {pending} 条记忆")
    print(f"  预计: {estimated_minutes:.1f} 分钟")
else:
    print(f"\n✅ 所有记忆已同步完成！")

print("\n" + "=" * 60)

conn.close()
