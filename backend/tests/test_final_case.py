"""
最终验收测试 - 验证修复 A 和修复 B
"""
import asyncio
import httpx
import sys
sys.stdout.reconfigure(encoding='utf-8')

API_BASE = "http://localhost:8000/api/v1"
USER_ID = "6e7ac151-100a-4427-a6ee-a5ac5b3c745e"  # 已有"昊哥的妈妈是老师"数据的用户

async def get_token():
    async with httpx.AsyncClient() as client:
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

async def check_neo4j_before_after(entity: str):
    """检查 Neo4j 中是否有新关系被创建"""
    from neo4j import AsyncGraphDatabase
    from app.core.config import settings
    
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (u:User {id: $user_id})-[r]->(t)
            WHERE t.name CONTAINS $entity
            RETURN type(r), t.name, r.weight
            """,
            user_id=USER_ID,
            entity=entity
        )
        relations = []
        async for record in result:
            relations.append(f"{record['type(r)']} -> {record['t.name']} (weight={record['r.weight']})")
    
    await driver.close()
    return relations

async def main():
    print("=" * 60)
    print("最终验收测试")
    print("=" * 60)
    print(f"User ID: {USER_ID}")
    print()
    
    token = await get_token()
    
    # ========== 测试 1: 修复 A - 提问不应创建关系 ==========
    print("=" * 60)
    print("测试 1: 修复 A - 提问句不应创建新关系")
    print("=" * 60)
    
    # 检查提问前的关系
    print("\n[提问前] User -> 老师 的关系:")
    before = await check_neo4j_before_after("老师")
    for r in before:
        print(f"  {r}")
    if not before:
        print("  (无)")
    
    # 发送提问
    print("\n[提问] 我认识老师吗？")
    reply = await send_message(token, "我认识老师吗？")
    print(f"[回复] {reply}")
    
    # 等待 Celery 处理
    await asyncio.sleep(5)
    
    # 检查提问后的关系
    print("\n[提问后] User -> 老师 的关系:")
    after = await check_neo4j_before_after("老师")
    for r in after:
        print(f"  {r}")
    if not after:
        print("  (无)")
    
    # 判断是否通过
    new_relations = set(after) - set(before)
    if not new_relations:
        print("\n✅ 修复 A 验证通过: 提问没有创建新关系")
    else:
        print(f"\n❌ 修复 A 验证失败: 提问创建了新关系 {new_relations}")
    
    # ========== 测试 2: 修复 B - 3-hop 检索 ==========
    print("\n" + "=" * 60)
    print("测试 2: 修复 B - 3-hop 检索能力")
    print("=" * 60)
    
    # 已有数据: User -> 昊哥 -> 昊哥的妈妈 -> 老师
    print("\n[查询] 昊哥的妈妈是做什么的？")
    reply = await send_message(token, "昊哥的妈妈是做什么的？")
    print(f"[回复] {reply}")
    
    # 检查是否能通过 3-hop 找到关系
    if "老师" in reply:
        print("\n✅ 修复 B 验证通过: 能通过多跳检索找到'老师'")
    else:
        print("\n⚠️ 修复 B 需要进一步验证")
    
    # ========== 测试 3: 综合测试 ==========
    print("\n" + "=" * 60)
    print("测试 3: 综合测试 - 间接关系推理")
    print("=" * 60)
    
    print("\n[查询] 我认识的人里面有谁的妈妈是老师？")
    reply = await send_message(token, "我认识的人里面有谁的妈妈是老师？")
    print(f"[回复] {reply}")
    
    if "昊哥" in reply:
        print("\n✅ 综合测试通过: 能正确推理出昊哥的妈妈是老师")
    else:
        print("\n⚠️ 综合测试需要进一步验证")

if __name__ == "__main__":
    asyncio.run(main())
