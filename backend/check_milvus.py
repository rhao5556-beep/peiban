"""检查 Milvus 中的数据"""
from pymilvus import connections, Collection

connections.connect(host="localhost", port="19530")
col = Collection("memories")

# 查询所有数据
results = col.query(
    expr='user_id == "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"',
    output_fields=["id", "content", "user_id"],
    limit=50
)

print(f"Found {len(results)} records in Milvus:")
for r in results:
    print(f"  - {r['content'][:60]}...")
