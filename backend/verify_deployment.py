#!/usr/bin/env python3
"""
部署验证脚本
快速验证所有四个系统是否正常工作
"""

import asyncio
import sys
from sqlalchemy import create_engine, text
from app.core.config import settings

def print_status(system: str, status: str, details: str = ""):
    """打印系统状态"""
    emoji = "✅" if status == "OK" else "❌" if status == "FAIL" else "⚠️"
    print(f"{emoji} {system}: {status}")
    if details:
        print(f"   {details}")

async def verify_database_tables():
    """验证数据库表是否存在"""
    print("\n" + "="*60)
    print("📊 验证数据库表")
    print("="*60)
    
    engine = create_engine(str(settings.DATABASE_URL))
    
    tables_to_check = [
        # 冲突解决系统
        ("conflict_records", "冲突解决系统"),
        
        # 内容推荐系统
        ("content_library", "内容推荐系统 - 内容库"),
        ("user_content_preference", "内容推荐系统 - 用户偏好"),
        ("recommendation_history", "内容推荐系统 - 推荐历史"),
        
        # 主动消息系统
        ("proactive_messages", "主动消息系统 - 消息表"),
        ("user_proactive_preferences", "主动消息系统 - 用户偏好"),
        
        # 表情包系统
        ("memes", "表情包系统 - 表情包库"),
        ("meme_usage_history", "表情包系统 - 使用历史"),
        ("user_meme_preferences", "表情包系统 - 用户偏好"),
    ]
    
    with engine.connect() as conn:
        for table_name, description in tables_to_check:
            try:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count = result.scalar()
                print_status(description, "OK", f"表 '{table_name}' 存在，包含 {count} 条记录")
            except Exception as e:
                print_status(description, "FAIL", f"表 '{table_name}' 不存在或查询失败: {str(e)}")

async def verify_content_aggregation():
    """验证内容聚合是否成功"""
    print("\n" + "="*60)
    print("📦 验证内容聚合")
    print("="*60)
    
    engine = create_engine(str(settings.DATABASE_URL))
    
    with engine.connect() as conn:
        # 检查内容推荐
        result = conn.execute(text("SELECT COUNT(*) FROM content_library WHERE is_active = TRUE"))
        content_count = result.scalar()
        
        if content_count > 0:
            print_status("内容推荐聚合", "OK", f"已聚合 {content_count} 条内容")
        else:
            print_status("内容推荐聚合", "WARN", "内容库为空，请运行聚合任务")
        
        # 检查表情包
        result = conn.execute(text("SELECT COUNT(*) FROM memes WHERE status = 'approved'"))
        meme_count = result.scalar()
        
        if meme_count > 0:
            print_status("表情包聚合", "OK", f"已聚合 {meme_count} 个表情包")
        else:
            print_status("表情包聚合", "WARN", "表情包库为空，请运行聚合任务")

async def verify_user_preferences():
    """验证用户偏好设置"""
    print("\n" + "="*60)
    print("⚙️  验证用户偏好设置")
    print("="*60)
    
    engine = create_engine(str(settings.DATABASE_URL))
    
    with engine.connect() as conn:
        # 检查内容推荐偏好
        result = conn.execute(text("SELECT COUNT(*) FROM user_content_preference"))
        pref_count = result.scalar()
        print_status("内容推荐偏好", "OK" if pref_count > 0 else "WARN", 
                    f"{pref_count} 个用户已配置偏好")
        
        # 检查主动消息偏好
        result = conn.execute(text("SELECT COUNT(*) FROM user_proactive_preferences"))
        pref_count = result.scalar()
        print_status("主动消息偏好", "OK" if pref_count > 0 else "WARN", 
                    f"{pref_count} 个用户已配置偏好")
        
        # 检查表情包偏好
        result = conn.execute(text("SELECT COUNT(*) FROM user_meme_preferences"))
        pref_count = result.scalar()
        print_status("表情包偏好", "OK" if pref_count > 0 else "WARN", 
                    f"{pref_count} 个用户已配置偏好")

async def verify_services():
    """验证服务是否可以初始化"""
    print("\n" + "="*60)
    print("🔧 验证服务初始化")
    print("="*60)
    
    try:
        from app.services.conflict_detector_service import ConflictDetector
        detector = ConflictDetector()
        print_status("冲突检测服务", "OK", "ConflictDetector 初始化成功")
    except Exception as e:
        print_status("冲突检测服务", "FAIL", f"初始化失败: {str(e)}")
    
    try:
        from app.services.conflict_resolution_service import ConflictResolutionService
        service = ConflictResolutionService()
        print_status("冲突解决服务", "OK", "ConflictResolutionService 初始化成功")
    except Exception as e:
        print_status("冲突解决服务", "FAIL", f"初始化失败: {str(e)}")
    
    try:
        from app.services.content_recommendation_service import ContentRecommendationService
        service = ContentRecommendationService()
        print_status("内容推荐服务", "OK", "ContentRecommendationService 初始化成功")
    except Exception as e:
        print_status("内容推荐服务", "FAIL", f"初始化失败: {str(e)}")
    
    try:
        from app.services.proactive_service import ProactiveService
        service = ProactiveService()
        print_status("主动消息服务", "OK", "ProactiveService 初始化成功")
    except Exception as e:
        print_status("主动消息服务", "FAIL", f"初始化失败: {str(e)}")
    
    try:
        from app.services.usage_decision_engine_service import UsageDecisionEngine
        engine = UsageDecisionEngine()
        print_status("表情包决策引擎", "OK", "UsageDecisionEngine 初始化成功")
    except Exception as e:
        print_status("表情包决策引擎", "FAIL", f"初始化失败: {str(e)}")

async def main():
    """主函数"""
    print("\n" + "="*60)
    print("🚀 开始验证部署")
    print("="*60)
    
    try:
        await verify_database_tables()
        await verify_content_aggregation()
        await verify_user_preferences()
        await verify_services()
        
        print("\n" + "="*60)
        print("✅ 验证完成！")
        print("="*60)
        print("\n下一步:")
        print("1. 启动前端: cd frontend && npm run dev")
        print("2. 访问应用: http://localhost:5173")
        print("3. 查看详细报告: DEPLOYMENT_COMPLETE.md")
        print()
        
    except Exception as e:
        print(f"\n❌ 验证失败: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
