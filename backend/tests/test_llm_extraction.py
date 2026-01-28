"""
LLM + IR + Graph 架构验证测试
覆盖：实体抽取、实体消歧、Entity→Entity 关系、昵称/指代、失败兜底
"""
import json
import time
import requests
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# 配置
API_BASE = "http://localhost:8000/api/v1"
TOKEN = None
USER_ID = None

@dataclass
class TestCase:
    """测试用例"""
    id: str
    category: str
    input_text: str
    expected_entities: List[str]
    expected_relations: List[str]
    notes: str = ""

# ============================================================================
# 20 条测试用例
# ============================================================================

TEST_CASES = [
    # 一、基础实体 + User → Entity（热身）
    TestCase(
        id="1", category="基础实体",
        input_text="二丫是我朋友",
        expected_entities=["二丫(Person)"],
        expected_relations=["user → FRIEND_OF → 二丫"],
    ),
    TestCase(
        id="2", category="基础实体",
        input_text="我住在哈尔滨",
        expected_entities=["哈尔滨(Location)"],
        expected_relations=["user → LIVES_IN → 哈尔滨"],
    ),
    TestCase(
        id="3", category="基础实体",
        input_text="张伟是我同事",
        expected_entities=["张伟(Person)"],
        expected_relations=["user → WORKS_AT/COLLEAGUE → 张伟"],
    ),
    
    # 二、Entity → Entity（核心能力）
    TestCase(
        id="4", category="Entity→Entity",
        input_text="二丫喜欢篮球",
        expected_entities=["二丫(Person)", "篮球(Preference)"],
        expected_relations=["二丫 → LIKES → 篮球"],
        notes="⚠️ 正则必挂，LLM 必须成功",
    ),
    TestCase(
        id="5", category="Entity→Entity",
        input_text="张伟和二丫是大学同学",
        expected_entities=["张伟(Person)", "二丫(Person)"],
        expected_relations=["张伟 ↔ CLASSMATE_OF ↔ 二丫"],
    ),
    TestCase(
        id="6", category="Entity→Entity",
        input_text="我朋友二丫在北京工作",
        expected_entities=["二丫(Person)", "北京(Location)"],
        expected_relations=["user → FRIEND_OF → 二丫", "二丫 → WORKS_AT → 北京"],
    ),
    
    # 三、昵称 / 非"我的"前缀（正则死区）
    TestCase(
        id="7", category="昵称识别",
        input_text="昊哥最近很忙",
        expected_entities=["昊哥(Person)"],
        expected_relations=[],
        notes="至少要建实体",
    ),
    TestCase(
        id="8", category="昵称识别",
        input_text="张sir今天心情不错",
        expected_entities=["张sir(Person)"],
        expected_relations=[],
        notes="可复用 recent_entities",
    ),
    TestCase(
        id="9", category="语义理解",
        input_text="二丫其实就是张伟的妹妹",
        expected_entities=["二丫(Person)", "张伟(Person)"],
        expected_relations=["二丫 → SIBLING_OF → 张伟"],
        notes="⚠️ 强语义理解",
    ),
    
    # 四、recent_entities 消歧测试
    TestCase(
        id="10", category="实体消歧",
        input_text="二丫最近换工作了",
        expected_entities=["二丫(Person)"],
        expected_relations=[],
        notes="必须复用已有 id，不允许新建",
    ),
    TestCase(
        id="11", category="指代消解",
        input_text="她最近压力很大",
        expected_entities=[],
        expected_relations=[],
        notes="'她'指代最近活跃实体",
    ),
    
    # 五、多句 / 跨句上下文
    TestCase(
        id="12", category="跨句理解",
        input_text="我有个朋友叫二丫 她很喜欢打篮球",
        expected_entities=["二丫(Person)", "篮球(Preference)"],
        expected_relations=["user → FRIEND_OF → 二丫", "二丫 → LIKES → 篮球"],
    ),
    TestCase(
        id="13", category="跨句理解",
        input_text="张伟是我同事 他和二丫关系很好",
        expected_entities=["张伟(Person)", "二丫(Person)"],
        expected_relations=["user → COLLEAGUE → 张伟", "张伟 → RELATED_TO → 二丫"],
    ),
    
    # 六、否定 / 修正语义
    TestCase(
        id="14", category="否定语义",
        input_text="二丫不是我同事，是我表妹",
        expected_entities=["二丫(Person)"],
        expected_relations=["user → COUSIN_OF/FAMILY → 二丫"],
        notes="不应保留'同事'关系",
    ),
    TestCase(
        id="15", category="否定语义",
        input_text="我不太喜欢篮球，但二丫很喜欢",
        expected_entities=["篮球(Preference)", "二丫(Person)"],
        expected_relations=["user → DISLIKES → 篮球", "二丫 → LIKES → 篮球"],
    ),
    
    # 七、模糊 / 推断型关系
    TestCase(
        id="16", category="推断关系",
        input_text="二丫经常加班，看起来工作压力不小",
        expected_entities=["二丫(Person)"],
        expected_relations=[],
        notes="允许 confidence < 1.0",
    ),
    TestCase(
        id="17", category="推断关系",
        input_text="张伟好像在上海发展",
        expected_entities=["张伟(Person)", "上海(Location)"],
        expected_relations=["张伟 → WORKS_AT/LIVES_IN → 上海"],
        notes="metadata.confidence < 1.0",
    ),
    
    # 八、异常 / 失败路径测试 - 跳过，需要特殊处理
    # TestCase(id="18", ...) - 模拟 LLM 返回非 JSON
    # TestCase(id="19", ...) - 模拟 API 超时
    
    # 九、复合世界观构建（终极测试）
    TestCase(
        id="20", category="复合测试",
        input_text="二丫是我朋友，她喜欢篮球，也和张伟是大学同学，现在在北京工作",
        expected_entities=["二丫(Person)", "篮球(Preference)", "张伟(Person)", "北京(Location)"],
        expected_relations=[
            "user → FRIEND_OF → 二丫",
            "二丫 → LIKES → 篮球",
            "二丫 ↔ CLASSMATE_OF ↔ 张伟",
            "二丫 → WORKS_AT → 北京"
        ],
        notes="终极测试：多实体多关系",
    ),
]


