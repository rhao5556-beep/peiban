"""Simple API test"""
import requests

# Get token
auth_resp = requests.post('http://localhost:8000/api/v1/auth/token', json={})
print(f"Auth status: {auth_resp.status_code}")

token_data = auth_resp.json()
token = token_data['access_token']
user_id = token_data['user_id']

print(f"User ID: {user_id}")

# Get recommendations
headers = {'Authorization': f'Bearer {token}'}
rec_resp = requests.get('http://localhost:8000/api/v1/content/recommendations', headers=headers)

print(f"\nRecommendations status: {rec_resp.status_code}")
print(f"Response: {rec_resp.text[:500]}")

if rec_resp.status_code == 200:
    recs = rec_resp.json()
    print(f"\nCount: {len(recs)}")
    for rec in recs:
        print(f"  - {rec['title']}")
