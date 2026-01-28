"""测试并行检索优化"""
import asyncio
import time
import sys
sys.path.insert(0, '.')

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
SESSION_ID = "test-parallel-session"


async def test_parallel_retrieval():
    """测试并行检索性能"""
    print("=" * 60)
    print("测试并行检索优化")
    print("=" * 60)
    
    # 初始化连接
    neo4j_driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
    
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
    
    # 测试查询
    query = "谁住在海边"
    print(f"\n查询: {query}")
    print("-" * 40)
    
    # 测试并行检索
    start_time = time.time()
    
    response = await conversation_service.process_message(
        user_id=USER_ID,
        message=query,
        session_id=SESSION_ID,
        mode=ConversationMode.GRAPH_ONLY
    )
    
    total_time = (time.time() - start_time) * 1000
    
    print(f"\nAI 回复: {response.reply[:100]}...")
    print(f"\n上下文来源: {response.context_source}")
    print(f"总响应时间: {total_time:.0f}ms")
    print(f"服务端响应时间: {response.response_time_ms:.0f}ms")
    
    # 验证并行检索是否生效
    print("\n" + "=" * 60)
    print("验证并行检索")
    print("=" * 60)
    
    # 单独测试向量检索时间
    start = time.time()
    affinity = await affinity_service.get_affinity(USER_ID)
    vector_result = await retrieval_service.hybrid_retrieve(
        USER_ID, query, affinity.new_score
    )
    vector_time = (time.time() - start) * 1000
    print(f"向量检索时间: {vector_time:.0f}ms")
    
    # 单独测试图谱检索时间
    start = time.time()
    graph_facts = await retrieval_service.retrieve_entity_facts(
        USER_ID, query, graph_service
    )
    graph_time = (time.time() - start) * 1000
    print(f"图谱检索时间: {graph_time:.0f}ms")
    
    # 并行检索时间（理论值）
    parallel_time = max(vector_time, graph_time)
    serial_time = vector_time + graph_time
    saved_time = serial_time - parallel_time
    
    print(f"\n串行总时间: {serial_time:.0f}ms")
    print(f"并行总时间: {parallel_time:.0f}ms (理论值)")
    print(f"节省时间: {saved_time:.0f}ms ({saved_time/serial_time*100:.1f}%)")
    
    await neo4j_driver.close()
    connections.disconnect("default")


if __name__ == "__main__":
    asyncio.run(test_parallel_retrieval())
