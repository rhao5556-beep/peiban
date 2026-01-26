"""
诊断前端问题：
1. 检查后端API是否正常
2. 检查推荐内容是否有URL
3. 检查记忆图谱数据
4. 检查好感度数据
"""
import asyncio
import httpx
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def diagnose():
    print("=" * 60)
    print("前端问题诊断")
    print("=" * 60)
    
    # 1. 获取Token
    print("\n1. 获取认证Token...")
    async with httpx.AsyncClient() as client:
        response = await client.post("http://localhost:8000/api/v1/auth/token", json={})
        if response.status_code == 200:
            data = response.json()
            token = data["access_token"]
            user_id = data["user_id"]
            print(f"   ✅ Token获取成功")
            print(f"   User ID: {user_id}")
        else:
            print(f"   ❌ Token获取失败: {response.status_code}")
            return
    
    # 2. 检查推荐内容
    print("\n2. 检查推荐内容...")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/api/v1/content/recommendations",
            headers=headers
        )
        if response.status_code == 200:
            recommendations = response.json()
            print(f"   ✅ 推荐内容获取成功: {len(recommendations)} 条")
            
            if recommendations:
                for i, rec in enumerate(recommendations, 1):
                    print(f"\n   推荐 {i}:")
                    print(f"      标题: {rec['title']}")
                    print(f"      URL: {rec['url']}")
                    print(f"      来源: {rec['source']}")
                    
                    if not rec['url']:
                        print(f"      ⚠️  URL为空！")
            else:
                print("   ⚠️  没有推荐内容")
        else:
            print(f"   ❌ 推荐内容获取失败: {response.status_code}")
            print(f"   响应: {response.text}")
    
    # 3. 检查记忆图谱
    print("\n3. 检查记忆图谱...")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/api/v1/graph/?day=30",
            headers=headers
        )
        if response.status_code == 200:
            graph_data = response.json()
            nodes = graph_data.get("nodes", [])
            edges = graph_data.get("edges", [])
            print(f"   ✅ 图谱数据获取成功")
            print(f"   节点数: {len(nodes)}")
            print(f"   边数: {len(edges)}")
            
            if nodes:
                print(f"\n   前5个节点:")
                for node in nodes[:5]:
                    print(f"      - {node.get('label', 'N/A')} ({node.get('type', 'N/A')})")
            else:
                print("   ⚠️  没有图谱节点")
        else:
            print(f"   ❌ 图谱数据获取失败: {response.status_code}")
    
    # 4. 检查好感度
    print("\n4. 检查好感度...")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/api/v1/affinity/history",
            headers=headers
        )
        if response.status_code == 200:
            affinity_history = response.json()
            print(f"   ✅ 好感度历史获取成功: {len(affinity_history)} 条记录")
            
            if affinity_history:
                latest = affinity_history[-1]
                print(f"\n   最新好感度:")
                print(f"      分数: {latest.get('new_score', 0) * 100:.1f}%")
                print(f"      触发事件: {latest.get('trigger_event', 'N/A')}")
            else:
                print("   ⚠️  没有好感度记录")
        else:
            print(f"   ❌ 好感度获取失败: {response.status_code}")
    
    # 5. 检查数据库中的记忆
    print("\n5. 检查数据库中的记忆...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT COUNT(*) as total,
                       COUNT(CASE WHEN status = 'committed' THEN 1 END) as committed,
                       COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending
                FROM memories
                WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        )
        row = result.fetchone()
        print(f"   总记忆数: {row[0]}")
        print(f"   已提交: {row[1]}")
        print(f"   待处理: {row[2]}")
        
        if row[0] == 0:
            print("   ⚠️  没有任何记忆！用户需要先与AI对话")
    
    print("\n" + "=" * 60)
    print("诊断完成！")
    print("=" * 60)
    
    # 6. 给出建议
    print("\n建议:")
    if not recommendations:
        print("- 推荐内容为空，请确保已启用内容推荐功能")
    if not nodes:
        print("- 记忆图谱为空，请先与AI进行对话以建立记忆")
    if not affinity_history:
        print("- 好感度为空，请先与AI进行对话以建立关系")

if __name__ == "__main__":
    asyncio.run(diagnose())
