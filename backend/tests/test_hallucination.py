"""真正的反幻觉测试 - 查询完全不存在的人"""
import asyncio
import httpx

API_BASE = "http://localhost:8000/api/v1"
USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"


async def test():
    async with httpx.AsyncClient(timeout=90.0) as client:
        # 获取 token
        resp = await client.post(f"{API_BASE}/auth/token", json={"user_id": USER_ID})
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        print("=" * 60)
        print("反幻觉测试")
        print("=" * 60)
        
        # 测试 1: 小明 - Milvus 中有记录，应该能回答
        print("\n[1] 测试: '小明喜欢什么' (Milvus有记录，Neo4j无记录)")
        resp1 = await client.post(
            f"{API_BASE}/conversation/message",
            json={"message": "小明喜欢什么", "session_id": "test"},
            headers=headers
        )
        if resp1.status_code == 200:
            reply1 = resp1.json().get("reply", "")
            print(f"   回复: {reply1}")
            if "羽毛球" in reply1:
                print("   ✓ 正确！从对话历史中召回了小明喜欢羽毛球")
        
        # 测试 2: 王五 - 完全不存在的人
        print("\n[2] 测试: '王五喜欢什么' (完全不存在 - 真正的反幻觉测试)")
        resp2 = await client.post(
            f"{API_BASE}/conversation/message",
            json={"message": "王五喜欢什么", "session_id": "test"},
            headers=headers
        )
        if resp2.status_code == 200:
            reply2 = resp2.json().get("reply", "")
            print(f"   回复: {reply2}")
            
            honest = ["不记得", "没告诉", "不知道", "没有找到", "还没", "不清楚", "告诉我", "不太记得"]
            if any(kw in reply2 for kw in honest):
                print("   ✓ 反幻觉成功！系统诚实表示不知道")
            else:
                print("   ✗ 可能存在幻觉")
        
        # 测试 3: 李华 - 完全不存在的人
        print("\n[3] 测试: '李华住在哪里' (完全不存在)")
        resp3 = await client.post(
            f"{API_BASE}/conversation/message",
            json={"message": "李华住在哪里", "session_id": "test"},
            headers=headers
        )
        if resp3.status_code == 200:
            reply3 = resp3.json().get("reply", "")
            print(f"   回复: {reply3}")
            
            honest = ["不记得", "没告诉", "不知道", "没有找到", "还没", "不清楚", "告诉我", "不太记得", "没有具体聊过", "没有聊过"]
            if any(kw in reply3 for kw in honest):
                print("   ✓ 反幻觉成功！")
            else:
                print("   ✗ 可能存在幻觉")
        
        print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(test())
