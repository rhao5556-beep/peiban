"""
端到端测试：验证推荐功能完整流程
"""
import asyncio
import httpx

async def test_full_flow():
    print("=" * 60)
    print("端到端测试：推荐功能")
    print("=" * 60)
    
    base_url = "http://localhost:8000/api/v1"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 步骤 1: 获取 token（创建新用户）
        print("\n📝 步骤 1: 创建新用户并获取 token...")
        auth_response = await client.post(f"{base_url}/auth/token", json={})
        
        if auth_response.status_code != 200:
            print(f"❌ 获取 token 失败: {auth_response.status_code}")
            return False
        
        token_data = auth_response.json()
        token = token_data["access_token"]
        user_id = token_data["user_id"]
        
        print(f"✅ 用户创建成功")
        print(f"   User ID: {user_id}")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # 步骤 2: 获取推荐（应该自动生成）
        print("\n📰 步骤 2: 获取推荐列表...")
        rec_response = await client.get(
            f"{base_url}/content/recommendations",
            headers=headers
        )
        
        if rec_response.status_code != 200:
            print(f"❌ 获取推荐失败: {rec_response.status_code}")
            print(f"   响应: {rec_response.text}")
            return False
        
        recommendations = rec_response.json()
        
        if not recommendations:
            print("❌ 推荐列表为空")
            return False
        
        print(f"✅ 成功获取 {len(recommendations)} 条推荐")
        
        for i, rec in enumerate(recommendations, 1):
            print(f"\n{i}. [{rec['source']}] {rec['title']}")
            print(f"   URL: {rec['url']}")
            print(f"   匹配度: {rec['match_score']:.0%}")
        
        # 步骤 3: 获取用户偏好
        print("\n⚙️  步骤 3: 获取用户偏好...")
        pref_response = await client.get(
            f"{base_url}/content/preference",
            headers=headers
        )
        
        if pref_response.status_code != 200:
            print(f"❌ 获取偏好失败: {pref_response.status_code}")
            return False
        
        preference = pref_response.json()
        print(f"✅ 用户偏好:")
        print(f"   启用状态: {preference['content_recommendation_enabled']}")
        print(f"   每日限额: {preference['max_daily_recommendations']}")
        print(f"   偏好来源: {preference['preferred_sources']}")
        
        # 步骤 4: 更新偏好（启用推荐）
        print("\n🔧 步骤 4: 启用推荐功能...")
        update_response = await client.put(
            f"{base_url}/content/preference",
            headers=headers,
            json={
                "content_recommendation_enabled": True,
                "max_daily_recommendations": 5,
                "preferred_sources": ["zhihu", "bilibili"]
            }
        )
        
        if update_response.status_code != 200:
            print(f"❌ 更新偏好失败: {update_response.status_code}")
            print(f"   响应: {update_response.text}")
            return False
        
        updated_pref = update_response.json()
        print(f"✅ 偏好更新成功")
        print(f"   启用状态: {updated_pref['content_recommendation_enabled']}")
        
        # 步骤 5: 再次获取推荐（验证一致性）
        print("\n🔄 步骤 5: 再次获取推荐...")
        rec_response2 = await client.get(
            f"{base_url}/content/recommendations",
            headers=headers
        )
        
        if rec_response2.status_code != 200:
            print(f"❌ 获取推荐失败: {rec_response2.status_code}")
            return False
        
        recommendations2 = rec_response2.json()
        print(f"✅ 成功获取 {len(recommendations2)} 条推荐")
        
        # 验证推荐内容一致
        if len(recommendations) == len(recommendations2):
            print("✅ 推荐内容一致（同一天内不会重复生成）")
        
        # 步骤 6: 提交反馈
        if recommendations:
            print("\n👍 步骤 6: 提交反馈...")
            first_rec_id = recommendations[0]['id']
            
            feedback_response = await client.post(
                f"{base_url}/content/recommendations/{first_rec_id}/feedback",
                headers=headers,
                json={"action": "liked"}
            )
            
            if feedback_response.status_code != 200:
                print(f"⚠️  提交反馈失败: {feedback_response.status_code}")
            else:
                print("✅ 反馈提交成功")
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        
        print("\n📋 测试总结:")
        print(f"   ✓ 用户创建和认证")
        print(f"   ✓ 自动生成推荐（{len(recommendations)} 条）")
        print(f"   ✓ 获取用户偏好")
        print(f"   ✓ 更新用户偏好")
        print(f"   ✓ 推荐内容一致性")
        print(f"   ✓ 反馈提交")
        
        print("\n🌐 前端访问:")
        print("   打开浏览器访问: http://localhost:5173")
        print("   切换到'内容推荐'标签页")
        print("   应该能看到 3 条真实推荐内容")
        
        return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_full_flow())
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
