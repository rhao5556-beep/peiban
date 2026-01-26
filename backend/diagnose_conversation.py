"""诊断对话服务问题"""
import asyncio
import sys
import logging
sys.path.insert(0, '.')

# 设置日志级别为 DEBUG
logging.basicConfig(level=logging.DEBUG)

from neo4j import AsyncGraphDatabase
from pymilvus import connections, Collection

from app.services.conversation_service import ConversationService, ConversationMode
from app.services.affinity_service import AffinityService
from app.services.retrieval_service import RetrievalService
from app.services.graph_service import GraphService

# 配置
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "neo4j_secret"
MILVUS_HOST = "localhost"
MILVUS_PORT = 19530

USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"
SESSION_ID = "test-diagnose-session"


async def test_conversation():
    """测试对话服务"""
    print("=" * 60)
    print("诊断对话服务")
    print("=" * 60)
    
    # 初始化连接
    neo4j_driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
    
    # 连接 Milvus
    connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)
    milvus_collection = Collection("memories")
    milvus_collection.load()
    
    # 初始化服务
    graph_service = GraphService(neo4j_driver=neo4j_driver)
    retrieval_service = RetrievalService(
        milvus_client=milvus_collection,
        graph_service=graph_service
    )
    affinity_service = AffinityService()
    
    conversation_service = ConversationService(
        affinity_service=affinity_service,
        retrieval_service=retrieval_service,
        graph_service=graph_service
    )
    
    # 测试不同的查询
    test_queries = [
        "你好",
        "谁住在海边",
        "我认识的人谁住在海边",
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"测试查询: {query}")
        print("=" * 60)
        
        try:
            response = await conversation_service.process_message(
                user_id=USER_ID,
                message=query,
                session_id=SESSION_ID,
                mode=ConversationMode.GRAPH_ONLY
            )
            
            print(f"\nAI 回复: {response.reply}")
            print(f"响应时间: {response.response_time_ms:.0f}ms")
            print(f"上下文来源: {response.context_source}")
            
        except Exception as e:
            print(f"\n错误: {e}")
            import traceback
            traceback.print_exc()
    
    await neo4j_driver.close()
    connections.disconnect("default")


if __name__ == "__main__":
    asyncio.run(test_conversation())
