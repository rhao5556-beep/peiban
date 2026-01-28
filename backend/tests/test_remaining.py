"""继续测试剩余的测试用例 (9-20)"""
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

def run_test(test_id, category, text, expected, notes=""):
    print(f"\n{'='*60}")
    print(f"测试 #{test_id} [{category}]")
    print(f"输入: {text}")
    if notes:
        print(f"备注: {notes}")
    print(f"期望: {expected}")
    print(f"{'='*60}")
    
    # 获取测试前图谱
    graph_before = get_graph()
    nodes_before = set(n['id'] for n in graph_before['nodes'])
    edges_before = set(f"{e['source_id']}->{e['target_id']}" for e in graph_before['edges'])
    
    # 发送消息
    memory_id, ai_response = send_message(text)
    print(f"📤 消息已发送")
    print(f"💬 AI: {ai_response[:80]}...")
    
    if memory_id:
        print(f"🔄 等待提交 (id: {memory_id[:16]}...)...")
        if wait_commit(memory_id, timeout=45):
            print(f"✅ 已提交")
        else:
            print(f"⚠️ 超时，等待后台处理...")
            time.sleep(10)  # 额外等待
    else:
        print(f"ℹ️ 无 Memory")
        time.sleep(5)
    
    # 获取测试后图谱
    graph_after = get_graph()
    nodes_after = set(n['id'] for n in graph_after['nodes'])
    edges_after = set(f"{e['source_id']}->{e['target_id']}" for e in graph_after['edges'])
    
    # 新增内容
    new_nodes = nodes_after - nodes_before
    new_edges = edges_after - edges_before
    
    node_map = {n['id']: n['name'] for n in graph_after['nodes']}
    
    print(f"\n📊 结果:")
    print(f"  新增节点: {len(new_nodes)}")
    for nid in new_nodes:
        n = next((x for x in graph_after['nodes'] if x['id'] == nid), None)
        if n:
            print(f"    - {n['name']} ({n['type']})")
    
    print(f"  新增关系: {len(new_edges)}")
    for eid in new_edges:
        e = next((x for x in graph_after['edges'] if f"{x['source_id']}->{x['target_id']}" == eid), None)
        if e:
            src = node_map.get(e['source_id'], e['source_id'][:8])
            tgt = node_map.get(e['target_id'], e['target_id'][:8])
            print(f"    - {src} --[{e['relation_type']}]--> {tgt}")
    
    return {
        "test_id": test_id,
        "new_nodes": len(new_nodes),
        "new_edges": len(new_edges)
    }

# 剩余测试用例 (9-20)
REMAINING_TESTS = [
    # 9. 语义理解
    ("9", "语义理解", "二丫其实就是张伟的妹妹", 
     "二丫 → SIBLING_OF → 张伟", "⚠️ 强语义理解"),
    
    # 10. 实体消歧
    ("10", "实体消歧", "二丫最近换工作了",
     "必须复用已有 id，不允许新建", ""),
    
    # 11. 指代消解
    ("11", "指代消解", "她最近压力很大",
     "'她'指代最近活跃实体", ""),
    
    # 12. 跨句理解
    ("12", "跨句理解", "我有个朋友叫二丫 她很喜欢打篮球",
     "user → FRIEND_OF → 二丫, 二丫 → LIKES → 篮球", ""),
    
    # 13. 跨句理解
    ("13", "跨句理解", "张伟是我同事 他和二丫关系很好",
     "user → COLLEAGUE → 张伟, 张伟 → RELATED_TO → 二丫", ""),
    
    # 14. 否定语义
    ("14", "否定语义", "二丫不是我同事，是我表妹",
     "user → COUSIN_OF/FAMILY → 二丫", "不应保留'同事'关系"),
    
    # 15. 否定语义
    ("15", "否定语义", "我不太喜欢篮球，但二丫很喜欢",
     "user → DISLIKES → 篮球, 二丫 → LIKES → 篮球", ""),
    
    # 16. 推断关系
    ("16", "推断关系", "二丫经常加班，看起来工作压力不小",
     "二丫 → HAS_STATE → 工作压力大", "允许 confidence < 1.0"),
    
    # 17. 推断关系
    ("17", "推断关系", "张伟好像在上海发展",
     "张伟 → WORKS_AT/LIVES_IN → 上海", "metadata.confidence < 1.0"),
    
    # 20. 复合测试（终极）
    ("20", "复合测试", "二丫是我朋友，她喜欢篮球，也和张伟是大学同学，现在在北京工作",
     "user→FRIEND_OF→二丫, 二丫→LIKES→篮球, 二丫↔CLASSMATE_OF↔张伟, 二丫→WORKS_AT→北京",
     "终极测试：多实体多关系"),
]

if __name__ == "__main__":
    print("=" * 70)
    print("🧪 继续测试剩余用例 (9-20)")
    print("=" * 70)
    
    results = []
    for test_id, category, text, expected, notes in REMAINING_TESTS:
        try:
            result = run_test(test_id, category, text, expected, notes)
            results.append(result)
        except Exception as e:
            print(f"❌ 测试 #{test_id} 失败: {e}")
        
        time.sleep(3)  # 测试间隔
    
    # 最终图谱状态
    print("\n" + "=" * 70)
    print("📊 最终图谱状态")
    print("=" * 70)
    
    graph = get_graph()
    print(f"总节点数: {len(graph['nodes'])}")
    print(f"总边数: {len(graph['edges'])}")
    
    print("\n所有节点:")
    for n in graph['nodes']:
        print(f"  - {n['name']} ({n['type']})")
    
    print("\n所有关系:")
    node_map = {n['id']: n['name'] for n in graph['nodes']}
    for e in graph['edges']:
        src = node_map.get(e['source_id'], e['source_id'][:8])
        tgt = node_map.get(e['target_id'], e['target_id'][:8])
        w = e.get('current_weight') or e.get('weight', 1)
        print(f"  - {src} --[{e['relation_type']}]--> {tgt} ({w:.0%})")
