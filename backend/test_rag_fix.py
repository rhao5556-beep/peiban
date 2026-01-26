"""
测试 RAG 修复 - 验证图谱事实检索和反幻觉功能

测试场景：
1. 查询已知实体（二丫、昊哥）的喜好
2. 查询未知实体（小明）的喜好 - 应该说不知道
"""
import asyncio
import httpx

API_BASE = "http://localhost:8000/api/v1"
USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"


async def get_token(client: httpx.AsyncClient, user_id: str) -> str:
    """获取认证 token"""
    resp = await client.post(
        f"{API_BASE}/auth/token",
        json={"user_id": user_id}
    )
    if resp.status_code == 200:
        return resp.json()["access_token"]
    raise Exception(f"Failed to get token: {resp.status_code} {resp.text}")


async def test_rag_retrieval():
    """测试 RAG 检索修复"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        print("=" * 60)
        print("RAG 修复测试")
        print("=" * 60)
        
        # 获取认证 token
        print("\n[0] 获取认证 token...")
        token = await get_token(client, USER_ID)
        headers = {"Authorization": f"Bearer {token}"}
        print(f"   ✓ Token 获取成功")
        
        # 测试 1: 查询二丫（图谱中有记录）
        print("\n[1] 测试查询: '二丫喜欢什么' (图谱中有记录)")
        resp1 = await client.post(
            f"{API_BASE}/conversation/message",
            json={"message": "二丫喜欢什么", "session_id": "test-rag"},
            headers=headers
        )
        if resp1.status_code == 200:
            reply1 = resp1.json().get("reply", "")
            print(f"   回复: {reply1}")
            if "足球" in reply1 or "篮球" in reply1:
                print("   ✓ 正确召回了二丫的喜好")
            else:
                print("   ? 回复中没有提到足球/篮球")
        
        # 测试 2: 查询昊哥（图谱中有记录）
        print("\n[2] 测试查询: '昊哥喜欢什么' (图谱中有记录)")
        resp2 = await client.post(
            f"{API_BASE}/conversation/message",
            json={"message": "昊哥喜欢什么", "session_id": "test-rag"},
            headers=headers
        )
        if resp2.status_code == 200:
            reply2 = resp2.json().get("reply", "")
            print(f"   回复: {reply2}")
            if "足球" in reply2:
                print("   ✓ 正确召回了昊哥的喜好（图谱中确实有昊哥喜欢足球的记录）")
        
        # 测试 3: 查询小明（图谱中没有记录）- 关键测试
        print("\n[3] 测试查询: '小明喜欢什么' (图谱中无记录 - 反幻觉测试)")
        resp3 = await client.post(
            f"{API_BASE}/conversation/message",
            json={"message": "小明喜欢什么", "session_id": "test-rag"},
            headers=headers
        )
        if resp3.status_code == 200:
            reply3 = resp3.json().get("reply", "")
            print(f"   回复: {reply3}")
            
            # 检查是否正确表示不知道
            honest_keywords = ["不记得", "没告诉", "不知道", "没有", "还没", "不清楚"]
            is_honest = any(kw in reply3 for kw in honest_keywords)
            
            # 检查是否有幻觉
            hallucination_keywords = ["喜欢", "爱好", "运动", "音乐", "游戏", "阅读"]
            has_hallucination = any(kw in reply3 for kw in hallucination_keywords) and not is_honest
            
            if is_honest:
                print("   ✓ 反幻觉成功！系统诚实表示不知道")
            elif has_hallucination:
                print("   ✗ 检测到幻觉！系统编造了小明的喜好")
            else:
                print("   ? 需要人工检查")
        
        # 测试 4: 查询张sir（图谱中有记录）
        print("\n[4] 测试查询: '张sir住在哪里' (图谱中有记录)")
        resp4 = await client.post(
            f"{API_BASE}/conversation/message",
            json={"message": "张sir住在哪里", "session_id": "test-rag"},
            headers=headers
        )
        if resp4.status_code == 200:
            reply4 = resp4.json().get("reply", "")
            print(f"   回复: {reply4}")
            if "哈尔滨" in reply4:
                print("   ✓ 正确召回了张sir的居住地")
        
        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_rag_retrieval())
