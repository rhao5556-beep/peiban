"""检查图谱状态"""
import requests
import json

# 使用已有的 user_id
user_id = '9a9e9803-94d6-4ecd-8d09-66fb4745ef85'
r = requests.post('http://localhost:8000/api/v1/auth/token', json={'user_id': user_id})
t = r.json()['access_token']
print(f'Token for user {user_id}')

g = requests.get('http://localhost:8000/api/v1/graph/', headers={'Authorization': f'Bearer {t}'})
data = g.json()
print(f'Nodes: {len(data["nodes"])}')
print(f'Edges: {len(data["edges"])}')
print()
print('=== Nodes ===')
for n in data['nodes']:
    print(f"  {n['name']} ({n['type']})")
print()
print('=== Edges ===')
for e in data['edges']:
    w = e.get('current_weight') or e.get('weight', 1)
    print(f"  {e['source_id'][:8]}... --[{e['relation_type']}]--> {e['target_id'][:8]}... (w={w:.2f})")
