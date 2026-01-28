"""
多跳推理测试集 - Multi-hop Reasoning Test Suite
"""
import asyncio
import httpx
import subprocess

API_BASE = "http://localhost:8000/api/v1"
TOKEN = None
USER_ID = None

async def get_token():
    global TOKEN, USER_ID
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{API_BASE}/auth/token", json={})
        data = resp.json()
        TOKEN = data["access_token"]
        USER_ID = data["user_id"]
        print(f"Test User ID: {USER_ID}")

async def send_message(message: str) -> str:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{API_BASE}/conversation/message",
            json={"message": message},
            headers=headers
        )
        data = resp.json()
        if isinstance(data, dict):
            return data.get("reply", str(data))
        return str(data)

def check_neo4j(entity: str) -> str:
    cmd = f'docker exec affinity-neo4j cypher-shell -u neo4j -p neo4j_secret "MATCH (e {{user_id: \'{USER_ID}\'}})-[r]->(t) WHERE e.name CONTAINS \'{entity}\' RETURN e.name, type(r), t.name LIMIT 5"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

async def test_case(tid: str, setup_msgs: list, query: str, expected: str):
    print(f"\n{'='*50}\n{tid}\n{'='*50}")
    
    # 发送设置消息
    for msg in setup_msgs:
        print(f"[输入] {msg}")
        reply = await send_message(msg)
        print(f"[回复] {reply[:80]}...")
        await asyncio.sleep(2)
    
    # 发送查询
    print(f"\n[查询] {query}")
    reply = await send_message(query)
    print(f"[回复] {reply}")
    print(f"[期望] {expected}")
    
    return {"tid": tid, "reply": reply, "expected": expected}

async def main():
    print("=" * 50)
    print("多跳推理测试")
    print("=" * 50)
    
    await get_token()
    results = []
    
    # Group D: 反幻觉 (P0)
    print("\n\n### Group D: 反幻觉测试 (P0) ###")
    
    r = await test_case("D1",
        ["二丫喜欢踢足球。"],
        "那二丫擅长什么位置？",
        "应拒答：不知道位置信息")
    results.append(r)
    
    r = await test_case("D2",
        ["昊哥喜欢咖啡。"],
        "那昊哥每天喝几杯？",
        "应拒答：没有相关信息")
    results.append(r)
    
    # Group A: 两跳推理
    print("\n\n### Group A: 两跳推理 ###")
    
    r = await test_case("A1",
        ["我朋友二丫喜欢踢足球。", "踢足球需要经常去室外。"],
        "那二丫一般喜欢待在室内还是室外？",
        "室外（足球是室外运动）")
    results.append(r)
    
    r = await test_case("A2",
        ["昊哥最讨厌下雨天。", "下雨天通常会让人不方便出门。"],
        "那昊哥周末更可能选择宅家还是外出？",
        "宅家")
    results.append(r)
    
    # Group C: 跨实体多跳
    print("\n\n### Group C: 跨实体多跳 ###")
    
    r = await test_case("C1",
        ["二丫是昊哥的妹妹。", "昊哥喜欢踢足球。"],
        "那二丫平时更可能接触到什么运动？",
        "足球（通过昊哥）")
    results.append(r)
    
    # Group D2: 更多反幻觉
    print("\n\n### 额外反幻觉测试 ###")
    
    r = await test_case("D3",
        [],  # 不提供任何信息
        "小明喜欢什么？",
        "应拒答：不知道小明")
    results.append(r)
    
    # 报告
    print("\n\n" + "=" * 50)
    print("测试报告摘要")
    print("=" * 50)
    for r in results:
        print(f"\n{r['tid']}:")
        print(f"  回复: {r['reply'][:60]}...")
        print(f"  期望: {r['expected']}")

if __name__ == "__main__":
    asyncio.run(main())
