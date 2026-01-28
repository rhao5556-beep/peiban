"""单条测试"""
import requests
import json
import time

API_BASE = "http://localhost:8000/api/v1"
USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"

def get_token():
    r = requests.post(f"{API_BASE}/auth/token", json={"user_id": USER_ID})
    return r.json()["access_token"]

def send_message(text):
    token = get_token()
    resp = requests.post(
        f"{API_BASE}/sse/message",
        json={"message": text},
        headers={"Authorization": f"Bearer {token}"},
        stream=True
    )
    
    memory_id = None
    for line in resp.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                data_str = line_str[6:]
                if data_str == '[DONE]':
                    break
                try:
                    event = json.loads(data_str)
                    if event.get('type') == 'memory_pending':
                        memory_id = event.get('memory_id')
                except:
                    pass
    return memory_id

def wait_commit(memory_id, timeout=60):
    token = get_token()
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(
                f"{API_BASE}/memories/{memory_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code == 200:
                if resp.json().get("status") == "committed":
                    return True
        except:
            pass
        time.sleep(2)
    return False

def get_graph():
    token = get_token()
    resp = requests.get(f"{API_BASE}/graph/", headers={"Authorization": f"Bearer {token}"})
    return resp.json()

# 测试
test_msg = "小明是我的好朋友，他喜欢打羽毛球，住在深圳"
print(f"发送: {test_msg}")

memory_id = send_message(test_msg)
print(f"Memory ID: {memory_id}")

if memory_id:
    print("等待提交...")
    if wait_commit(memory_id):
        print("✅ 已提交")
    else:
        print("⚠️ 超时")

time.sleep(3)

# 获取图谱
graph = get_graph()
print(f"\n=== 图谱 ===")
print(f"节点数: {len(graph['nodes'])}")
print(f"边数: {len(graph['edges'])}")

print("\n节点:")
for n in graph['nodes']:
    print(f"  - {n['name']} ({n['type']})")

print("\n关系:")
for e in graph['edges']:
    w = e.get('current_weight') or e.get('weight', 1)
    print(f"  - {e['relation_type']} (w={w:.2f})")
