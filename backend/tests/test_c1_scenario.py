"""
测试 C1 场景：跨实体多跳推理
使用已有数据的用户 ID
"""
import asyncio
import httpx
import sys
sys.stdout.reconfigure(encoding='utf-8')

API_BASE = "http://localhost:8000/api/v1"

# 使用已有数据的用户
USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"

async def get_token_for_user():
    """为指定用户获取 token"""
    async with httpx.AsyncClient() as client:
        # 直接用 user_id 登录
        resp = await client.post(f"{API_BASE}/auth/token", json={"user_id": USER_ID})
        data = resp.json()
        return data["access_token"]

async def send_message(token: str, message: str) -> str:
    headers = {"Authorization": f"Bearer {token}"}
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

async def main():
    print("=" * 60)
    print("C1 场景测试：跨实体多跳推理")
    print("=" * 60)
    print(f"User ID: {USER_ID}")
    print()
    
    # 获取 token
    token = await get_token_for_user()
    print(f"Token obtained")
    print()
    
    # 已有数据：
    # - 二丫 喜欢 踢足球
    # - 二丫 SIBLING_OF 张伟
    # - 昊哥 喜欢 踢足球
    
    # 测试 1: 直接查询已有事实
    print("=" * 60)
    print("Test 1: 直接查询 - 二丫喜欢什么？")
    print("=" * 60)
    reply = await send_message(token, "二丫喜欢什么？")
    print(f"回复: {reply}")
    print()
    
    # 测试 2: 查询关系
    print("=" * 60)
    print("Test 2: 关系查询 - 二丫和张伟是什么关系？")
    print("=" * 60)
    reply = await send_message(token, "二丫和张伟是什么关系？")
    print(f"回复: {reply}")
    print()
    
    # 测试 3: 2-hop 推理
    print("=" * 60)
    print("Test 3: 2-hop 推理 - 张伟的妹妹喜欢什么运动？")
    print("=" * 60)
    reply = await send_message(token, "张伟的妹妹喜欢什么运动？")
    print(f"回复: {reply}")
    print()
    
    # 测试 4: 反幻觉
    print("=" * 60)
    print("Test 4: 反幻觉 - 二丫擅长什么位置？")
    print("=" * 60)
    reply = await send_message(token, "二丫擅长什么位置？")
    print(f"回复: {reply}")

if __name__ == "__main__":
    asyncio.run(main())
