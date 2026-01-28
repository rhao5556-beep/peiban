"""直接测试 API 端点"""
import requests
import json

# 1. 获取 token
print("1. 获取 token...")
try:
    response = requests.post("http://localhost:8000/api/v1/auth/token", json={})
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        token = data["access_token"]
        print(f"✓ Token: {token[:50]}...")
    else:
        print(f"❌ Error: {response.text}")
        exit(1)
except Exception as e:
    print(f"❌ Exception: {e}")
    exit(1)

# 2. 测试获取偏好设置
print("\n2. 测试 GET /api/v1/content/preference...")
try:
    response = requests.get(
        "http://localhost:8000/api/v1/content/preference",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
    
    if response.status_code == 200:
        print("✓ 成功")
    else:
        print(f"❌ 失败")
except Exception as e:
    print(f"❌ Exception: {e}")

# 3. 测试获取推荐列表
print("\n3. 测试 GET /api/v1/content/recommendations...")
try:
    response = requests.get(
        "http://localhost:8000/api/v1/content/recommendations",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
    
    if response.status_code == 200:
        print("✓ 成功")
    else:
        print(f"❌ 失败")
except Exception as e:
    print(f"❌ Exception: {e}")
