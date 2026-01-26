"""
通过 API 测试回答质量
模拟前端调用，验证语序优化效果
"""
import requests
import json
import time

API_BASE = "http://localhost:8000/api/v1"
TEST_USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"  # 使用现有测试用户

def get_auth_token():
    """获取认证 token"""
    try:
        response = requests.post(
            f"{API_BASE}/auth/token",
            json={"user_id": TEST_USER_ID}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
    except Exception as e:
        print(f"获取 token 失败: {e}")
    
    return None

def test_conversation_quality():
    """测试对话质量"""
    
    print("=" * 60)
    print("测试：谁当警察？")
    print("=" * 60)
    
    # 获取认证 token
    token = get_auth_token()
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        print(f"✅ 已获取认证 token")
    else:
        print("⚠️  未获取到 token，尝试无认证访问")
    
    # 发送消息
    url = f"{API_BASE}/conversation/message"
    payload = {
        "user_id": TEST_USER_ID,
        "session_id": "test_session_quality",
        "message": "谁当警察",
        "mode": "hybrid"
    }
    
    print(f"\n发送请求: {payload['message']}")
    print("等待回复...\n")
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            reply = result.get("reply", "")
            
            print("AI 回答:")
            print("-" * 60)
            print(reply)
            print("-" * 60)
            
            # 分析回答质量
            print("\n质量分析:")
            issues = []
            
            # 检查语序问题
            if "就是一名" in reply:
                issues.append("❌ 句子不完整：'就是一名'")
            else:
                print("✅ 无句子不完整问题")
            
            if "也这个职业" in reply:
                issues.append("❌ 语序混乱：'也这个职业'")
            else:
                print("✅ 无语序混乱问题")
            
            # 检查逻辑跳跃
            if "可能还有其他人也" in reply and "张sir" not in reply:
                issues.append("❌ 逻辑跳跃：提到其他人但没有依据")
            else:
                print("✅ 逻辑连贯")
            
            # 检查关键信息
            if "张sir" in reply or "张 sir" in reply:
                print("✅ 正确识别：张sir")
            else:
                issues.append("⚠️  未提及张sir")
            
            if "警察" in reply or "警局" in reply:
                print("✅ 正确识别：警察相关")
            else:
                issues.append("⚠️  未提及警察")
            
            # 检查句子完整性
            sentence_count = reply.count("。") + reply.count("！") + reply.count("？")
            if sentence_count >= 1:
                print(f"✅ 句子完整：包含 {sentence_count} 个完整句子")
            else:
                issues.append("⚠️  可能缺少标点")
            
            # 检查过度不确定
            uncertain_words = ["可能", "或许", "说不定", "大概"]
            uncertain_count = sum(1 for word in uncertain_words if word in reply)
            if uncertain_count > 2:
                issues.append(f"⚠️  过度使用不确定词（{uncertain_count}次）")
            else:
                print(f"✅ 语气适当：不确定词 {uncertain_count} 次")
            
            # 总结
            print("\n" + "=" * 60)
            if issues:
                print("发现问题:")
                for issue in issues:
                    print(f"  {issue}")
                return False
            else:
                print("✅ 回答质量良好！")
                return True
                
        else:
            print(f"❌ API 错误: {response.status_code}")
            print(response.text)
            return False
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False


def test_multiple_scenarios():
    """测试多个场景"""
    
    # 获取认证 token
    token = get_auth_token()
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    scenarios = [
        {
            "query": "谁当警察",
            "expected": ["张sir", "警察"],
            "name": "职业查询"
        },
        {
            "query": "谁和二丫认识",
            "expected": ["二丫"],
            "name": "关系查询"
        },
        {
            "query": "张sir做什么工作",
            "expected": ["张sir", "警察"],
            "name": "具体人物查询"
        }
    ]
    
    results = []
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n\n{'=' * 60}")
        print(f"场景 {i}/{len(scenarios)}: {scenario['name']}")
        print(f"{'=' * 60}")
        
        url = f"{API_BASE}/conversation/message"
        payload = {
            "user_id": TEST_USER_ID,
            "session_id": f"test_session_{i}",
            "message": scenario['query'],
            "mode": "hybrid"
        }
        
        print(f"问题: {scenario['query']}")
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                reply = result.get("reply", "")
                
                print(f"回答: {reply}")
                
                # 检查关键词
                found = [kw for kw in scenario['expected'] if kw in reply]
                print(f"\n关键词匹配: {len(found)}/{len(scenario['expected'])}")
                print(f"  期望: {scenario['expected']}")
                print(f"  找到: {found}")
                
                # 简单评分
                score = len(found) / len(scenario['expected']) if scenario['expected'] else 0
                
                # 检查语序
                has_issues = any(bad in reply for bad in ["就是一名", "也这个职业", "的信息我没有"])
                
                if score >= 0.5 and not has_issues:
                    print("✅ 通过")
                    results.append(True)
                else:
                    print("❌ 未通过")
                    results.append(False)
            else:
                print(f"❌ API 错误: {response.status_code}")
                results.append(False)
                
        except Exception as e:
            print(f"❌ 错误: {e}")
            results.append(False)
        
        time.sleep(1)  # 避免请求过快
    
    # 总结
    print(f"\n\n{'=' * 60}")
    print("测试总结")
    print(f"{'=' * 60}")
    passed = sum(results)
    total = len(results)
    print(f"通过: {passed}/{total}")
    print(f"成功率: {passed/total*100:.1f}%")
    
    return passed == total


if __name__ == "__main__":
    print("回答质量 API 测试")
    print("=" * 60)
    print("目标：验证语序优化后的实际效果")
    print("=" * 60)
    
    # 单个测试
    success = test_conversation_quality()
    
    # 如果单个测试通过，运行完整测试
    if success:
        print("\n\n继续运行完整测试套件...")
        test_multiple_scenarios()
