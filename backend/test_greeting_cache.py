"""
测试问候语缓存功能
"""
import asyncio
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TEST_USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"


async def test_greeting_cache():
    """测试问候语缓存"""
    from app.services.conversation_service import ConversationService, ConversationMode
    
    service = ConversationService()
    
    greetings = [
        "你好",
        "早上好",
        "晚上好",
        "嗨",
        "hi",
        "hello",
        "再见",
        "拜拜",
        "谢谢",
        "好的"
    ]
    
    print("\n" + "="*60)
    print("问候语缓存测试")
    print("="*60)
    
    for greeting in greetings:
        print(f"\n测试: '{greeting}'")
        
        # 第一次调用（可能缓存未命中）
        t0 = time.time()
        response1 = await service.process_message(
            user_id=TEST_USER_ID,
            message=greeting,
            session_id="test-session-1",
            mode=ConversationMode.HYBRID
        )
        time1 = (time.time() - t0) * 1000
        
        # 第二次调用（应该缓存命中）
        t0 = time.time()
        response2 = await service.process_message(
            user_id=TEST_USER_ID,
            message=greeting,
            session_id="test-session-2",
            mode=ConversationMode.HYBRID
        )
        time2 = (time.time() - t0) * 1000
        
        cached1 = response1.context_source.get("cached", False)
        cached2 = response2.context_source.get("cached", False)
        
        print(f"  第1次: {time1:.0f}ms (cached={cached1})")
        print(f"  第2次: {time2:.0f}ms (cached={cached2})")
        print(f"  回复: {response2.reply[:50]}...")
        
        # 验证缓存效果
        if cached2:
            if time2 < 100:
                print(f"  ✅ 缓存命中，延迟 < 100ms")
            else:
                print(f"  ⚠️  缓存命中，但延迟 {time2:.0f}ms > 100ms")
        else:
            print(f"  ❌ 缓存未命中")
    
    # 获取缓存统计
    print("\n" + "="*60)
    print("缓存统计")
    print("="*60)
    stats = await service.response_cache_service.get_cache_stats()
    print(f"  总缓存键数: {stats['total_keys']}")
    print(f"  总命中次数: {stats['total_hits']}")
    print(f"  按类型统计:")
    for msg_type, type_stats in stats.get('by_type', {}).items():
        print(f"    {msg_type}: {type_stats['keys']} keys, {type_stats['hits']} hits")


async def test_complex_query():
    """测试复杂查询（不应该被缓存）"""
    from app.services.conversation_service import ConversationService, ConversationMode
    
    service = ConversationService()
    
    complex_queries = [
        "二丫来自哪里？",
        "我的朋友都有谁？",
        "昨天我们聊了什么？"
    ]
    
    print("\n" + "="*60)
    print("复杂查询测试（不应该被缓存）")
    print("="*60)
    
    for query in complex_queries:
        print(f"\n测试: '{query}'")
        
        t0 = time.time()
        response = await service.process_message(
            user_id=TEST_USER_ID,
            message=query,
            session_id="test-session-complex",
            mode=ConversationMode.HYBRID
        )
        elapsed = (time.time() - t0) * 1000
        
        cached = response.context_source.get("cached", False)
        
        print(f"  延迟: {elapsed:.0f}ms")
        print(f"  缓存: {cached}")
        print(f"  回复: {response.reply[:100]}...")
        
        if not cached:
            print(f"  ✅ 正确：复杂查询不使用缓存")
        else:
            print(f"  ❌ 错误：复杂查询不应该被缓存")


if __name__ == "__main__":
    asyncio.run(test_greeting_cache())
    asyncio.run(test_complex_query())
