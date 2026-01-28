"""
测试回答质量优化效果

验证：
1. 语序是否流畅
2. 逻辑是否清晰
3. 是否正确使用检索到的信息
"""
import asyncio
import sys
from app.services.conversation_service import ConversationService
from app.core.database import get_db_session

async def test_police_query():
    """测试"谁当警察"这类查询的回答质量"""
    
    print("=" * 60)
    print("测试场景：谁当警察？")
    print("=" * 60)
    
    service = ConversationService()
    
    # 模拟用户查询
    user_id = "test_user"
    session_id = "test_session"
    message = "谁当警察"
    
    print(f"\n用户问题: {message}")
    print("\n正在生成回答...")
    
    try:
        # 使用流式输出
        full_reply = ""
        async for delta in service.process_message_stream(
            user_id=user_id,
            session_id=session_id,
            message=message,
            db_session=None,  # 测试模式
            mode="hybrid"
        ):
            if delta.type == "text" and delta.content:
                full_reply += delta.content
                print(delta.content, end="", flush=True)
            elif delta.type == "done":
                print("\n")
                break
            elif delta.type == "error":
                print(f"\n错误: {delta.content}")
                return
        
        print("\n" + "=" * 60)
        print("回答质量分析:")
        print("=" * 60)
        
        # 分析回答质量
        issues = []
        
        # 检查语序问题
        if "就是一名" in full_reply or "也这个职业" in full_reply:
            issues.append("❌ 语序混乱：句子不完整")
        
        # 检查逻辑跳跃
        if "可能还有其他人也" in full_reply:
            issues.append("❌ 逻辑跳跃：突然提到其他人但没有依据")
        
        # 检查是否有明确答案
        if "张sir" in full_reply and ("警察" in full_reply or "警局" in full_reply):
            print("✅ 正确识别：张sir是警察")
        else:
            issues.append("❌ 未能正确回答问题")
        
        # 检查句子完整性
        if full_reply.count("。") >= 2:
            print("✅ 句子完整：使用了完整的句子")
        else:
            issues.append("⚠️  句子可能不够完整")
        
        # 检查是否过度猜测
        uncertain_words = ["可能", "或许", "说不定", "大概"]
        uncertain_count = sum(1 for word in uncertain_words if word in full_reply)
        if uncertain_count > 2:
            issues.append(f"⚠️  过度使用不确定词汇（{uncertain_count}次）")
        
        if issues:
            print("\n发现的问题:")
            for issue in issues:
                print(f"  {issue}")
        else:
            print("\n✅ 回答质量良好！")
        
        print("\n完整回答:")
        print(f"「{full_reply}」")
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()


async def test_multiple_queries():
    """测试多个查询场景"""
    
    test_cases = [
        {
            "query": "谁当警察",
            "expected_keywords": ["张sir", "警察"],
            "description": "职业查询"
        },
        {
            "query": "谁和二丫认识",
            "expected_keywords": ["张sir", "二丫", "朋友"],
            "description": "关系查询"
        },
        {
            "query": "谁住海边",
            "expected_keywords": ["昊哥", "大连", "海边"],
            "description": "推理查询"
        }
    ]
    
    service = ConversationService()
    
    for i, case in enumerate(test_cases, 1):
        print("\n" + "=" * 60)
        print(f"测试 {i}/{len(test_cases)}: {case['description']}")
        print("=" * 60)
        print(f"问题: {case['query']}")
        
        full_reply = ""
        try:
            async for delta in service.process_message_stream(
                user_id="test_user",
                session_id=f"test_session_{i}",
                message=case['query'],
                db_session=None,
                mode="hybrid"
            ):
                if delta.type == "text" and delta.content:
                    full_reply += delta.content
                elif delta.type == "done":
                    break
            
            print(f"回答: {full_reply}")
            
            # 检查关键词
            found_keywords = [kw for kw in case['expected_keywords'] if kw in full_reply]
            print(f"\n关键词匹配: {len(found_keywords)}/{len(case['expected_keywords'])}")
            print(f"  期望: {case['expected_keywords']}")
            print(f"  找到: {found_keywords}")
            
            # 简单的流畅度评分
            fluency_score = 0
            if "。" in full_reply:
                fluency_score += 1
            if not any(bad in full_reply for bad in ["就是一名", "也这个职业", "的信息我没有"]):
                fluency_score += 1
            if len(full_reply) > 20:
                fluency_score += 1
            
            print(f"流畅度评分: {fluency_score}/3")
            
        except Exception as e:
            print(f"错误: {e}")
        
        await asyncio.sleep(1)  # 避免请求过快


if __name__ == "__main__":
    print("回答质量测试")
    print("=" * 60)
    print("目标：验证语序优化效果")
    print("=" * 60)
    
    # 运行测试
    asyncio.run(test_police_query())
    
    # 如果需要测试多个场景
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        print("\n\n运行完整测试套件...")
        asyncio.run(test_multiple_queries())
