#!/usr/bin/env python3
"""
诊断 LoCoMo 评测失败的根本原因
"""
import asyncio
import sys
from pathlib import Path

# 添加 backend 到路径
BACKEND_DIR = Path(__file__).parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import get_db
from app.services.graph_service import GraphService
from app.services.retrieval_service import RetrievalService
from sqlalchemy import text


async def diagnose():
    """诊断系统状态"""
    print("=" * 60)
    print("LoCoMo 评测失败诊断")
    print("=" * 60)
    
    # 1. 检查 PostgreSQL 记忆数量
    print("\n[1] 检查 PostgreSQL 记忆存储...")
    async for db in get_db():
        result = await db.execute(text("SELECT COUNT(*) FROM memories"))
        memory_count = result.scalar()
        print(f"   总记忆数: {memory_count}")
        
        result = await db.execute(text("""
            SELECT status, COUNT(*) 
            FROM memories 
            GROUP BY status
        """))
        for row in result:
            print(f"   - {row[0]}: {row[1]}")
        
        # 检查最近的记忆
        result = await db.execute(text("""
            SELECT id, content, status, created_at 
            FROM memories 
            ORDER BY created_at DESC 
            LIMIT 5
        """))
        print("\n   最近 5 条记忆:")
        for row in result:
            print(f"   - [{row[2]}] {row[1][:50]}... ({row[3]})")
        break
    
    # 2. 检查 Neo4j 图谱
    print("\n[2] 检查 Neo4j 图谱...")
    node_count = 0
    rel_count = 0
    try:
        from neo4j import AsyncGraphDatabase
        from app.core.config import settings
        
        driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
        
        async with driver.session() as session:
            # 检查节点数量
            result = await session.run("MATCH (n) RETURN count(n) as count")
            record = await result.single()
            node_count = record["count"] if record else 0
            print(f"   总节点数: {node_count}")
            
            # 检查关系数量
            result = await session.run("MATCH ()-[r]->() RETURN count(r) as count")
            record = await result.single()
            rel_count = record["count"] if record else 0
            print(f"   总关系数: {rel_count}")
            
            # 检查实体类型分布
            result = await session.run("""
                MATCH (n:Entity)
                RETURN n.entity_type as type, count(n) as count
                ORDER BY count DESC
                LIMIT 10
            """)
            print("\n   实体类型分布:")
            async for record in result:
                print(f"   - {record['type']}: {record['count']}")
        
        await driver.close()
            
    except Exception as e:
        print(f"   ❌ Neo4j 连接失败: {e}")
    
    # 3. 检查 Outbox 状态
    print("\n[3] 检查 Outbox 事件处理...")
    async for db in get_db():
        result = await db.execute(text("""
            SELECT status, COUNT(*) 
            FROM outbox_events 
            GROUP BY status
        """))
        print("   Outbox 事件状态:")
        for row in result:
            print(f"   - {row[0]}: {row[1]}")
        
        # 检查待处理事件
        result = await db.execute(text("""
            SELECT COUNT(*) 
            FROM outbox_events 
            WHERE status = 'pending'
        """))
        pending = result.scalar()
        if pending > 0:
            print(f"   ⚠️  有 {pending} 个待处理事件！")
        
        # 检查失败事件
        result = await db.execute(text("""
            SELECT COUNT(*) 
            FROM outbox_events 
            WHERE status = 'failed'
        """))
        failed = result.scalar()
        if failed > 0:
            print(f"   ❌ 有 {failed} 个失败事件！")
            
            # 查看失败原因
            result = await db.execute(text("""
                SELECT error_message, COUNT(*) 
                FROM outbox_events 
                WHERE status = 'failed'
                GROUP BY error_message
                LIMIT 5
            """))
            print("\n   失败原因:")
            for row in result:
                print(f"   - {row[0]}: {row[1]} 次")
        break
    
    # 4. 测试检索功能
    print("\n[4] 测试检索功能...")
    
    test_queries = [
        "Caroline 的性别认同是什么？",
        "Melanie 什么时候跑了慈善跑？",
        "Caroline 研究了什么？"
    ]
    
    retrieval_success = 0
    for query in test_queries:
        print(f"\n   查询: {query}")
        try:
            retrieval_service = RetrievalService()
            results, facts = await retrieval_service.hybrid_retrieve(
                user_id="test_user",
                query=query,
                top_k=5,
                affinity_score=0.5,
                mode="hybrid"
            )
            print(f"   检索到 {len(results)} 条记忆结果")
            if results:
                print(f"   - 第一条: {results[0].content[:50]}...")
                retrieval_success += 1
            else:
                print("   ❌ 未检索到任何结果！")
        except Exception as e:
            print(f"   ❌ 检索失败: {e}")
    
    # 5. 诊断结论
    print("\n" + "=" * 60)
    print("诊断结论")
    print("=" * 60)
    
    if memory_count == 0:
        print("❌ 致命问题: PostgreSQL 中没有记忆！")
        print("   → 记忆存储流程完全失败")
    elif node_count == 0:
        print("❌ 致命问题: Neo4j 中没有节点！")
        print("   → Outbox 处理失败或 Neo4j 同步失败")
    elif pending > 1000:
        print(f"❌ 严重问题: 大量 Outbox 事件待处理 ({pending} 个)")
        print("   → Celery worker 可能未运行或处理太慢")
        print(f"   → {pending / memory_count * 100:.1f}% 的记忆未同步到图谱")
    elif failed > 50:
        print("❌ 严重问题: 大量 Outbox 事件失败")
        print("   → 需要检查失败原因并修复")
    elif retrieval_success == 0:
        print("⚠️  检索问题: 记忆已存储但检索不到")
        print("   → 检索策略或相似度计算有问题")
    else:
        print("✅ 系统基本正常，但仍有优化空间")
    
    print("\n建议:")
    print("1. 检查 Celery worker 是否运行: docker ps | grep celery")
    print("2. 手动处理积压事件: python backend/app/worker/tasks/outbox.py")
    print("3. 检查 Neo4j 和 Milvus 连接")
    print("4. 运行 resync_memories_to_neo4j.py 重新同步")
    print("5. 检查实体提取是否正常工作")


if __name__ == "__main__":
    asyncio.run(diagnose())
