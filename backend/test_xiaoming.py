"""单独测试小明查询（反幻觉测试）"""
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
        
        print("测试: '小明喜欢什么' (图谱中无记录)")
        resp = await client.post(
            f"{API_BASE}/conversation/message",
            json={"message": "小明喜欢什么", "session_id": "test"},
            headers=headers
        )
        
        if resp.status_code == 200:
            reply = resp.json().get("reply", "")
            print(f"回复: {reply}")
            
            honest = ["不记得", "没告诉", "不知道", "没有", "还没", "不清楚"]
            if any(kw in reply for kw in honest):
                print("✓ 反幻觉成功")
            else:
                print("? 需要检查")
        else:
            print(f"失败: {resp.status_code}")


if __name__ == "__main__":
    asyncio.run(test())
