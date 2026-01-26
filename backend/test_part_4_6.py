"""
针对第四部分和第六部分的专项测试
测试家庭关系识别和否定语义处理
"""
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
    ai_response = ""
    for line in resp.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                data_str = line_str[6:]
                if data_str == '[DONE]':
                    break
                try:
                    event = json.loads(data_str)
                    if event.get('type') == 'text':
                        ai_response += event.get('content', '')
                    elif event.get('type') == 'memory_pending':
                        memory_id = event.get('memory_id')
                except:
                    pass
    return memory_id, ai_response

def wait_commit(memory_id, timeout=60):
    if not memory_id:
        return False
    token = get_token()
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(
                f"{API_BASE}/memories/{memory_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code == 200:
                status = resp.json().get("status")
                if status == "committed":
                    return True
        except:
            pass
        time.sleep(2)
    return False

def get_graph():
    token = get_token()
    resp = requests.get(f"{API_BASE}/graph/", headers={"Authorization": f"Bearer {token}"})
    return resp.json()

def run_test(test_id, text, expected, notes=""):
    print(f"\n{'='*60}")
    print(f"测试 #{test_id}")
    print(f"输入: {text}")
    if notes:
        print(f"备注: {notes}")
    print(f"期望: {expected}")
    print(f"{'='*60}")
    
    # 获取测试前图谱
    graph_before = get_graph()
    edges_before = {(e['source_id'], e['target_id'], e['relation_type']) for e in graph_before['edges']}
    
    # 发送消息
    memory_id, ai_response = send_message(text)
    print(f"📤 消息已发送")
    print(f"💬 AI: {ai_response[:60]}..." if len(ai_response) > 60 else f"💬 AI: {ai_response}")
    
    if memory_id:
        print(f"🔄 等待提交...")
        if wait_commit(memory_id, timeout=60):
            print(f"✅ 已提交")
        else:
            print(f"⚠️ 超时")
            time.sleep(5)
    else:
        print(f"ℹ️ 无 Memory")
        time.sleep(3)
    
    # 获取测试后图谱
    graph_after = get_graph()
    edges_after = {(e['source_id'], e['target_id'], e['relation_type']) for e in graph_after['edges']}
    
    # 新增关系
    new_edges = edges_after - edges_before
    
    node_map = {n['id']: n['name'] for n in graph_after['nodes']}
    
    print(f"\n📊 新增关系: {len(new_edges)}")
    for src_id, tgt_id, rel_type in new_edges:
        src = node_map.get(src_id, src_id[:8])
        tgt = node_map.get(tgt_id, tgt_id[:8])
        print(f"    - {src} --[{rel_type}]--> {tgt}")
    
    return new_edges

# 测试用例
TESTS = [
    # 第四部分：家庭关系识别
    ("4.9", "小红是张伟的妹妹", "小红 → SIBLING_OF → 张伟", "测试兄弟姐妹关系"),
    ("4.14", "小红不是我同事，是我表妹", "user → COUSIN_OF → 小红", "测试否定语义 + 表亲关系"),
    
    # 第六部分：否定语义
    ("6.14", "李明是我朋友，不是同事", "user → FRIEND_OF → 李明（不应有 COLLEAGUE_OF）", "测试否定语义"),
    ("6.15", "我不喜欢游泳，但喜欢跑步", "user → DISLIKES → 游泳, user → LIKES → 跑步", "测试对比否定"),
]

if __name__ == "__main__":
    print("=" * 70)
    print("🧪 第四部分和第六部分专项测试")
    print("=" * 70)
    
    for test_id, text, expected, notes in TESTS:
        try:
            run_test(test_id, text, expected, notes)
        except Exception as e:
            print(f"❌ 测试 #{test_id} 失败: {e}")
        
        time.sleep(3)
    
    # 最终图谱
    print("\n" + "=" * 70)
    print("📊 最终图谱状态")
    print("=" * 70)
    
    graph = get_graph()
    print(f"总节点数: {len(graph['nodes'])}")
    print(f"总边数: {len(graph['edges'])}")
    
    print("\n所有关系:")
    node_map = {n['id']: n['name'] for n in graph['nodes']}
    for e in graph['edges']:
        src = node_map.get(e['source_id'], e['source_id'][:8])
        tgt = node_map.get(e['target_id'], e['target_id'][:8])
        print(f"  - {src} --[{e['relation_type']}]--> {tgt}")
