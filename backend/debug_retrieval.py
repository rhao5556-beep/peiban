"""
调试检索流程
"""
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')

async def debug():
    from neo4j import AsyncGraphDatabase
    from app.core.config import settings
    
    user_id = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"
    
    # 直接连接 Neo4j
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    
    async with driver.session() as session:
        # 1. 查看所有节点
        print("=== All nodes for user ===")
        result = await session.run(
            "MATCH (e {user_id: $user_id}) RETURN e.name, e.id, labels(e) LIMIT 20",
            user_id=user_id
        )
        async for record in result:
            print(f"  Node: {record['e.name']} (id={record['e.id']}, labels={record['labels(e)']})")
        
        # 2. 查看所有关系
        print("\n=== All relationships for user ===")
        result = await session.run(
            """
            MATCH (e {user_id: $user_id})-[r]->(t)
            RETURN e.name, type(r), t.name, r.desc
            LIMIT 20
            """,
            user_id=user_id
        )
        async for record in result:
            print(f"  {record['e.name']} --[{record['type(r)']}]--> {record['t.name']} (desc: {record['r.desc']})")
        
        # 3. 测试模糊匹配
        print("\n=== Fuzzy match test ===")
        test_names = ["二丫", "昊哥", "足球"]
        for name in test_names:
            result = await session.run(
                """
                MATCH (e {user_id: $user_id})
                WHERE e.name CONTAINS $name OR $name CONTAINS e.name
                RETURN e.name, e.id
                LIMIT 5
                """,
                user_id=user_id,
                name=name
            )
            matches = []
            async for record in result:
                matches.append(record['e.name'])
            print(f"  '{name}' matches: {matches}")
    
    await driver.close()

if __name__ == "__main__":
    asyncio.run(debug())
