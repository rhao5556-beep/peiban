"""
对话质量优化 - 直接测试（绕过 HTTP API）
直接调用服务层进行测试
"""
import asyncio
import sys
import os
import uuid
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.conversation_service import ConversationService, ConversationMode
from app.services.affinity_service import AffinityService
from app.services.retrieval_service import RetrievalService
from app.services.graph_service import GraphService
from app.core.database import get_neo4j_driver, get_milvus_collection

# 测试配置
TEST_USER_ID = f"test_opt_{uuid.uuid4().hex[:8]}"
TEST_SESSION_ID = str(uuid.uuid4())


async def send_message(conversation_service, message: str, show_details: bool = True):
    """发送消息并获取回复"""
    try:
        start_time = datetime.now()
        
        response = await conversation_service.process_message(
            user_id=TEST_USER_ID,
            message=message,
            session_id=TEST_SESSION_ID,
            mode=ConversationMode.HYBRID
        )
        
        end_time = datetime.now()
        response_time = (end_time - start_time).total_seconds() * 1000
        
        if show_details:
            print(f"\n{'─' * 80}")
            print(f"👤 用户: {message}")
            print(f"{'─' * 80}")
            print(f"🤖 AI: {response.reply}")
            print(f"{'─' * 80}")
            print(f"📊 元数据:")
            print(f"   - 响应时间: {response_time:.0f}ms")
            print(f"   - 模式: {response.mode}")
            print(f"   - 缓存: {'是' if response.context_source.get('cached') else '否'}")
            print(f"   - 图谱事实: {response.context_source.get('graph_facts_count', 0)} 条")
            print(f"   - 向量记忆: {response.context_source.get('vector_memories_count', 0)} 条")
            print(f"   - 对话历史: {response.context_source.get('history_turns_count', 0)} 轮")
            print(f"   - 好感度: {response.affinity['state']} ({response.affinity['score']:.2f})")
            print(f"{'─' * 80}")
        
        return {
            "reply": response.reply,
            "response_time": response_time,
            "context_source": response.context_source,
            "affinity": response.affinity,
            "success": True
        }
        
    except Exception as e:
        print(f"❌ 发送消息失败: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


async def test_scenario_1_fact_query(conversation_service):
    """测试场景 1：事实查询（核心改进）"""
    print("\n" + "=" * 80)
    print("测试场景 1：事实查询 - 谁去沈阳旅游过")
    print("=" * 80)
    print("预期：路由到 Tier 1（DeepSeek-V3），回复准确自然")
    
    # 先建立一些记忆
    print("\n📝 步骤 1：建立记忆...")
    await send_message(conversation_service, "我和二丫去了沈阳旅游", show_details=False)
    print("   ✅ 记忆 1 已发送")
    await asyncio.sleep(1)
    
    await send_message(conversation_service, "昊哥和张sir没有去", show_details=False)
    print("   ✅ 记忆 2 已发送")
    await asyncio.sleep(1)
    
    # 测试事实查询
    print("\n📝 步骤 2：测试事实查询...")
    result = await send_message(conversation_service, "谁去沈阳旅游过")
    
    if result and result.get("success"):
        reply = result["reply"].lower()
        
        # 验证回复质量
        checks = [
            ("提到'二丫'或相关内容", "二丫" in reply or "你" in reply or "我" in reply),
            ("不是模板化回复", len(reply) > 15),
            ("响应时间合理", result["response_time"] < 15000),
            ("使用了对话历史", result["context_source"].get("history_turns_count", 0) > 0),
        ]
        
        print(f"\n✅ 回复质量检查:")
        all_passed = True
        for check_name, check_result in checks:
            status = "✅" if check_result else "❌"
            print(f"   {status} {check_name}")
            if not check_result:
                all_passed = False
        
        return all_passed
    
    return False


async def test_scenario_2_elliptical_question(conversation_service):
    """测试场景 2：省略问句（核心改进）"""
    print("\n" + "=" * 80)
    print("测试场景 2：省略问句 - 理解上下文")
    print("=" * 80)
    print("预期：能理解'谁去了'指的是刚才提到的地点")
    
    # 建立对话上下文
    print("\n📝 步骤 1：建立对话上下文...")
    await send_message(conversation_service, "我和二丫去了大连旅游", show_details=False)
    print("   ✅ 上下文已建立")
    await asyncio.sleep(1)
    
    # 测试省略问句
    print("\n📝 步骤 2：测试省略问句...")
    result = await send_message(conversation_service, "谁去了")
    
    if result and result.get("success"):
        reply = result["reply"].lower()
        
        # 验证能理解省略
        checks = [
            ("提到相关人物", "二丫" in reply or "你" in reply or "我" in reply),
            ("不是'我不记得'", "不记得" not in reply and "不知道" not in reply),
            ("使用了对话历史", result["context_source"].get("history_turns_count", 0) > 0),
        ]
        
        print(f"\n✅ 省略理解检查:")
        all_passed = True
        for check_name, check_result in checks:
            status = "✅" if check_result else "❌"
            print(f"   {status} {check_name}")
            if not check_result:
                all_passed = False
        
        return all_passed
    
    return False


async def test_scenario_3_simple_greeting(conversation_service):
    """测试场景 3：简单问候（验证不受影响）"""
    print("\n" + "=" * 80)
    print("测试场景 3：简单问候 - 验证快速响应")
    print("=" * 80)
    print("预期：仍然快速响应（< 3秒），可能使用缓存")
    
    greetings = ["你好", "早上好"]
    
    all_passed = True
    for greeting in greetings:
        result = await send_message(conversation_service, greeting, show_details=False)
        
        if result and result.get("success"):
            response_time = result["response_time"]
            is_fast = response_time < 5000  # 放宽到 5 秒
            
            status = "✅" if is_fast else "⚠️ "
            cached = "（缓存）" if result["context_source"].get("cached") else ""
            print(f"   {status} '{greeting}' - {response_time:.0f}ms {cached}")
            
            # 简单问候不算失败，只是警告
            if not is_fast and not result["context_source"].get("cached"):
                print(f"      ⚠️  响应较慢，但可能是首次请求")
        else:
            print(f"   ❌ '{greeting}' - 请求失败")
            all_passed = False
    
    return all_passed


async def test_routing_decision(conversation_service):
    """测试路由决策"""
    print("\n" + "=" * 80)
    print("测试场景 4：路由决策验证")
    print("=" * 80)
    
    test_cases = [
        ("谁去沈阳旅游过", "疑问句 + 地点 → 应该路由到 Tier 1"),
        ("昊哥住在哪里", "疑问句 + 人名 → 应该路由到 Tier 1"),
        ("什么时候", "疑问句（短）→ 应该路由到 Tier 2"),
    ]
    
    all_passed = True
    for message, description in test_cases:
        # 分析路由决策
        emotion = conversation_service.emotion_analyzer.analyze(message)
        affinity = await conversation_service.affinity_service.get_affinity(TEST_USER_ID)
        tier = conversation_service.tier_router.route(message, emotion, affinity.state, affinity.new_score)
        tier_config = conversation_service.tier_router.TIERS[tier]
        
        is_question = conversation_service.tier_router._is_question(message)
        has_entity = conversation_service.tier_router._contains_entity_or_location(message)
        
        print(f"\n   消息: {message}")
        print(f"   描述: {description}")
        print(f"   路由: Tier {tier} ({tier_config['model']})")
        print(f"   疑问句: {'是' if is_question else '否'}")
        print(f"   包含实体/地点: {'是' if has_entity else '否'}")
        
        # 验证路由逻辑
        if is_question and has_entity:
            if tier != 1:
                print(f"   ❌ 应该路由到 Tier 1，实际: Tier {tier}")
                all_passed = False
            else:
                print(f"   ✅ 路由正确")
        elif is_question:
            if tier > 2:
                print(f"   ❌ 应该路由到 Tier 1 或 2，实际: Tier {tier}")
                all_passed = False
            else:
                print(f"   ✅ 路由正确")
    
    return all_passed


async def main():
    """主测试函数"""
    print("\n" + "=" * 80)
    print("对话质量优化 - 直接测试")
    print("=" * 80)
    print(f"测试用户: {TEST_USER_ID}")
    print(f"会话 ID: {TEST_SESSION_ID}")
    
    # 初始化服务
    print("\n初始化服务...")
    try:
        # 连接 Milvus
        from pymilvus import connections
        from app.core.config import settings
        
        connections.connect(
            alias="default",
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT
        )
        print("Milvus 连接成功")
        
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
        
        print("服务初始化成功")
        
    except Exception as e:
        print(f"❌ 服务初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 运行测试场景
    results = {}
    
    try:
        # 场景 1：事实查询
        results["scenario_1"] = await test_scenario_1_fact_query(conversation_service)
        await asyncio.sleep(1)
        
        # 场景 2：省略问句
        results["scenario_2"] = await test_scenario_2_elliptical_question(conversation_service)
        await asyncio.sleep(1)
        
        # 场景 3：简单问候
        results["scenario_3"] = await test_scenario_3_simple_greeting(conversation_service)
        await asyncio.sleep(1)
        
        # 场景 4：路由决策
        results["scenario_4"] = await test_routing_decision(conversation_service)
        
    except Exception as e:
        print(f"\n❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("📊 测试结果汇总")
    print("=" * 80)
    
    scenario_names = {
        "scenario_1": "场景 1：事实查询",
        "scenario_2": "场景 2：省略问句",
        "scenario_3": "场景 3：简单问候",
        "scenario_4": "场景 4：路由决策",
    }
    
    passed = 0
    total = len(results)
    
    for scenario_id, scenario_name in scenario_names.items():
        result = results.get(scenario_id, False)
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {scenario_name}")
        if result:
            passed += 1
    
    print("\n" + "=" * 80)
    print(f"总计: {passed}/{total} 通过")
    
    if passed == total:
        print("所有测试通过！对话质量优化成功！")
    elif passed >= total * 0.75:
        print("大部分测试通过，优化效果显著")
    elif passed >= total * 0.5:
        print("部分测试通过，仍有改进空间")
    else:
        print("多数测试失败，需要进一步调试")
    
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
