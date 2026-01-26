#!/usr/bin/env python3
"""
用户切换工具 - 查看和切换用户
"""

import asyncio
from sqlalchemy import create_engine, text
from app.core.config import settings

def list_users():
    """列出所有用户及其记忆数量"""
    print("\n" + "="*80)
    print("📋 用户列表")
    print("="*80)
    
    engine = create_engine(str(settings.DATABASE_URL))
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                m.user_id,
                u.created_at as user_created,
                COUNT(*) as memory_count,
                MAX(m.created_at) as last_memory
            FROM memories m
            JOIN users u ON m.user_id = u.id
            GROUP BY m.user_id, u.created_at
            ORDER BY last_memory DESC
        """))
        
        users = result.fetchall()
        
        if not users:
            print("❌ 没有找到用户")
            return
        
        print(f"\n找到 {len(users)} 个用户:\n")
        
        for i, user in enumerate(users, 1):
            user_id, created, count, last = user
            print(f"{i}. 用户 ID: {user_id}")
            print(f"   创建时间: {created}")
            print(f"   记忆数量: {count}")
            print(f"   最后记忆: {last}")
            print()
        
        print("="*80)
        print("\n💡 如何切换到这个用户:")
        print("\n在浏览器控制台 (F12) 执行:")
        print(f"\nlocalStorage.setItem('affinity_user_id', '{users[0][0]}');")
        print("location.reload();")
        print()

if __name__ == "__main__":
    list_users()
