"""
检查内容推荐路由是否已注册
"""
import sys
import asyncio

async def check_routes():
    """检查路由注册状态"""
    print("="*60)
    print("内容推荐路由诊断")
    print("="*60)
    
    # 1. 检查模块导入
    print("\n1. 检查模块导入...")
    try:
        from app.api.endpoints import content_recommendation
        print("✓ content_recommendation 模块导入成功")
        print(f"  - router 对象: {hasattr(content_recommendation, 'router')}")
        if hasattr(content_recommendation, 'router'):
            routes = content_recommendation.router.routes
            print(f"  - 路由数量: {len(routes)}")
            for route in routes:
                print(f"    • {route.methods} {route.path}")
    except Exception as e:
        print(f"✗ 模块导入失败: {e}")
        return False
    
    # 2. 检查主路由器
    print("\n2. 检查主路由器...")
    try:
        from app.api.router import api_router
        print("✓ api_router 导入成功")
        all_routes = []
        for route in api_router.routes:
            if hasattr(route, 'path'):
                all_routes.append(f"{route.methods if hasattr(route, 'methods') else 'N/A'} {route.path}")
        
        print(f"  - 总路由数: {len(all_routes)}")
        
        # 查找内容推荐相关路由
        content_routes = [r for r in all_routes if 'content' in r.lower() or 'recommendation' in r.lower()]
        if content_routes:
            print(f"  - 内容推荐路由:")
            for r in content_routes:
                print(f"    • {r}")
        else:
            print("  ⚠ 未找到内容推荐路由")
            
    except Exception as e:
        print(f"✗ 主路由器检查失败: {e}")
        return False
    
    # 3. 检查数据库表
    print("\n3. 检查数据库表...")
    try:
        from app.core.database import async_session_maker
        from sqlalchemy import text
        
        async with async_session_maker() as session:
            # 检查表是否存在
            result = await session.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name LIKE 'content%' OR table_name LIKE '%recommendation%'
            """))
            tables = result.scalars().all()
            
            if tables:
                print(f"✓ 找到 {len(tables)} 个相关表:")
                for table in tables:
                    print(f"  - {table}")
            else:
                print("⚠ 未找到内容推荐相关表")
                print("  提示: 需要执行数据库迁移脚本")
                
    except Exception as e:
        print(f"⚠ 数据库检查失败: {e}")
    
    # 4. 检查 FastAPI 应用
    print("\n4. 检查 FastAPI 应用...")
    try:
        from app.main import app
        print("✓ FastAPI 应用导入成功")
        
        # 获取所有路由
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                routes.append(route.path)
        
        # 查找内容推荐路由
        content_routes = [r for r in routes if '/content' in r]
        if content_routes:
            print(f"✓ 找到 {len(content_routes)} 个内容推荐路由:")
            for r in content_routes:
                print(f"  - {r}")
        else:
            print("✗ 未找到 /content 相关路由")
            print("  可能原因: 应用未正确挂载 api_router")
            
    except Exception as e:
        print(f"✗ FastAPI 应用检查失败: {e}")
        return False
    
    print("\n" + "="*60)
    print("诊断完成")
    print("="*60)
    
    return True

if __name__ == "__main__":
    result = asyncio.run(check_routes())
    sys.exit(0 if result else 1)