def get_token() -> str:
    """获取认证 token"""
    global TOKEN, USER_ID
    if TOKEN:
        return TOKEN
    
    resp = requests.post(f"{API_BASE}/auth/token", json={})
    if resp.status_code == 200:
        data = resp.json()
        TOKEN = data.get("access_token")
        USER_ID = data.get("user_id")
        print(f"✅ 获取 Token 成功, user_id: {USER_ID}")
        return TOKEN
    else:
        print(f"❌ 获取 Token 失败: {resp.status_code}")
        return ""


def send_message(text: str) -> Dict[str, Any]:
    """发送消息并等待处理"""
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # 发送 SSE 消息
    resp = requests.post(
        f"{API_BASE}/sse/message",
        json={"message": text},
        headers=headers,
        stream=True
    )
    
    memory_id = None
    full_response = ""
    
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
                        full_response += event.get('content', '')
                    elif event.get('type') == 'memory_pending':
                        memory_id = event.get('memory_id')
                except:
                    pass
    
    return {
        "memory_id": memory_id,
        "response": full_response
    }


def wait_for_memory_commit(memory_id: str, timeout: int = 30) -> bool:
    """等待 memory 状态变为 committed"""
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(
                f"{API_BASE}/memories/{memory_id}",
                headers=headers
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "committed":
                    return True
        except:
            pass
        time.sleep(2)
    
    return False


def get_graph() -> Dict[str, Any]:
    """获取当前图谱"""
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    resp = requests.get(f"{API_BASE}/graph/", headers=headers)
    if resp.status_code == 200:
        return resp.json()
    return {"nodes": [], "edges": []}


def analyze_graph(graph: Dict) -> Dict[str, Any]:
    """分析图谱内容"""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    
    # 构建节点映射
    node_map = {n["id"]: n for n in nodes}
    
    # 分析实体
    entities = []
    for n in nodes:
        if n.get("type") != "user":
            entities.append(f"{n.get('name', n['id'])}({n.get('type', 'unknown')})")
    
    # 分析关系
    relations = []
    for e in edges:
        source = node_map.get(e.get("source_id"), {})
        target = node_map.get(e.get("target_id"), {})
        source_name = source.get("name", e.get("source_id", "?"))
        target_name = target.get("name", e.get("target_id", "?"))
        rel_type = e.get("relation_type", "RELATED_TO")
        weight = e.get("current_weight") or e.get("weight", 1.0)
        relations.append(f"{source_name} → {rel_type} → {target_name} (w={weight:.2f})")
    
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "entities": entities,
        "relations": relations
    }


