"""
测试脚本：验证 Graph-only 模式多跳推理 + IR Critic 过滤效果

测试目标：
1. Graph-only 模式：验证多跳推理能力（不依赖短期记忆）
2. IR Critic：验证低置信度/无效类型的过滤效果
"""
import asyncio
import json
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 测试用户 ID
TEST_USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"


async def test_graph_only_mode():
    """测试 Graph-only 模式的多跳推理"""
    print("\n" + "="*60)
    print("测试 1: Graph-only 模式多跳推理")
    print("="*60)
    
    from pymilvus import connections
    from app.core.config import settings
    
    # 初始化 Milvus 连接
    try:
        connections.connect(
            alias="default",
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT
        )
        print("Milvus 连接成功")
    except Exception as e:
        print(f"Milvus 连接: {e}")
    
    from app.services.conversation_service import ConversationService, ConversationMode
    from app.services.affinity_service import AffinityService
    from app.services.retrieval_service import RetrievalService
    from app.services.graph_service import GraphService
    from app.core.database import get_neo4j_driver, get_milvus_collection
    
    # 初始化服务
    neo4j_driver = get_neo4j_driver()
    milvus_collection = get_milvus_collection()
    
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
    
    # 测试问题（需要多跳推理）
    test_questions = [
        # 1-hop 问题
        ("二丫喜欢什么？", "1-hop: 用户 -> 二丫 -> 喜好"),
        # 2-hop 问题
        ("二丫的表妹喜欢什么？", "2-hop: 用户 -> 二丫 -> 表妹 -> 喜好"),
        # 事实性问题
        ("昊哥的妈妈是做什么的？", "2-hop: 用户 -> 昊哥 -> 妈妈 -> 职业"),
    ]
    
    session_id = f"test_graph_only_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    for question, description in test_questions:
        print(f"\n--- {description} ---")
        print(f"问题: {question}")
        
        # Graph-only 模式
        response = await conversation_service.process_message(
            user_id=TEST_USER_ID,
            message=question,
            session_id=session_id,
            mode=ConversationMode.GRAPH_ONLY
        )
        
        print(f"模式: {response.mode}")
        print(f"上下文来源: {response.context_source}")
        print(f"回复: {response.reply[:200]}...")
        print(f"响应时间: {response.response_time_ms:.0f}ms")
        
        # 验证物理隔离
        assert response.context_source["history_turns_count"] == 0, "Graph-only 模式不应有 history"
        print("✅ 物理隔离验证通过")
    
    print("\n" + "="*60)
    print("Graph-only 模式测试完成")
    print("="*60)


async def test_hybrid_mode_comparison():
    """对比 Graph-only 和 Hybrid 模式"""
    print("\n" + "="*60)
    print("测试 2: Graph-only vs Hybrid 模式对比")
    print("="*60)
    
    from pymilvus import connections
    from app.core.config import settings
    
    # 初始化 Milvus 连接
    try:
        connections.connect(
            alias="default",
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT
        )
    except Exception:
        pass
    
    from app.services.conversation_service import ConversationService, ConversationMode
    from app.services.affinity_service import AffinityService
    from app.services.retrieval_service import RetrievalService
    from app.services.graph_service import GraphService
    from app.core.database import get_neo4j_driver, get_milvus_collection
    
    # 初始化服务
    neo4j_driver = get_neo4j_driver()
    milvus_collection = get_milvus_collection()
    
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
    
    question = "二丫来自哪里？"
    session_id = f"test_compare_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Graph-only 模式
    print(f"\n问题: {question}")
    print("\n--- Graph-only 模式 ---")
    response_graph = await conversation_service.process_message(
        user_id=TEST_USER_ID,
        message=question,
        session_id=session_id,
        mode=ConversationMode.GRAPH_ONLY
    )
    print(f"上下文: {response_graph.context_source}")
    print(f"回复: {response_graph.reply}")
    
    # Hybrid 模式
    print("\n--- Hybrid 模式 ---")
    response_hybrid = await conversation_service.process_message(
        user_id=TEST_USER_ID,
        message=question,
        session_id=session_id,
        mode=ConversationMode.HYBRID
    )
    print(f"上下文: {response_hybrid.context_source}")
    print(f"回复: {response_hybrid.reply}")
    
    # 对比
    print("\n--- 对比结果 ---")
    print(f"Graph-only history_turns: {response_graph.context_source['history_turns_count']}")
    print(f"Hybrid history_turns: {response_hybrid.context_source['history_turns_count']}")
    
    assert response_graph.context_source["history_turns_count"] == 0
    print("✅ 模式隔离验证通过")


