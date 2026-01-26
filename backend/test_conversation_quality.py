"""
测试对话质量优化 - 端到端测试
"""
import asyncio
import sys
import os
import uuid

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.conversation_service import ConversationService, ConversationMode
from app.services.affinity_service import AffinityService
from app.services.retrieval_service import RetrievalService
from app.services.graph_service import GraphService
from app.core.database import get_neo4j_driver


async def test_question_routing():
    """测试疑问句路由到强模型"""
    print("\n" + "=" * 80)
    print("测试：疑问句路由优化")
    print("=" * 80)
    
    # 初始化服务
    neo4j_driver = get_neo4j_driver()
    graph_service = GraphService(neo4j_driver=neo4j_driver)
    conversation_service = ConversationService(graph_service=graph_service)
    
    # 测试用户
    test_user_id = "test_user_routing_" + str(uuid.uuid4())[:8]
    session_id = str(uuid.uuid4())
    
    # 测试消息
    test_messages = [
        "谁去沈阳旅游过",
        "昊哥住在哪里",
        "什么时候去的",
    ]
    
    for message in test_messages:
        print(f"\n{'─' * 80}")
        print(f"用户消息: {message}")
        print(f"{'─' * 80}")
        
        try:
            # 分析路由决策
            emotion = conversation_service.emotion_analyzer.analyze(message)
            affinity = await conversation_service.affinity_service.get_affinity(test_user_id)
            tier = conversation_service.tier_router.route(message, emotion, affinity.state, affinity.new_score)
            tier_config = conversation_service.tier_router.TIERS[tier]
            
            print(f"✅ 路由决策:")
            print(f"   - Tier: {tier}")
            print(f"   - 模型: {tier_config['model']}")
            print(f"   - 好感度: {affinity.state} ({affinity.new_score:.2f})")
            print(f"   - 情感: {emotion.get('primary_emotion')} (valence={emotion.get('valence', 0):.2f})")
            
            # 验证疑问句路由到 Tier 1 或 Tier 2
            if conversation_service.tier_router._is_question(message):
                if conversation_service.tier_router._contains_entity_or_location(message):
                    assert tier == 1, f"疑问句 + 实体/地点应该路由到 Tier 1，实际: Tier {tier}"
                    print(f"   ✅ 疑问句 + 实体/地点 -> Tier 1 (正确)")
                else:
                    assert tier <= 2, f"疑问句应该路由到 Tier 1 或 2，实际: Tier {tier}"
                    print(f"   ✅ 疑问句 -> Tier {tier} (正确)")
            
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("✅ 疑问句路由测试完成")
    print("=" * 80)


async def test_prompt_improvement():
    """测试 Prompt 改进（允许使用最近对话中的事实）"""
    print("\n" + "=" * 80)
    print("测试：Prompt 改进（短期记忆使用）")
    print("=" * 80)
    
    # 初始化服务
    neo4j_driver = get_neo4j_driver()
    graph_service = GraphService(neo4j_driver=neo4j_driver)
    conversation_service = ConversationService(graph_service=graph_service)
    
    # 构建测试 Prompt
    test_message = "谁去了"
    test_memories = []
    
    # 模拟好感度和情感
    class MockAffinity:
        new_score = 0.6
        state = "friend"
    
    affinity = MockAffinity()
    emotion = {"primary_emotion": "neutral", "valence": 0.0}
    
    # 模拟对话历史（包含事实）
    conversation_history = [
        {"role": "user", "content": "我和二丫去了沈阳旅游"},
        {"role": "assistant", "content": "听起来很有趣！沈阳有什么好玩的地方吗？"},
        {"role": "user", "content": "我们去了故宫和张氏帅府"},
    ]
    
    # 构建 Prompt
    prompt = conversation_service._build_prompt(
        message=test_message,
        memories=test_memories,
        affinity=affinity,
        emotion=emotion,
        entity_facts=[],
        conversation_history=conversation_history,
        mode=ConversationMode.HYBRID
    )
    
    print(f"\n生成的 Prompt:")
    print("─" * 80)
    print(prompt)
    print("─" * 80)
    
    # 验证 Prompt 包含关键内容
    checks = [
        ("短期记忆", "短期记忆" in prompt or "对话历史" in prompt),
        ("允许使用最近事实", "最近3轮" in prompt or "刚刚明确提到" in prompt),
        ("示例说明", "例如" in prompt or "示例" in prompt),
    ]
    
    print(f"\nPrompt 检查:")
    all_passed = True
    for check_name, check_result in checks:
        status = "✅" if check_result else "❌"
        print(f"  {status} {check_name}: {check_result}")
        if not check_result:
            all_passed = False
    
    if all_passed:
        print("\n✅ Prompt 改进验证通过")
    else:
        print("\n⚠️  部分 Prompt 检查未通过")
    
    print("=" * 80)


async def main():
    """主测试函数"""
    print("\n" + "=" * 80)
    print("对话质量优化 - 端到端测试")
    print("=" * 80)
    
    try:
        # 测试 1: 路由优化
        await test_question_routing()
        
        # 测试 2: Prompt 改进
        await test_prompt_improvement()
        
        print("\n" + "=" * 80)
        print("✅ 所有测试完成")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
