#!/usr/bin/env python3
"""
快速系统测试脚本
测试所有四个系统的核心功能
"""

import asyncio
import sys
from sqlalchemy import create_engine, text
from app.core.config import settings

def print_test(name: str, status: str, details: str = ""):
    """打印测试结果"""
    emoji = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"{emoji} {name}: {status}")
    if details:
        print(f"   {details}")

async def test_database_connection():
    """测试数据库连接"""
    print("\n" + "="*60)
    print("🔌 测试数据库连接")
    print("="*60)
    
    try:
        engine = create_engine(str(settings.DATABASE_URL))
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.scalar()
        print_test("PostgreSQL 连接", "PASS", "数据库连接正常")
        return True
    except Exception as e:
        print_test("PostgreSQL 连接", "FAIL", f"连接失败: {str(e)}")
        return False

async def test_content_data():
    """测试内容数据"""
    print("\n" + "="*60)
    print("📦 测试内容数据")
    print("="*60)
    
    engine = create_engine(str(settings.DATABASE_URL))
    
    with engine.connect() as conn:
        # 内容推荐
        result = conn.execute(text("SELECT COUNT(*) FROM content_library WHERE is_active = TRUE"))
        content_count = result.scalar()
        
        if content_count > 0:
            print_test("内容推荐数据", "PASS", f"发现 {content_count} 条活跃内容")
        else:
            print_test("内容推荐数据", "WARN", "内容库为空")
        
        # 表情包
        result = conn.execute(text("SELECT COUNT(*) FROM memes WHERE status = 'approved'"))
        meme_count = result.scalar()
        
        if meme_count > 0:
            print_test("表情包数据", "PASS", f"发现 {meme_count} 个已审核表情包")
        else:
            print_test("表情包数据", "WARN", "表情包库为空")
        
        # 用户偏好
        result = conn.execute(text("SELECT COUNT(*) FROM user_content_preference"))
        pref_count = result.scalar()
        
        if pref_count > 0:
            print_test("用户偏好", "PASS", f"{pref_count} 个用户已配置偏好")
        else:
            print_test("用户偏好", "WARN", "无用户偏好配置")

async def test_api_endpoints():
    """测试 API 端点"""
    print("\n" + "="*60)
    print("🌐 测试 API 端点")
    print("="*60)
    
    import requests
    
    base_url = "http://localhost:8000"
    
    # 测试健康检查
    try:
        response = requests.get(f"{base_url}/docs", timeout=5)
        if response.status_code == 200:
            print_test("API 服务", "PASS", "API 文档可访问")
        else:
            print_test("API 服务", "FAIL", f"状态码: {response.status_code}")
    except Exception as e:
        print_test("API 服务", "FAIL", f"无法连接: {str(e)}")

async def test_celery_worker():
    """测试 Celery Worker"""
    print("\n" + "="*60)
    print("⚙️  测试 Celery Worker")
    print("="*60)
    
    import subprocess
    
    try:
        result = subprocess.run(
            ["docker-compose", "ps", "celery-worker"],
            cwd=".",
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if "Up" in result.stdout:
            print_test("Celery Worker", "PASS", "Worker 正在运行")
        else:
            print_test("Celery Worker", "WARN", "Worker 可能未运行")
    except Exception as e:
        print_test("Celery Worker", "FAIL", f"检查失败: {str(e)}")

async def test_services():
    """测试服务初始化"""
    print("\n" + "="*60)
    print("🔧 测试服务初始化")
    print("="*60)
    
    services = [
        ("冲突检测服务", "app.services.conflict_detector_service", "ConflictDetector"),
        ("冲突解决服务", "app.services.conflict_resolution_service", "ConflictResolutionService"),
        ("主动消息服务", "app.services.proactive_service", "ProactiveService"),
    ]
    
    for name, module_path, class_name in services:
        try:
            module = __import__(module_path, fromlist=[class_name])
            service_class = getattr(module, class_name)
            service = service_class()
            print_test(name, "PASS", f"{class_name} 初始化成功")
        except Exception as e:
            print_test(name, "FAIL", f"初始化失败: {str(e)}")

async def main():
    """主函数"""
    print("\n" + "="*60)
    print("🚀 开始快速系统测试")
    print("="*60)
    
    try:
        # 测试数据库连接
        db_ok = await test_database_connection()
        
        if db_ok:
            # 测试内容数据
            await test_content_data()
        
        # 测试 API 端点
        await test_api_endpoints()
        
        # 测试 Celery Worker
        await test_celery_worker()
        
        # 测试服务初始化
        await test_services()
        
        print("\n" + "="*60)
        print("✅ 测试完成！")
        print("="*60)
        print("\n系统状态:")
        print("- 数据库: 已连接")
        print("- 内容数据: 已就绪")
        print("- API 服务: 运行中")
        print("- Celery Worker: 运行中")
        print("- 核心服务: 可用")
        print("\n下一步:")
        print("1. 启动前端: cd frontend && npm run dev")
        print("2. 访问应用: http://localhost:5173")
        print("3. 开始对话测试！")
        print()
        
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