def test_ir_critic():
    """测试 IR Critic 过滤效果"""
    print("\n" + "="*60)
    print("测试 3: IR Critic 过滤效果")
    print("="*60)
    
    from app.services.ir_critic_service import critique_ir, CONFIDENCE_THRESHOLD
    
    # 构造测试数据（包含各种需要过滤的情况）
    test_entities = [
        # 正常实体
        {"id": "user", "name": "我", "type": "Person", "is_user": True, "confidence": 1.0},
        {"id": "erya", "name": "二丫", "type": "Person", "confidence": 0.9},
        {"id": "harbin", "name": "哈尔滨", "type": "Location", "confidence": 0.85},
        # 低置信度（应被过滤）
        {"id": "unknown1", "name": "某人", "type": "Person", "confidence": 0.3},
        # 无效类型（应被过滤）
        {"id": "invalid1", "name": "测试", "type": "InvalidType", "confidence": 0.9},
        # 重复实体（应被过滤）
        {"id": "erya", "name": "二丫重复", "type": "Person", "confidence": 0.8},
        # 空名称（应被过滤）
        {"id": "empty1", "name": "", "type": "Person", "confidence": 0.9},
    ]
    
    test_relations = [
        # 正常关系
        {"source": "user", "target": "erya", "type": "FRIEND_OF", "confidence": 0.9},
        {"source": "erya", "target": "harbin", "type": "FROM", "confidence": 0.85},
        # 低置信度（应被过滤）
        {"source": "user", "target": "erya", "type": "LIKES", "confidence": 0.2},
        # 无效关系类型（应被过滤）
        {"source": "user", "target": "erya", "type": "INVALID_REL", "confidence": 0.9},
        # 自环（应被过滤）
        {"source": "erya", "target": "erya", "type": "FRIEND_OF", "confidence": 0.9},
        # 目标不存在（应被过滤，因为 unknown1 被过滤了）
        {"source": "user", "target": "unknown1", "type": "FRIEND_OF", "confidence": 0.9},
        # 重复关系（应被过滤）
        {"source": "user", "target": "erya", "type": "FRIEND_OF", "confidence": 0.85},
    ]
    
    print(f"\n输入: {len(test_entities)} 实体, {len(test_relations)} 关系")
    print(f"置信度阈值: {CONFIDENCE_THRESHOLD}")
    
    # 执行 Critic
    result = critique_ir(test_entities, test_relations, strict_mode=False)
    
    print(f"\n输出: {len(result.entities)} 实体, {len(result.relations)} 关系")
    print(f"\n--- 统计信息 ---")
    for key, value in result.stats.items():
        print(f"  {key}: {value}")
    
    print(f"\n--- 保留的实体 ---")
    for ent in result.entities:
        print(f"  - {ent['name']} ({ent['type']}, conf={ent.get('confidence', 'N/A')})")
    
    print(f"\n--- 保留的关系 ---")
    for rel in result.relations:
        print(f"  - {rel['source']} -[{rel['type']}]-> {rel['target']}")
    
    print(f"\n--- 被过滤的实体 ---")
    for ent in result.filtered_entities:
        print(f"  - {ent['name']}: {ent.get('filter_reason', 'unknown')}")
    
    print(f"\n--- 被过滤的关系 ---")
    for rel in result.filtered_relations:
        print(f"  - {rel['source']}->{rel['target']}: {rel.get('filter_reason', 'unknown')}")
    
    # 验证
    assert len(result.entities) == 3, f"Expected 3 entities, got {len(result.entities)}"
    assert len(result.relations) == 2, f"Expected 2 relations, got {len(result.relations)}"
    assert result.stats["filtered_low_confidence_entities"] >= 1
    assert result.stats["filtered_invalid_type_entities"] >= 1
    assert result.stats["filtered_self_loop_relations"] >= 1
    
    print("\n✅ IR Critic 测试通过")


def test_ir_critic_strict_mode():
    """测试 IR Critic 严格模式"""
    print("\n" + "="*60)
    print("测试 4: IR Critic 严格模式 (threshold=0.7)")
    print("="*60)
    
    from app.services.ir_critic_service import critique_ir
    
    test_entities = [
        {"id": "user", "name": "我", "type": "Person", "is_user": True, "confidence": 1.0},
        {"id": "e1", "name": "实体1", "type": "Person", "confidence": 0.9},  # 保留
        {"id": "e2", "name": "实体2", "type": "Person", "confidence": 0.6},  # 严格模式过滤
        {"id": "e3", "name": "实体3", "type": "Person", "confidence": 0.75}, # 保留
    ]
    
    test_relations = [
        {"source": "user", "target": "e1", "type": "FRIEND_OF", "confidence": 0.9},
        {"source": "user", "target": "e3", "type": "FRIEND_OF", "confidence": 0.75},
    ]
    
    # 正常模式
    result_normal = critique_ir(test_entities, test_relations, strict_mode=False)
    print(f"正常模式: {len(result_normal.entities)} 实体, {len(result_normal.relations)} 关系")
    
    # 严格模式
    result_strict = critique_ir(test_entities, test_relations, strict_mode=True)
    print(f"严格模式: {len(result_strict.entities)} 实体, {len(result_strict.relations)} 关系")
    
    # 严格模式应该过滤更多
    assert len(result_strict.entities) <= len(result_normal.entities)
    print("\n✅ 严格模式测试通过")


async def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("开始测试: Graph-only 模式 + IR Critic")
    print("="*60)
    
    # 测试 IR Critic（不需要数据库连接）
    test_ir_critic()
    test_ir_critic_strict_mode()
    
    # 测试 Graph-only 模式（需要数据库连接）
    try:
        await test_graph_only_mode()
        await test_hybrid_mode_comparison()
    except Exception as e:
        print(f"\n⚠️ Graph 模式测试失败（可能是数据库未连接）: {e}")
        print("请确保 Docker 服务已启动: docker-compose up -d")
    
    print("\n" + "="*60)
    print("所有测试完成")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