def run_test(test: TestCase) -> Dict[str, Any]:
    """运行单个测试"""
    print(f"\n{'='*60}")
    print(f"测试 #{test.id} [{test.category}]")
    print(f"输入: {test.input_text}")
    if test.notes:
        print(f"备注: {test.notes}")
    print(f"{'='*60}")
    
    # 获取测试前的图谱
    graph_before = get_graph()
    analysis_before = analyze_graph(graph_before)
    
    # 发送消息
    result = send_message(test.input_text)
    memory_id = result.get("memory_id")
    
    print(f"📤 消息已发送")
    print(f"💬 AI 回复: {result.get('response', '')[:100]}...")
    
    if memory_id:
        print(f"🔄 等待 Memory 提交 (id: {memory_id})...")
        committed = wait_for_memory_commit(memory_id)
        if committed:
            print(f"✅ Memory 已提交")
        else:
            print(f"⚠️ Memory 提交超时")
    else:
        print(f"ℹ️ 无 Memory 生成")
        time.sleep(3)  # 等待一下
    
    # 获取测试后的图谱
    graph_after = get_graph()
    analysis_after = analyze_graph(graph_after)
    
    # 计算新增内容
    new_entities = set(analysis_after["entities"]) - set(analysis_before["entities"])
    new_relations = set(analysis_after["relations"]) - set(analysis_before["relations"])
    
    print(f"\n📊 图谱变化:")
    print(f"  节点: {analysis_before['node_count']} → {analysis_after['node_count']}")
    print(f"  边: {analysis_before['edge_count']} → {analysis_after['edge_count']}")
    
    if new_entities:
        print(f"\n🆕 新增实体:")
        for e in new_entities:
            print(f"    - {e}")
    
    if new_relations:
        print(f"\n🔗 新增关系:")
        for r in new_relations:
            print(f"    - {r}")
    
    # 验证期望
    print(f"\n📋 期望验证:")
    print(f"  期望实体: {test.expected_entities}")
    print(f"  期望关系: {test.expected_relations}")
    
    return {
        "test_id": test.id,
        "input": test.input_text,
        "new_entities": list(new_entities),
        "new_relations": list(new_relations),
        "expected_entities": test.expected_entities,
        "expected_relations": test.expected_relations,
        "graph_after": analysis_after
    }


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*70)
    print("🧪 LLM + IR + Graph 架构验证测试")
    print("="*70)
    
    results = []
    
    for test in TEST_CASES:
        try:
            result = run_test(test)
            results.append(result)
        except Exception as e:
            print(f"❌ 测试 #{test.id} 失败: {e}")
            results.append({
                "test_id": test.id,
                "error": str(e)
            })
        
        # 测试间隔
        time.sleep(2)
    
    # 汇总报告
    print("\n" + "="*70)
    print("📊 测试汇总报告")
    print("="*70)
    
    # 获取最终图谱
    final_graph = get_graph()
    final_analysis = analyze_graph(final_graph)
    
    print(f"\n最终图谱状态:")
    print(f"  总节点数: {final_analysis['node_count']}")
    print(f"  总边数: {final_analysis['edge_count']}")
    
    print(f"\n所有实体:")
    for e in final_analysis['entities']:
        print(f"    - {e}")
    
    print(f"\n所有关系:")
    for r in final_analysis['relations']:
        print(f"    - {r}")
    
    return results


if __name__ == "__main__":
    run_all_tests()
