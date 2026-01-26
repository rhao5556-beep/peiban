"""
模拟前端 API 调用，测试完整流程
"""
import requests
import json

API_BASE = "http://localhost:8000/api/v1"
USER_ID = "6e7ac151-100a-4427-a6ee-a5ac5b3c745e"

def test_frontend_workflow():
    """模拟前端的完整调用流程"""
    
    # 1. 获取 Token
    print("1. 获取 Token...")
    token_resp = requests.post(f"{API_BASE}/auth/token", json={"user_id": USER_ID})
    print(f"   Status: {token_resp.status_code}")
    token = token_resp.json()["access_token"]
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 2. 获取当前偏好（模拟前端加载）
    print("\n2. 获取当前偏好...")
    get_resp = requests.get(f"{API_BASE}/content/preference", headers=headers)
    print(f"   Status: {get_resp.status_code}")
    if get_resp.status_code == 200:
        current = get_resp.json()
        print(f"   当前设置: enabled={current['content_recommendation_enabled']}, daily={current['max_daily_recommendations']}")
    
    # 3. 模拟前端保存（使用前端实际发送的格式）
    print("\n3. 保存设置（模拟前端格式）...")
    
    # 前端发送的 payload 格式
    frontend_payload = {
        "content_recommendation_enabled": True,
        "preferred_sources": ["bilibili", "zhihu"],
        "max_daily_recommendations": 5,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00"
    }
    
    print(f"   Payload: {json.dumps(frontend_payload, ensure_ascii=False)}")
    
    save_resp = requests.put(
        f"{API_BASE}/content/preference",
        headers=headers,
        json=frontend_payload
    )
    
    print(f"   Status: {save_resp.status_code}")
    
    if save_resp.status_code == 200:
        result = save_resp.json()
        print(f"   ✅ 保存成功!")
        print(f"   返回: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print(f"   ❌ 保存失败!")
        print(f"   错误: {save_resp.text}")
    
    # 4. 验证保存结果
    print("\n4. 验证保存结果...")
    verify_resp = requests.get(f"{API_BASE}/content/preference", headers=headers)
    if verify_resp.status_code == 200:
        verified = verify_resp.json()
        print(f"   ✅ 验证成功: daily={verified['max_daily_recommendations']}")

if __name__ == "__main__":
    test_frontend_workflow()
