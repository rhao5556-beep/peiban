"""测试好感度 API"""
import requests

# 测试用户 token（需要替换为实际的 token）
user_id = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"

# 直接访问 API（不需要认证，因为是内部测试）
response = requests.get("http://localhost:8000/api/v1/affinity/state-mapping")
print("State mapping:", response.json())

# 尝试获取好感度（这个需要认证，可能会失败）
try:
    response = requests.get("http://localhost:8000/api/v1/affinity/")
    print("Affinity:", response.json())
except Exception as e:
    print(f"Error: {e}")
