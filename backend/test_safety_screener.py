"""
简单测试脚本：验证SafetyScreenerService功能

测试各种场景：
1. 安全内容（应该通过）
2. 暴力内容（应该拒绝）
3. 色情内容（应该拒绝）
4. 政治敏感内容（应该拒绝）
5. 版权问题（应该标记为不确定）
6. 灾难嘲讽（应该拒绝）
"""
import asyncio
from uuid import uuid4
from datetime import datetime

# 模拟Meme对象
class MockMeme:
    def __init__(self, text_description: str):
        self.id = uuid4()
        self.text_description = text_description
        self.image_url = None
        self.source_platform = "weibo"
        self.category = "humor"
        self.content_hash = "test_hash"
        self.popularity_score = 50.0
        self.trend_score = 0.0
        self.trend_level = "emerging"
        self.safety_status = "pending"
        self.status = "candidate"
        self.first_seen_at = datetime.utcnow()
        self.last_updated_at = datetime.utcnow()
        self.usage_count = 0


async def test_safety_screener():
    """测试安全筛选服务"""
    from app.services.safety_screener_service import SafetyScreenerService
    
    screener = SafetyScreenerService()
    
    # 测试用例
    test_cases = [
        {
            "name": "安全内容",
            "text": "今天天气真好，yyds 永远的神！",
            "expected": "approved"
        },
        {
            "name": "暴力内容",
            "text": "这个人该杀，血腥暴力",
            "expected": "rejected"
        },
        {
            "name": "色情内容",
            "text": "约炮一夜情，色情淫秽",
            "expected": "rejected"
        },
        {
            "name": "政治敏感",
            "text": "六四天安门事件，法轮功",
            "expected": "rejected"
        },
        {
            "name": "歧视内容",
            "text": "黑鬼尼哥，支那小日本",
            "expected": "rejected"
        },
        {
            "name": "地区冲突",
            "text": "台独港独，武统台湾",
            "expected": "rejected"
        },
        {
            "name": "版权问题",
            "text": "迪士尼盗版资源免费下载",
            "expected": "flagged"  # 不确定，需人工审核
        },
        {
            "name": "灾难嘲讽",
            "text": "汶川地震笑话，新冠笑话",
            "expected": "rejected"
        },
        {
            "name": "弱势群体",
            "text": "残废瘸子，智障笑话",
            "expected": "rejected"
        },
        {
            "name": "表情符号（安全）",
            "text": "😂😂😂 笑死我了",
            "expected": "approved"
        }
    ]
    
    print("=" * 80)
    print("SafetyScreenerService 测试")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for i, test_case in enumerate(test_cases, 1):
        meme = MockMeme(test_case["text"])
        result = await screener.screen_meme(meme)
        
        status_match = result.overall_status == test_case["expected"]
        status_icon = "✓" if status_match else "✗"
        
        print(f"\n测试 {i}: {test_case['name']}")
        print(f"  文本: {test_case['text']}")
        print(f"  预期: {test_case['expected']}")
        print(f"  实际: {result.overall_status}")
        print(f"  结果: {status_icon}")
        
        # 显示详细检查结果
        if result.overall_status != "approved":
            print(f"  详情:")
            if result.content_safety.status.value != "passed":
                print(f"    - 内容安全: {result.content_safety.status.value}")
                print(f"      原因: {result.content_safety.reason}")
                print(f"      匹配: {result.content_safety.matched_keywords}")
            if result.cultural_sensitivity.status.value != "passed":
                print(f"    - 文化敏感性: {result.cultural_sensitivity.status.value}")
                print(f"      原因: {result.cultural_sensitivity.reason}")
                print(f"      匹配: {result.cultural_sensitivity.matched_keywords}")
            if result.legal_compliance.status.value != "passed":
                print(f"    - 法律合规: {result.legal_compliance.status.value}")
                print(f"      原因: {result.legal_compliance.reason}")
                print(f"      匹配: {result.legal_compliance.matched_keywords}")
            if result.ethical_boundaries.status.value != "passed":
                print(f"    - 伦理边界: {result.ethical_boundaries.status.value}")
                print(f"      原因: {result.ethical_boundaries.reason}")
                print(f"      匹配: {result.ethical_boundaries.matched_keywords}")
        
        if status_match:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"测试结果: {passed}/{len(test_cases)} 通过")
    if failed > 0:
        print(f"失败: {failed} 个测试")
    else:
        print("所有测试通过！✓")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_safety_screener())
