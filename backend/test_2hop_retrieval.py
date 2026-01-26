"""
测试 2-hop 检索功能
"""
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')

async def test_2hop():
    from neo4j import AsyncGraphDatabase
    from app.services.retrieval_service import RetrievalService
    from app.core.config import settings
    
    # 使用已有数据的用户
    user_id = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"
    
    # 直接创建 Neo4j driver
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    
    retrieval = RetrievalService()
    
    # 测试查询
    queries = [
        "二丫喜欢什么",
        "昊哥的妹妹是谁",
        "二丫平时接触什么运动",
    ]
    
    for query in queries:
        print(f"\n{'='*50}")
        print(f"Query: {query}")
        print("="*50)
        
        # 直接传入 neo4j driver
        facts = await retrieval.retrieve_entity_facts(
            user_id=user_id,
            query=query,
            neo4j_driver=neo4j_driver
        )
        
        if facts:
            print(f"Found {len(facts)} facts:")
            for f in facts:
                hop = f.get('hop', 1)
                if hop == 1:
                    print(f"  [1-hop] {f['entity']} --{f['relation']}--> {f['target']}")
                else:
                    path = f.get('path') or f"{f['entity']} -> {f['target']}"
                    print(f"  [2-hop] {path}")
        else:
            print("  No facts found")
    
    await neo4j_driver.close()

if __name__ == "__main__":
    asyncio.run(test_2hop())
