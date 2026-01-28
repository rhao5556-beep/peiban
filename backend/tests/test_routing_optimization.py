"""
测试路由优化 - 验证疑问句路由到强模型
"""
import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.conversation_service import TierRouter, EmotionAnalyzer


def test_routing_rules():
    """测试路由规则"""
    router = TierRouter()
    emotion_analyzer = EmotionAnalyzer()
    
    # 测试用例
    test_cases = [
        # (消息, 预期Tier, 描述)
        ("谁去沈阳旅游过", 1, "疑问句 + 地点 -> Tier 1"),
        ("昊哥住在哪里", 1, "疑问句 + 人名 -> Tier 1"),
        ("什么时候去的", 2, "疑问句（短）-> Tier 2"),
        ("你好", 3, "简单问候 -> Tier 3"),
        ("早上好", 3, "简单问候 -> Tier 3"),
        ("谢谢", 3, "简单问候 -> Tier 3"),
        ("我今天心情不好", 2, "中等长度 -> Tier 2"),
        ("我今天去了公园，看到了很多花，心情特别好，想和你分享一下", 2, "长消息 + 中等情感 -> Tier 2"),
    ]
    
    print("=" * 80)
    print("路由优化测试")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for message, expected_tier, description in test_cases:
        emotion = emotion_analyzer.analyze(message)
        affinity_state = "friend"  # 默认好感度状态
        
        tier = router.route(message, emotion, affinity_state)
        
        status = "✅ PASS" if tier == expected_tier else "❌ FAIL"
        if tier == expected_tier:
            passed += 1
        else:
            failed += 1
        
        print(f"\n{status}")
        print(f"  消息: {message}")
        print(f"  描述: {description}")
        print(f"  预期: Tier {expected_tier}")
        print(f"  实际: Tier {tier}")
        
        # 获取路由解释
        explanation = router.get_routing_explanation(message, emotion, affinity_state)
        print(f"  因素: {explanation['factors']}")
    
    print("\n" + "=" * 80)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 80)
    
    return failed == 0


def test_helper_methods():
    """测试辅助方法"""
    router = TierRouter()
    
    print("\n" + "=" * 80)
    print("辅助方法测试")
    print("=" * 80)
    
    # 测试 _is_question
    question_tests = [
        ("谁去沈阳旅游过", True),
        ("什么时候", True),
        ("你好吗", True),
        ("你好", False),
        ("我今天很开心", False),
    ]
    
    print("\n_is_question() 测试:")
    for message, expected in question_tests:
        result = router._is_question(message)
        status = "✅" if result == expected else "❌"
        print(f"  {status} '{message}' -> {result} (预期: {expected})")
    
    # 测试 _contains_entity_or_location
    entity_tests = [
        ("昊哥住在大连", True),
        ("我去过沈阳", True),
        ("二丫是我表妹", True),
        ("今天天气不错", False),
        ("我很开心", False),
    ]
    
    print("\n_contains_entity_or_location() 测试:")
    for message, expected in entity_tests:
        result = router._contains_entity_or_location(message)
        status = "✅" if result == expected else "❌"
        print(f"  {status} '{message}' -> {result} (预期: {expected})")


if __name__ == "__main__":
    print("\n开始测试路由优化...\n")
    
    # 测试辅助方法
    test_helper_methods()
    
    # 测试路由规则
    success = test_routing_rules()
    
    if success:
        print("\n✅ 所有测试通过！路由优化已成功实施。")
        sys.exit(0)
    else:
        print("\n❌ 部分测试失败，请检查路由逻辑。")
        sys.exit(1)
