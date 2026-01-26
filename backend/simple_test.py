"""简单测试 - 验证后端是否返回不同的回复"""
import asyncio
import sys
sys.path.insert(0, '.')

from neo4j import AsyncGraphDatabase
from pymilvus import connections, Collection

from app.services.conversation_service import ConversationService, ConversationMode
from app.services.affinity_service import AffinityService
from app.services.retrieval_service import RetrievalService
from app.services.graph_service import GraphService

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "neo4j_secret"
MILVUS_HOST = "localhost"
MILVUS_PORT = 19530
USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"


async def main():
    # 初始化
    neo4j_driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)
    milvus_collection = Collection("memories")
    milvus_collection.load()
    
    graph_service = GraphService(neo4j_driver=neo4j_driver)
    retrieval_service = RetrievalService(milvus_client=milvus_collection, graph_service=graph_service)
    affinity_service = AffinityService()
    conversation_service = ConversationService(
        affinity_service=affinity_service,
        retrieval_service=retrieval_service,
        graph_service=graph_service
    )
    
    # 测试 3 个不同的输入
    tests = [
        "谁住在海边",
        "我认识的人谁住在海边",
        "你好"
    ]
    
    print("=" * 60)
    print("测试：后端是否对不同输入返回不同回复")
    print("=" * 60)
    
    replies = []
    for query in tests:
        response = await conversation_service.process_message(
            user_id=USER_ID,
            message=query,
            session_id=f"test-{query[:5]}",
            mode=ConversationMode.GRAPH_ONLY
        )
        replies.append(response.reply)
        print(f"\n输入: {query}")
        print(f"回复: {response.reply[:100]}...")
    
    # 检查是否所有回复都相同
    if len(set(replies)) == 1:
        print("\n❌ 问题确认：所有回复都相同！")
        print(f"相同的回复: {replies[0]}")
    else:
        print(f"\n✓ 正常：{len(set(replies))} 个不同的回复")
    
    await neo4j_driver.close()
    connections.disconnect("default")


if __name__ == "__main__":
    asyncio.run(main())
