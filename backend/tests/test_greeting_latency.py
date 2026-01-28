"""
详细分析"你好啊"的延迟 - 每个环节计时
"""
import asyncio
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TEST_USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"


async def analyze_greeting_latency():
    """详细分析问候语的每个环节延迟"""
    from app.services.conversation_service import ConversationService, ConversationMode
    
    service = ConversationService()
    
    greeting = "你好啊"
    
    print("\n" + "="*70)
    print(f"详细延迟分析: '{greeting}'")
    print("="*70)
    
    timings = {}
    
    # 总计时开始
    total_start = time.time()
    
    # 1. 检查是否可缓存
    t0 = time.time()
    is_cacheable = service.response_cache_service.is_cacheable(greeting)
    timings["1. 缓存检查"] = (time.time() - t0) * 1000
    print(f"\n1. 缓存检查: {timings['1. 缓存检查']:.1f}ms")
    print(f"   可缓存: {is_cacheable}")
    
    if is_cacheable:
        # 2. 获取好感度
        t0 = time.time()
        affinity = await service.affinity_service.get_affinity(TEST_USER_ID)
        timings["2. 获取好感度"] = (time.time() - t0) * 1000
        print(f"\n2. 获取好感度: {timings['2. 获取好感度']:.1f}ms")
        print(f"   状态: {affinity.state}, 分数: {affinity.new_score:.2f}")
        
        # 3. 尝试获取缓存响应
        t0 = time.time()
        cached_response = await service.response_cache_service.get_cached_response(
            greeting, affinity.state
        )
        timings["3. 获取缓存响应"] = (time.time() - t0) * 1000
        print(f"\n3. 获取缓存响应: {timings['3. 获取缓存响应']:.1f}ms")
        print(f"   缓存命中: {cached_response is not None}")
        if cached_response:
            print(f"   响应: {cached_response[:50]}...")
            
            # 如果缓存命中，应该直接返回
            total_time = (time.time() - total_start) * 1000
            print(f"\n✅ 缓存路径总耗时: {total_time:.1f}ms")
            print("\n各环节耗时:")
            for stage, ms in timings.items():
                print(f"  {stage}: {ms:.1f}ms")
            return
    
    # 如果没有缓存命中，走完整流程
    print("\n❌ 缓存未命中，走完整流程...")
    
    # 4. 情感分析
    t0 = time.time()
    emotion = service.emotion_analyzer.analyze(greeting)
    timings["4. 情感分析"] = (time.time() - t0) * 1000
    print(f"\n4. 情感分析: {timings['4. 情感分析']:.1f}ms")
    
    # 5. 获取好感度（如果之前没获取）
    if "2. 获取好感度" not in timings:
        t0 = time.time()
        affinity = await service.affinity_service.get_affinity(TEST_USER_ID)
        timings["5. 获取好感度"] = (time.time() - t0) * 1000
        print(f"\n5. 获取好感度: {timings['5. 获取好感度']:.1f}ms")
    
    # 6. Tier 路由
    t0 = time.time()
    tier = service.tier_router.route(greeting, emotion, affinity.state, affinity.new_score)
    timings["6. Tier 路由"] = (time.time() - t0) * 1000
    print(f"\n6. Tier 路由: {timings['6. Tier 路由']:.1f}ms")
    print(f"   选择 Tier: {tier}")
    
    # 7. 并行检索
    t0 = time.time()
    import asyncio
    vector_task = asyncio.create_task(
        service.retrieval_service.hybrid_retrieve(
            TEST_USER_ID, greeting, affinity.new_score
        )
    )
    graph_task = asyncio.create_task(
        service.retrieval_service.retrieve_entity_facts(
            TEST_USER_ID, greeting, service.graph_service
        )
    )
    retrieval_result, entity_facts = await asyncio.gather(vector_task, graph_task)
    timings["7. 并行检索"] = (time.time() - t0) * 1000
    print(f"\n7. 并行检索: {timings['7. 并行检索']:.1f}ms")
    print(f"   向量结果: {len(retrieval_result.memories)} 条")
    print(f"   图谱事实: {len(entity_facts) if entity_facts else 0} 条")
    
    # 8. LLM 生成回复
    t0 = time.time()
    reply = await service._generate_reply(
        greeting, retrieval_result.memories, affinity, emotion, tier, entity_facts
    )
    timings["8. LLM 生成回复"] = (time.time() - t0) * 1000
    print(f"\n8. LLM 生成回复: {timings['8. LLM 生成回复']:.1f}ms")
    print(f"   回复: {reply[:100]}...")
    
    # 总计时
    total_time = (time.time() - total_start) * 1000
    
    print("\n" + "="*70)
    print("完整流程总耗时分析")
    print("="*70)
    print(f"\n总耗时: {total_time:.1f}ms")
    print("\n各环节耗时:")
    for stage, ms in timings.items():
        pct = ms / total_time * 100
        print(f"  {stage}: {ms:.1f}ms ({pct:.1f}%)")
    
    # 瓶颈分析
    print("\n瓶颈分析（Top 3）:")
    sorted_timings = sorted(timings.items(), key=lambda x: x[1], reverse=True)
    for stage, ms in sorted_timings[:3]:
        pct = ms / total_time * 100
        print(f"  {stage}: {ms:.1f}ms ({pct:.1f}%)")


async def test_multiple_greetings():
    """测试多次问候，看缓存是否生效"""
    from app.services.conversation_service import ConversationService, ConversationMode
    
    service = ConversationService()
    
    greetings = ["你好啊", "你好啊", "你好啊"]  # 重复3次
    
    print("\n" + "="*70)
    print("多次问候测试（验证缓存）")
    print("="*70)
    
    for i, greeting in enumerate(greetings, 1):
        print(f"\n第 {i} 次: '{greeting}'")
        
        t0 = time.time()
        response = await service.process_message(
            user_id=TEST_USER_ID,
            message=greeting,
            session_id=f"test-session-{i}",
            mode=ConversationMode.HYBRID
        )
        elapsed = (time.time() - t0) * 1000
        
        cached = response.context_source.get("cached", False)
        
        print(f"  耗时: {elapsed:.1f}ms")
        print(f"  缓存: {cached}")
        print(f"  回复: {response.reply[:50]}...")
        
        if cached and elapsed < 100:
            print(f"  ✅ 缓存命中，延迟 < 100ms")
        elif cached:
            print(f"  ⚠️  缓存命中，但延迟 {elapsed:.1f}ms > 100ms")
        else:
            print(f"  ❌ 缓存未命中")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("开始延迟分析...")
    print("="*70)
    
    asyncio.run(analyze_greeting_latency())
    asyncio.run(test_multiple_greetings())
