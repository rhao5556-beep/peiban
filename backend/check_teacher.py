"""检查老师相关的图谱数据"""
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')

async def check():
    from neo4j import AsyncGraphDatabase
    from app.core.config import settings
    
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    
    async with driver.session() as session:
        # 1. 查找所有包含"老师"或"妈妈"的节点
        print("=== 查找老师/妈妈相关节点 ===")
        result = await session.run(
            """
            MATCH (n)
            WHERE n.name CONTAINS '老师' OR n.name CONTAINS '妈妈' OR n.name CONTAINS '昊哥'
            RETURN n.name, n.id, labels(n), n.user_id
            """
        )
        async for record in result:
            print(f"  Node: {record['n.name']} (id={record['n.id']}, labels={record['labels(n)']}, user={record['n.user_id']})")
        
        # 2. 查找所有与"老师"相关的关系
        print("\n=== 查找老师相关关系 ===")
        result = await session.run(
            """
            MATCH (e)-[r]->(t)
            WHERE e.name CONTAINS '老师' OR t.name CONTAINS '老师' 
               OR e.name CONTAINS '妈妈' OR t.name CONTAINS '妈妈'
            RETURN e.name, type(r), t.name, r.weight, e.user_id
            """
        )
        async for record in result:
            print(f"  {record['e.name']} --[{record['type(r)']}]--> {record['t.name']} (weight={record['r.weight']})")
        
        # 3. 查找"我"节点和它的关系
        print("\n=== 查找 User 节点的关系 ===")
        result = await session.run(
            """
            MATCH (u:User)-[r]->(t)
            RETURN u.id, type(r), t.name, r.weight
            LIMIT 20
            """
        )
        async for record in result:
            print(f"  User({record['u.id'][:8]}...) --[{record['type(r)']}]--> {record['t.name']} (weight={record['r.weight']})")
        
        # 4. 查找最近创建的节点
        print("\n=== 最近的节点 ===")
        result = await session.run(
            """
            MATCH (n)
            WHERE n.name IS NOT NULL
            RETURN n.name, labels(n), n.user_id
            ORDER BY n.name
            LIMIT 30
            """
        )
        async for record in result:
            print(f"  {record['n.name']} ({record['labels(n)']}) - user: {record['n.user_id']}")
    
    await driver.close()

if __name__ == "__main__":
    asyncio.run(check())
