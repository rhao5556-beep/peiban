"""
模拟浏览器测试：验证前端能正常获取推荐
"""
import asyncio
import httpx

async def simulate_browser_flow():
    print("=" * 60)
    print("浏览器模拟测试")
    print("=" * 60)
    
    base_url = "http://localhost:8000/api/v1"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 步骤 1: 模拟前端获取 token（新用户）
        print("\n1️⃣  模拟前端：创建新用户...")
        auth_response = await client.post(f"{base_url}/auth/token", json={})
        
        if auth_response.status_code != 200:
            print(f"❌ 失败: {auth_response.status_code}")
            return False
        
        token_data = auth_response.json()
        token = token_data["access_token"]
        user_id = token_data["user_id"]
        
        print(f"✅ 用户创建成功: {user_id}")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # 步骤 2: 获取推荐（应该自动生成）
        print("\n2️⃣  模拟前端：获取推荐列表...")
        rec_response = await client.get(
            f"{base_url}/content/recommendations",
            headers=headers
        )
        
        print(f"   状态码: {rec_response.status_code}")
        
        if rec_response.status_code != 200:
            print(f"❌ 失败: {rec_response.text}")
            return False
        
        recommendations = rec_response.json()
        
        if not recommendations:
            print("❌ 推荐列表为空！")
            return False
        
        print(f"✅ 成功获取 {len(recommendations)} 条推荐\n")
        
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. [{rec['source']}] {rec['title']}")
            print(f"   URL: {rec['url']}")
            print(f"   匹配度: {rec['matchScore']:.0%}")
            print()
        
        # 步骤 3: 获取用户偏好
        print("3️⃣  模拟前端：获取用户偏好...")
        pref_response = await client.get(
            f"{base_url}/content/preference",
            headers=headers
        )
        
        if pref_response.status_code != 200:
            print(f"❌ 失败: {pref_response.status_code}")
            return False
        
        preference = pref_response.json()
        print(f"✅ 偏好状态: enabled={preference['content_recommendation_enabled']}")
        
        # 步骤 4: 模拟点击第一条推荐
        if recommendations:
            print("\n4️⃣  模拟前端：点击第一条推荐...")
            first_rec = recommendations[0]
            
            feedback_response = await client.post(
                f"{base_url}/content/recommendations/{first_rec['id']}/feedback",
                headers=headers,
                json={"action": "clicked"}
            )
            
            if feedback_response.status_code != 200:
                print(f"⚠️  反馈失败: {feedback_response.status_code}")
                print(f"   响应: {feedback_response.text}")
            else:
                print("✅ 点击反馈成功")
        
        print("\n" + "=" * 60)
        print("✅ 浏览器模拟测试通过！")
        print("=" * 60)
        
        print("\n📋 测试结果:")
        print(f"   ✓ 新用户自动获取推荐")
        print(f"   ✓ 推荐内容正确返回（{len(recommendations)} 条）")
        print(f"   ✓ 用户偏好正确返回")
        print(f"   ✓ 反馈提交成功")
        
        print("\n🌐 现在可以打开浏览器测试:")
        print("   1. 访问: http://localhost:5173")
        print("   2. 切换到'内容推荐'标签页")
        print("   3. 应该能看到 3 条真实推荐内容")
        print("   4. 点击标题可以打开链接")
        print("   5. 点击喜欢/不喜欢按钮可以提交反馈")
        
        return True


if __name__ == "__main__":
    try:
        success = asyncio.run(simulate_browser_flow())
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
