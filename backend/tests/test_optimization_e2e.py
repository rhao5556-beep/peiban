"""
对话质量优化 - 端到端测试
模拟真实用户对话场景
"""
import asyncio
import sys
import os
import uuid
import httpx
import json
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# API 配置
API_BASE_URL = "http://localhost:8000/api/v1"
TEST_USER_ID = f"test_optimization_{uuid.uuid4().hex[:8]}"
TEST_SESSION_ID = str(uuid.uuid4())

# 测试用户 Token（需要先注册）
TEST_TOKEN = None


async def register_test_user():
    """注册测试用户（简化版 - 使用默认测试用户）"""
    global TEST_TOKEN, TEST_USER_ID
    
    # 使用默认测试用户
    TEST_USER_ID = "test_user_001"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # 尝试登录
            response = await client.post(
                f"{API_BASE_URL}/auth/login",
                json={
                    "username": "test_user_001",
                    "password": "test123456"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                TEST_TOKEN = data.get("access_token")
                print(f"✅ 测试用户登录成功: {TEST_USER_ID}")
                return True
            
            # 如果登录失败，尝试注册
            response = await client.post(
                f"{API_BASE_URL}/auth/register",
                json={
                    "username": "test_user_001",
                    "password": "test123456",
                    "email": "test_user_001@test.com"
                }
            )
            
            if response.status_code == 200 or response.status_code == 201:
                data = response.json()
                TEST_TOKEN = data.get("access_token")
                print(f"✅ 测试用户注册成功: {TEST_USER_ID}")
                return True
            
            print(f"⚠️  认证失败，尝试无认证模式")
            # 某些端点可能不需要认证，继续测试
            return True
            
        except Exception as e:
            print(f"⚠️  认证异常: {e}，尝试无认证模式")
            return True


async def send_message(message: str, show_details: bool = True):
    """发送消息并获取回复"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            start_time = datetime.now()
            
            headers = {}
            if TEST_TOKEN:
                headers["Authorization"] = f"Bearer {TEST_TOKEN}"
            
            response = await client.post(
                f"{API_BASE_URL}/conversation/message",
                headers=headers,
                json={
                    "message": message,
                    "session_id": TEST_SESSION_ID,
                    "user_id": TEST_USER_ID  # 直接传递 user_id
                }
            )
            
            end_time = datetime.now()
            response_time = (end_time - start_time).total_seconds() * 1000
            
            if response.status_code == 200:
                data = response.json()
                reply = data.get("reply", "")
                context_source = data.get("context_source", {})
                
                if show_details:
                    print(f"\n{'─' * 80}")
                    print(f"👤 用户: {message}")
                    print(f"{'─' * 80}")
                    print(f"🤖 AI: {reply}")
                    print(f"{'─' * 80}")
                    print(f"📊 元数据:")
                    print(f"   - 响应时间: {response_time:.0f}ms")
                    print(f"   - 模式: {context_source.get('mode', 'unknown')}")
                    print(f"   - 缓存: {'是' if context_source.get('cached') else '否'}")
                    print(f"   - 图谱事实: {context_source.get('graph_facts_count', 0)} 条")
                    print(f"   - 向量记忆: {context_source.get('vector_memories_count', 0)} 条")
                    print(f"   - 对话历史: {context_source.get('history_turns_count', 0)} 轮")
                    print(f"{'─' * 80}")
                
                return {
                    "reply": reply,
                    "response_time": response_time,
                    "context_source": context_source,
                    "success": True
                }
            else:
                print(f"❌ 请求失败: {response.status_code}")
                print(f"   错误: {response.text[:200]}")
                return {"success": False, "error": response.text}
                
        except Exception as e:
            print(f"❌ 发送消息失败: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}


async def test_scenario_1_fact_query():
    """测试场景 1：事实查询（核心改进）"""
    print("\n" + "=" * 80)
    print("测试场景 1：事实查询 - 谁去沈阳旅游过")
    print("=" * 80)
    print("预期：路由到 Tier 1（DeepSeek-V3），回复准确自然")
    
    # 先建立一些记忆
    print("\n📝 步骤 1：建立记忆...")
    await send_message("我和二丫去了沈阳旅游", show_details=False)
    await asyncio.sleep(2)  # 等待记忆处理
    
    await send_message("昊哥和张sir没有去", show_details=False)
    await asyncio.sleep(2)
    
    # 测试事实查询
    print("\n📝 步骤 2：测试事实查询...")
    result = await send_message("谁去沈阳旅游过")
    
    if result and result.get("success"):
        reply = result["reply"].lower()
        
        # 验证回复质量
        checks = [
            ("提到'二丫'", "二丫" in reply or "erya" in reply),
            ("提到'我'或'你'", "我" in reply or "你" in reply),
            ("不是模板化回复", len(reply) > 20),
            ("响应时间合理", result["response_time"] < 10000),
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


async def test_scenario_2_elliptical_question():
    """测试场景 2：省略问句（核心改进）"""
    print("\n" + "=" * 80)
    print("测试场景 2：省略问句 - 理解上下文")
    print("=" * 80)
    print("预期：能理解'谁去了'指的是'谁去了沈阳'")
    
    # 建立对话上下文
    print("\n📝 步骤 1：建立对话上下文...")
    await send_message("我和二丫去了大连旅游", show_details=False)
    await asyncio.sleep(1)
    
    # 测试省略问句
    print("\n📝 步骤 2：测试省略问句...")
    result = await send_message("谁去了")
    
    if result and result.get("success"):
        reply = result["reply"].lower()
        
        # 验证能理解省略
        checks = [
            ("提到'二丫'", "二丫" in reply or "erya" in reply),
            ("提到'我'或'你'", "我" in reply or "你" in reply),
            ("提到'大连'", "大连" in reply or "dalian" in reply),
            ("不是'我不记得'", "不记得" not in reply and "不知道" not in reply),
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


async def test_scenario_3_inference_question():
    """测试场景 3：推理问句（高级功能）"""
    print("\n" + "=" * 80)
    print("测试场景 3：推理问句 - 常识推理")
    print("=" * 80)
    print("预期：能推理'大连是海边城市'")
    
    # 建立事实
    print("\n📝 步骤 1：建立事实...")
    await send_message("昊哥住在大连", show_details=False)
    await asyncio.sleep(2)
    
    # 测试推理问句
    print("\n📝 步骤 2：测试推理问句...")
    result = await send_message("谁住海边")
    
    if result and result.get("success"):
        reply = result["reply"].lower()
        
        # 验证推理能力
        checks = [
            ("提到'昊哥'", "昊哥" in reply or "haoge" in reply),
            ("提到'大连'", "大连" in reply or "dalian" in reply),
            ("展示推理", "海边" in reply or "海" in reply or "推理" in reply or "是" in reply),
        ]
        
        print(f"\n✅ 推理能力检查:")
        all_passed = True
        for check_name, check_result in checks:
            status = "✅" if check_result else "❌"
            print(f"   {status} {check_name}")
            if not check_result:
                all_passed = False
        
        return all_passed
    
    return False


async def test_scenario_4_simple_greeting():
    """测试场景 4：简单问候（验证不受影响）"""
    print("\n" + "=" * 80)
    print("测试场景 4：简单问候 - 验证快速响应")
    print("=" * 80)
    print("预期：仍然快速响应（< 2秒），路由到 Tier 3")
    
    greetings = ["你好", "早上好", "谢谢"]
    
    all_passed = True
    for greeting in greetings:
        result = await send_message(greeting, show_details=False)
        
        if result and result.get("success"):
            response_time = result["response_time"]
            is_fast = response_time < 2000
            
            status = "✅" if is_fast else "❌"
            print(f"   {status} '{greeting}' - {response_time:.0f}ms")
            
            if not is_fast:
                all_passed = False
        else:
            print(f"   ❌ '{greeting}' - 请求失败")
            all_passed = False
    
    return all_passed


async def test_scenario_5_complex_question():
    """测试场景 5：复杂问句（验证路由提升）"""
    print("\n" + "=" * 80)
    print("测试场景 5：复杂问句 - 多实体查询")
    print("=" * 80)
    print("预期：路由到 Tier 1，能处理复杂查询")
    
    # 建立多个事实
    print("\n📝 步骤 1：建立多个事实...")
    await send_message("我和二丫去了沈阳，昊哥去了大连，张sir去了丹东", show_details=False)
    await asyncio.sleep(3)
    
    # 测试复杂查询
    print("\n📝 步骤 2：测试复杂查询...")
    result = await send_message("谁去了哪些地方")
    
    if result and result.get("success"):
        reply = result["reply"].lower()
        
        # 验证能处理多实体
        checks = [
            ("提到多个人名", sum([name in reply for name in ["二丫", "昊哥", "张sir"]]) >= 2),
            ("提到多个地点", sum([place in reply for place in ["沈阳", "大连", "丹东"]]) >= 2),
            ("回复详细", len(reply) > 30),
        ]
        
        print(f"\n✅ 复杂查询检查:")
        all_passed = True
        for check_name, check_result in checks:
            status = "✅" if check_result else "❌"
            print(f"   {status} {check_name}")
            if not check_result:
                all_passed = False
        
        return all_passed
    
    return False


async def main():
    """主测试函数"""
    print("\n" + "=" * 80)
    print("🚀 对话质量优化 - 端到端测试")
    print("=" * 80)
    print(f"测试用户: {TEST_USER_ID}")
    print(f"会话 ID: {TEST_SESSION_ID}")
    
    # 注册测试用户
    if not await register_test_user():
        print("\n❌ 无法注册测试用户，测试终止")
        return
    
    # 等待服务就绪
    print("\n⏳ 等待服务就绪...")
    await asyncio.sleep(2)
    
    # 运行测试场景
    results = {}
    
    try:
        # 场景 1：事实查询
        results["scenario_1"] = await test_scenario_1_fact_query()
        await asyncio.sleep(2)
        
        # 场景 2：省略问句
        results["scenario_2"] = await test_scenario_2_elliptical_question()
        await asyncio.sleep(2)
        
        # 场景 3：推理问句
        results["scenario_3"] = await test_scenario_3_inference_question()
        await asyncio.sleep(2)
        
        # 场景 4：简单问候
        results["scenario_4"] = await test_scenario_4_simple_greeting()
        await asyncio.sleep(2)
        
        # 场景 5：复杂问句
        results["scenario_5"] = await test_scenario_5_complex_question()
        
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
        "scenario_3": "场景 3：推理问句",
        "scenario_4": "场景 4：简单问候",
        "scenario_5": "场景 5：复杂问句",
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
        print("🎉 所有测试通过！对话质量优化成功！")
    elif passed >= total * 0.6:
        print("⚠️  大部分测试通过，但仍有改进空间")
    else:
        print("❌ 多数测试失败，需要进一步调试")
    
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
