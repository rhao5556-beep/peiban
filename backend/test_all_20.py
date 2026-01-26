"""
完整的 20 条测试用例 - 覆盖全部九个部分
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

def wait_commit(memory_id, timeout=45):
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
                elif status == "pending_review":
                    return "pending_review"
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
    print(f"💬 AI: {ai_response[:80]}..." if len(ai_response) > 80 else f"💬 AI: {ai_response}")
    
    if memory_id:
        print(f"🔄 等待提交 (id: {memory_id[:16]}...)...")
        result = wait_commit(memory_id, timeout=45)
        if result == True:
            print(f"✅ 已提交")
        elif result == "pending_review":
            print(f"⚠️ 进入 pending_review（符合预期）")
        else:
            print(f"⚠️ 超时")
            time.sleep(5)
    else:
        print(f"ℹ️ 无 Memory")
        time.sleep(3)
    
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

# ============================================================================
# 完整 20 条测试用例 - 九个部分
# ============================================================================

ALL_TESTS = [
    # ========== 一、基础实体 + User → Entity（热身）==========
    ("1", "一、基础实体", "二丫是我朋友",
     "Entity: 二丫(Person), Relation: user → FRIEND_OF → 二丫", ""),
    
    ("2", "一、基础实体", "我住在哈尔滨",
     "Entity: 哈尔滨(Location), Relation: user → LIVES_IN → 哈尔滨", ""),
    
    ("3", "一、基础实体", "张伟是我同事",
     "Entity: 张伟(Person), Relation: user → COLLEAGUE_OF → 张伟", ""),
    
    # ========== 二、Entity → Entity（核心能力）==========
    ("4", "二、Entity→Entity", "二丫喜欢篮球",
     "Entity: 二丫, 篮球, Relation: 二丫 → LIKES → 篮球", "⚠️ 正则必挂，LLM 必须成功"),
    
    ("5", "二、Entity→Entity", "张伟和二丫是大学同学",
     "Relation: 张伟 ↔ CLASSMATE_OF ↔ 二丫", ""),
    
    ("6", "二、Entity→Entity", "我朋友二丫在北京工作",
     "user → FRIEND_OF → 二丫, 二丫 → WORKS_IN → 北京", ""),
    
    # ========== 三、昵称 / 非"我的"前缀（正则死区）==========
    ("7", "三、昵称识别", "昊哥最近很忙",
     "Entity: 昊哥(Person)", "至少要建实体"),
    
    ("8", "三、昵称识别", "张sir今天心情不错",
     "Entity: 张sir(Person)", "可复用 recent_entities 中的张伟"),
    
    # ========== 四、recent_entities 消歧测试 ==========
    ("9", "四、语义理解", "二丫其实就是张伟的妹妹",
     "Relation: 二丫 → SIBLING_OF → 张伟", "⚠️ 强语义理解"),
    
    ("10", "四、实体消歧", "二丫最近换工作了",
     "必须复用已有 id，不允许新建", ""),
    
    ("11", "四、指代消解", "她最近压力很大",
     "'她'指代最近活跃实体（二丫）", ""),
    
    # ========== 五、多句 / 跨句上下文 ==========
    ("12", "五、跨句理解", "我有个朋友叫二丫 她很喜欢打篮球",
     "user → FRIEND_OF → 二丫, 二丫 → LIKES → 篮球", ""),
    
    ("13", "五、跨句理解", "张伟是我同事 他和二丫关系很好",
     "user → COLLEAGUE → 张伟, 张伟 → HAS_GOOD_RELATION → 二丫", ""),
    
    # ========== 六、否定 / 修正语义（LLM 优势区）==========
    ("14", "六、否定语义", "二丫不是我同事，是我表妹",
     "user → COUSIN_OF → 二丫", "不应保留'同事'关系"),
    
    ("15", "六、否定语义", "我不太喜欢篮球，但二丫很喜欢",
     "user → DISLIKES → 篮球, 二丫 → LIKES → 篮球", ""),
    
    # ========== 七、模糊 / 推断型关系 ==========
    ("16", "七、推断关系", "二丫经常加班，看起来工作压力不小",
     "二丫 → HAS_STATE → 工作压力大", "允许 confidence < 1.0"),
    
    ("17", "七、推断关系", "张伟好像在上海发展",
     "张伟 → PROBABLY_WORKS_IN → 上海", "metadata.confidence < 1.0"),
    
    # ========== 八、异常 / 失败路径测试（非常关键）==========
    # 注意：18、19 需要特殊处理，这里用正常消息模拟
    ("18", "八、异常测试", "asdfghjkl123456",
     "❌ 不写入 Neo4j, ✅ 标记 pending_review", "模拟无意义输入"),
    
    ("19", "八、异常测试", "!@#$%^&*()",
     "❌ 不写入 Neo4j, ✅ 标记 pending_review", "模拟特殊字符"),
    
    # ========== 九、复合世界观构建（终极测试）==========
    ("20", "九、复合测试", "二丫是我朋友，她喜欢篮球，也和张伟是大学同学，现在在北京工作",
     "user→FRIEND_OF→二丫, 二丫→LIKES→篮球, 二丫↔CLASSMATE_OF↔张伟, 二丫→WORKS_AT→北京",
     "终极测试：多实体多关系"),
]

if __name__ == "__main__":
    print("=" * 70)
    print("🧪 完整 20 条测试用例 - 覆盖全部九个部分")
    print("=" * 70)
    print("""
    一、基础实体 + User → Entity（1-3）
    二、Entity → Entity（4-6）
    三、昵称 / 非"我的"前缀（7-8）
    四、recent_entities 消歧测试（9-11）
    五、多句 / 跨句上下文（12-13）
    六、否定 / 修正语义（14-15）
    七、模糊 / 推断型关系（16-17）
    八、异常 / 失败路径测试（18-19）
    九、复合世界观构建（20）
    """)
    
    results = []
    for test_id, category, text, expected, notes in ALL_TESTS:
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
    
    # 统计
    print("\n" + "=" * 70)
    print("📈 测试统计")
    print("=" * 70)
    total_new_nodes = sum(r.get('new_nodes', 0) for r in results)
    total_new_edges = sum(r.get('new_edges', 0) for r in results)
    print(f"  测试用例数: {len(results)}")
    print(f"  新增节点总数: {total_new_nodes}")
    print(f"  新增关系总数: {total_new_edges}")
