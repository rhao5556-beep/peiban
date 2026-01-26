"""测试语义扩展检索功能 - 解决"谁住海边"问题"""
import asyncio
import sys
sys.path.insert(0, '.')

from app.services.retrieval_service import RetrievalService, EmbeddingService
from neo4j import AsyncGraphDatabase

# 配置
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "neo4j_secret"
USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"


async def test_semantic_retrieval():
    """测试语义扩展检索"""
    print("=" * 60)
    print("测试语义扩展检索功能")
    print("=" * 60)
    
    # 初始化服务
    retrieval_service = RetrievalService()
    neo4j_driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
    
    try:
        # 测试用例
        test_queries = [
            "谁住在海边",
            "我认识的人谁住在海边",
            "谁来自南方",
            "谁喜欢运动",
        ]
        
        for query in test_queries:
            print(f"\n{'='*60}")
            print(f"查询: {query}")
            print("=" * 60)
            
            # Step 1: 提取实体
            entities = await retrieval_service._extract_query_entities(query)
            print(f"\n提取的实体/概念: {entities}")
            
            # Step 2: 检索事实
            facts = await retrieval_service.retrieve_entity_facts(
                user_id=USER_ID,
                query=query,
                neo4j_driver=neo4j_driver
            )
            
            print(f"\n检索到 {len(facts)} 条事实:")
            for i, fact in enumerate(facts, 1):
                path_type = fact.get('path_type', 'direct')
                if path_type == 'semantic_expansion':
                    print(f"  {i}. [语义扩展] {fact['entity']} -[{fact['relation']}]-> {fact['target']}")
                else:
                    print(f"  {i}. [{fact.get('hop', 1)}-hop] {fact['entity']} -[{fact['relation']}]-> {fact['target']}")
            
            # 特别检查：是否包含"大连"相关信息
            dalian_facts = [f for f in facts if '大连' in str(f.get('target', '')) or '大连' in str(f.get('entity', ''))]
            if dalian_facts:
                print(f"\n✓ 找到大连相关事实: {len(dalian_facts)} 条")
                for f in dalian_facts:
                    print(f"  - {f['entity']} -[{f['relation']}]-> {f['target']}")
            
    finally:
        await neo4j_driver.close()


async def test_direct_neo4j_query():
    """直接查询 Neo4j 验证数据"""
    print("\n" + "=" * 60)
    print("直接查询 Neo4j 验证数据")
    print("=" * 60)
    
    neo4j_driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
    
    try:
        async with neo4j_driver.session() as session:
            # 查询所有 LIVES_IN 关系
            result = await session.run("""
                MATCH (p)-[r:LIVES_IN]->(place)
                WHERE p.user_id = $user_id
                RETURN p.name AS person, place.name AS location, r.weight AS weight
            """, user_id=USER_ID)
            
            print("\n所有 LIVES_IN 关系:")
            async for record in result:
                print(f"  {record['person']} 住在 {record['location']} (weight: {record['weight']})")
            
            # 查询昊哥的所有关系
            result2 = await session.run("""
                MATCH (p {name: '昊哥', user_id: $user_id})-[r]->(target)
                RETURN p.name AS source, type(r) AS rel, target.name AS target
            """, user_id=USER_ID)
            
            print("\n昊哥的所有关系:")
            async for record in result2:
                print(f"  {record['source']} -[{record['rel']}]-> {record['target']}")
                
    finally:
        await neo4j_driver.close()


if __name__ == "__main__":
    asyncio.run(test_direct_neo4j_query())
    asyncio.run(test_semantic_retrieval())
