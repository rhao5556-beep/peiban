"""端到端测试：验证"谁住海边"语义查询能否正确回答"""
import asyncio
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
SESSION_ID = "test-seaside-session"


async def test_seaside_query():
    """测试"谁住海边"查询"""
    print("=" * 60)
    print("端到端测试：谁住海边")
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
    
    # 测试查询
    query = "我认识的人谁住在海边"
    print(f"\n查询: {query}")
    print("-" * 40)
    
    try:
        response = await conversation_service.process_message(
            user_id=USER_ID,
            message=query,
            session_id=SESSION_ID,
            mode=ConversationMode.GRAPH_ONLY
        )
        
        print(f"\nAI 回复:")
        print(response.reply)
        
        # 检查是否提到昊哥和大连
        reply = response.reply
        if "昊哥" in reply and ("大连" in reply or "海边" in reply):
            print("\n✓ 测试通过：正确识别昊哥住在大连（海边城市）")
        elif "昊哥" in reply:
            print("\n⚠ 部分通过：提到了昊哥，但可能没有完整推理")
        elif "大连" in reply:
            print("\n⚠ 部分通过：提到了大连")
        else:
            print("\n✗ 测试失败：没有正确回答")
            
        # 显示上下文来源
        print(f"\n上下文来源: {response.context_source}")
        print(f"响应时间: {response.response_time_ms:.0f}ms")
        
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await neo4j_driver.close()
        connections.disconnect("default")


if __name__ == "__main__":
    asyncio.run(test_seaside_query())
