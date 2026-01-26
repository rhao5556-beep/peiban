"""检查小红的表亲关系"""
import requests

API_BASE = "http://localhost:8000/api/v1"
USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"

def get_token():
    r = requests.post(f"{API_BASE}/auth/token", json={"user_id": USER_ID})
    return r.json()["access_token"]

token = get_token()
graph = requests.get(f"{API_BASE}/graph/", headers={"Authorization": f"Bearer {token}"}).json()

print(f"总节点数: {len(graph['nodes'])}")
print(f"总边数: {len(graph['edges'])}")

# 查找小红相关的关系
node_map = {n['id']: n['name'] for n in graph['nodes']}
print("\n小红相关的关系:")
for e in graph['edges']:
    src = node_map.get(e['source_id'], e['source_id'][:8])
    tgt = node_map.get(e['target_id'], e['target_id'][:8])
    if '小红' in src or '小红' in tgt:
        print(f"  {src} --[{e['relation_type']}]--> {tgt}")

# 查找所有 COUSIN_OF 关系
print("\n所有 COUSIN_OF 关系:")
cousin_found = False
for e in graph['edges']:
    if e['relation_type'] == 'COUSIN_OF':
        src = node_map.get(e['source_id'], e['source_id'][:8])
        tgt = node_map.get(e['target_id'], e['target_id'][:8])
        print(f"  {src} --[COUSIN_OF]--> {tgt}")
        cousin_found = True

if not cousin_found:
    print("  (未找到)")
