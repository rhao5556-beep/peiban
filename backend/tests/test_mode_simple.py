"""
简化测试：验证 Graph-only 模式的物理隔离
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEST_USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"


async def test_mode_isolation():
    """测试模式物理隔离"""
    from pymilvus import connections
    from app.core.config import settings
    
    # 连接 Milvus
    connections.connect(alias="default", host=settings.MILVUS_HOST, port=settings.MILVUS_PORT)
    
    from app.services.conversation_service import ConversationService, ConversationMode
    from app.services.affinity_service import AffinityService
    from app.services.retrieval_service import RetrievalService
    from app.services.graph_service import GraphService
    from app.core.database import get_neo4j_driver, get_milvus_collection
    
    neo4j_driver = get_neo4j_driver()
    milvus_collection = get_milvus_collection()
    
    graph_service = GraphService(neo4j_driver=neo4j_driver)
    retrieval_service = RetrievalService(milvus_client=milvus_collection, graph_service=graph_service)
    affinity_service = AffinityService()
    
    conversation_service = ConversationService(
        affinity_service=affinity_service,
        retrieval_service=retrieval_service,
        graph_service=graph_service
    )
    
    question = "二丫来自哪里？"
    session_id = "test_session_123"
    
    print("\n=== Graph-only 模式 ===")
    response_graph = await conversation_service.process_message(
        user_id=TEST_USER_ID,
        message=question,
        session_id=session_id,
        mode=ConversationMode.GRAPH_ONLY
    )
    print(f"Mode: {response_graph.mode}")
    print(f"Context: {response_graph.context_source}")
    print(f"History turns: {response_graph.context_source['history_turns_count']}")
    print(f"Reply: {response_graph.reply[:100]}...")
    
    # 验证物理隔离
    assert response_graph.context_source["history_turns_count"] == 0, "Graph-only 不应有 history"
    print("✅ Graph-only 物理隔离验证通过")
    
    print("\n=== Hybrid 模式 ===")
    response_hybrid = await conversation_service.process_message(
        user_id=TEST_USER_ID,
        message=question,
        session_id=session_id,
        mode=ConversationMode.HYBRID
    )
    print(f"Mode: {response_hybrid.mode}")
    print(f"Context: {response_hybrid.context_source}")
    print(f"History turns: {response_hybrid.context_source['history_turns_count']}")
    print(f"Reply: {response_hybrid.reply[:100]}...")
    
    print("\n✅ 模式测试完成")


if __name__ == "__main__":
    asyncio.run(test_mode_isolation())
