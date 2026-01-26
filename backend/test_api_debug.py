"""Debug API response"""
import asyncio
import httpx

async def test():
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get token
        auth = await client.post('http://localhost:8000/api/v1/auth/token', json={})
        token_data = auth.json()
        token = token_data['access_token']
        user_id = token_data['user_id']
        
        print(f'User ID: {user_id}')
        print(f'Token: {token[:20]}...')
        
        # Get recommendations
        recs = await client.get(
            'http://localhost:8000/api/v1/content/recommendations',
            headers={'Authorization': f'Bearer {token}'}
        )
        
        print(f'\nStatus: {recs.status_code}')
        print(f'Response: {recs.text}')
        
        if recs.status_code == 200:
            data = recs.json()
            print(f'\nRecommendations count: {len(data)}')
            for rec in data:
                print(f'  - {rec["title"]}')

asyncio.run(test())
