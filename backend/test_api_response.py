"""
测试 API 返回的推荐数据
"""
import asyncio
import httpx

async def main():
    # 先获取 token
    async with httpx.AsyncClient() as client:
        # 获取 token
        auth_response = await client.post(
            "http://localhost:8000/api/v1/auth/token",
            json={}
        )
        
        if auth_response.status_code != 200:
            print(f"❌ 获取 token 失败: {auth_response.status_code}")
            print(auth_response.text)
            return
        
        token_data = auth_response.json()
        token = token_data["access_token"]
        user_id = token_data["user_id"]
        
        print(f"✅ 获取 token 成功")
        print(f"   User ID: {user_id}")
        print(f"   Token: {token[:20]}...")
        
        # 获取推荐列表
        headers = {"Authorization": f"Bearer {token}"}
        
        rec_response = await client.get(
            "http://localhost:8000/api/v1/content/recommendations",
            headers=headers
        )
        
        print(f"\n📡 API 响应状态: {rec_response.status_code}")
        
        if rec_response.status_code == 200:
            recommendations = rec_response.json()
            print(f"✅ 成功获取推荐")
            print(f"   推荐数量: {len(recommendations)}")
            
            if recommendations:
                print("\n📰 推荐内容：")
                for i, rec in enumerate(recommendations, 1):
                    print(f"\n{i}. [{rec['source']}] {rec['title']}")
                    print(f"   URL: {rec['url']}")
                    print(f"   匹配度: {rec['match_score']:.0%}")
                    print(f"   排名: {rec['rank_position']}")
            else:
                print("\n⚠️  推荐列表为空")
        else:
            print(f"❌ 获取推荐失败")
            print(rec_response.text)

if __name__ == "__main__":
    asyncio.run(main())
