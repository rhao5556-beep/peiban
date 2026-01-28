"""
测试内容推荐偏好设置的完整流程
验证时间字段转换和所有字段的保存
"""
import requests
import json

API_BASE = "http://localhost:8000/api/v1"
USER_ID = "6e7ac151-100a-4427-a6ee-a5ac5b3c745e"

def test_content_preference_workflow():
    """测试完整的偏好设置工作流"""
    
    # 1. 获取 Token
    print("1️⃣ 获取认证 Token...")
    token_resp = requests.post(f"{API_BASE}/auth/token", json={"user_id": USER_ID})
    assert token_resp.status_code == 200, f"Token 获取失败: {token_resp.status_code}"
    token = token_resp.json()["access_token"]
    print(f"✅ Token: {token[:20]}...")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 2. 获取当前偏好
    print("\n2️⃣ 获取当前偏好设置...")
    get_resp = requests.get(f"{API_BASE}/content/preference", headers=headers)
    assert get_resp.status_code == 200, f"获取偏好失败: {get_resp.status_code}"
    current = get_resp.json()
    print(f"✅ 当前设置: {json.dumps(current, indent=2, ensure_ascii=False)}")
    
    # 3. 测试场景 1: 启用推荐 + 设置所有字段
    print("\n3️⃣ 测试场景 1: 启用推荐并设置所有字段...")
    update_data = {
        "content_recommendation_enabled": True,
        "max_daily_recommendations": 5,
        "preferred_sources": ["bilibili", "zhihu", "weibo", "rss"],
        "excluded_topics": ["politics", "sports"],
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00"
    }
    update_resp = requests.put(f"{API_BASE}/content/preference", headers=headers, json=update_data)
    assert update_resp.status_code == 200, f"更新失败: {update_resp.status_code} - {update_resp.text}"
    updated = update_resp.json()
    print(f"✅ 更新成功: {json.dumps(updated, indent=2, ensure_ascii=False)}")
    
    # 验证字段
    assert updated["content_recommendation_enabled"] == True
    assert updated["max_daily_recommendations"] == 5
    assert set(updated["preferred_sources"]) == set(["bilibili", "zhihu", "weibo", "rss"])
    assert set(updated["excluded_topics"]) == set(["politics", "sports"])
    assert updated["quiet_hours_start"] == "22:00:00"
    assert updated["quiet_hours_end"] == "08:00:00"
    print("✅ 所有字段验证通过")
    
    # 4. 测试场景 2: 只更新部分字段
    print("\n4️⃣ 测试场景 2: 只更新每日推荐数量...")
    partial_update = {
        "max_daily_recommendations": 3
    }
    partial_resp = requests.put(f"{API_BASE}/content/preference", headers=headers, json=partial_update)
    assert partial_resp.status_code == 200, f"部分更新失败: {partial_resp.status_code}"
    partial_result = partial_resp.json()
    assert partial_result["max_daily_recommendations"] == 3
    assert partial_result["content_recommendation_enabled"] == True  # 其他字段保持不变
    print(f"✅ 部分更新成功，其他字段保持不变")
    
    # 5. 测试场景 3: 关闭推荐
    print("\n5️⃣ 测试场景 3: 关闭推荐...")
    disable_update = {
        "content_recommendation_enabled": False
    }
    disable_resp = requests.put(f"{API_BASE}/content/preference", headers=headers, json=disable_update)
    assert disable_resp.status_code == 200, f"关闭推荐失败: {disable_resp.status_code}"
    disabled = disable_resp.json()
    assert disabled["content_recommendation_enabled"] == False
    print(f"✅ 推荐已关闭")
    
    # 6. 测试场景 4: 边界时间值
    print("\n6️⃣ 测试场景 4: 边界时间值 (00:00 和 23:59)...")
    edge_time_update = {
        "quiet_hours_start": "00:00",
        "quiet_hours_end": "23:59"
    }
    edge_resp = requests.put(f"{API_BASE}/content/preference", headers=headers, json=edge_time_update)
    assert edge_resp.status_code == 200, f"边界时间更新失败: {edge_resp.status_code}"
    edge_result = edge_resp.json()
    assert edge_result["quiet_hours_start"] == "00:00:00"
    assert edge_result["quiet_hours_end"] == "23:59:00"
    print(f"✅ 边界时间值处理正确")
    
    print("\n" + "="*60)
    print("🎉 所有测试通过！内容推荐偏好设置功能正常工作")
    print("="*60)

if __name__ == "__main__":
    try:
        test_content_preference_workflow()
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
