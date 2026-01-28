"""测试 Neo4j 连接"""
import asyncio
from neo4j import AsyncGraphDatabase

async def test_neo4j():
    try:
        # 直接使用配置中的连接信息
        driver = AsyncGraphDatabase.driver(
            "bolt://localhost:7687",
            auth=("neo4j", "neo4j_secret")
        )
        
        # 测试连接
        await driver.verify_connectivity()
        print("Neo4j 连接成功")
        
        # 测试查询
        session = driver.session()
        result = await session.run("RETURN 1 as test")
        record = await result.single()
        print(f"Neo4j 查询成功: {record['test']}")
        
        # 检查是否有数据
        result = await session.run("MATCH (n) RETURN count(n) as count")
        record = await result.single()
        print(f"Neo4j 节点数量: {record['count']}")
        
        await session.close()
        await driver.close()
        
    except Exception as e:
        print(f"Neo4j 连接失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_neo4j())