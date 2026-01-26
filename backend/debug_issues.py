"""
调试两个问题：
1. 问"谁住海边"，昊哥住大连但系统说不知道
2. "讨厌吃蛋糕"没记录，但"讨厌阴雨天"记录了
"""
import asyncio
from neo4j import GraphDatabase
from app.core.config import settings

TEST_USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"


def check_neo4j_data():
    """检查 Neo4j 中的数据"""
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    
    print("\n" + "="*60)
    print("问题1: 检查昊哥和大连的关系")
    print("="*60)
    
    with driver.session() as session:
        # 查找昊哥
        result = session.run("""
            MATCH (p {user_id: $user_id})
            WHERE p.name CONTAINS '昊' OR p.name CONTAINS '昊哥'
            RETURN p.id, p.name, p.type, labels(p) as labels
        """, user_id=TEST_USER_ID)
        
        haoge_nodes = list(result)
        print(f"\n昊哥相关节点: {len(haoge_nodes)}")
        for r in haoge_nodes:
            print(f"  - {r['p.name']} (id={r['p.id']}, type={r['p.type']}, labels={r['labels']})")
        
        # 查找大连
        result = session.run("""
            MATCH (l {user_id: $user_id})
            WHERE l.name CONTAINS '大连' OR l.name CONTAINS '海边'
            RETURN l.id, l.name, l.type, labels(l) as labels
        """, user_id=TEST_USER_ID)
        
        dalian_nodes = list(result)
        print(f"\n大连/海边相关节点: {len(dalian_nodes)}")
        for r in dalian_nodes:
            print(f"  - {r['l.name']} (id={r['l.id']}, type={r['l.type']}, labels={r['labels']})")
        
        # 查找昊哥的所有关系
        result = session.run("""
            MATCH (p {user_id: $user_id})-[r]->(t)
            WHERE p.name CONTAINS '昊' OR p.name CONTAINS '昊哥'
            RETURN p.name, type(r) as rel_type, t.name, t.type
        """, user_id=TEST_USER_ID)
        
        haoge_rels = list(result)
        print(f"\n昊哥的关系: {len(haoge_rels)}")
        for r in haoge_rels:
            print(f"  - {r['p.name']} -[{r['rel_type']}]-> {r['t.name']} ({r['t.type']})")
        
        # 反向查找：谁指向昊哥
        result = session.run("""
            MATCH (s)-[r]->(p {user_id: $user_id})
            WHERE p.name CONTAINS '昊' OR p.name CONTAINS '昊哥'
            RETURN s.name, type(r) as rel_type, p.name
        """, user_id=TEST_USER_ID)
        
        haoge_incoming = list(result)
        print(f"\n指向昊哥的关系: {len(haoge_incoming)}")
        for r in haoge_incoming:
            print(f"  - {r['s.name']} -[{r['rel_type']}]-> {r['p.name']}")
        
        # 查找 LIVES_IN 或 FROM 关系
        result = session.run("""
            MATCH (p {user_id: $user_id})-[r:LIVES_IN|FROM]->(l)
            RETURN p.name, type(r) as rel_type, l.name
        """, user_id=TEST_USER_ID)
        
        location_rels = list(result)
        print(f"\n所有居住/来自关系: {len(location_rels)}")
        for r in location_rels:
            print(f"  - {r['p.name']} -[{r['rel_type']}]-> {r['l.name']}")
    
    print("\n" + "="*60)
    print("问题2: 检查蛋糕和阴雨天的记录")
    print("="*60)
    
    with driver.session() as session:
        # 查找蛋糕相关
        result = session.run("""
            MATCH (n {user_id: $user_id})
            WHERE n.name CONTAINS '蛋糕'
            RETURN n.id, n.name, n.type, labels(n) as labels
        """, user_id=TEST_USER_ID)
        
        cake_nodes = list(result)
        print(f"\n蛋糕相关节点: {len(cake_nodes)}")
        for r in cake_nodes:
            print(f"  - {r['n.name']} (type={r['n.type']})")
        
        # 查找阴雨天相关
        result = session.run("""
            MATCH (n {user_id: $user_id})
            WHERE n.name CONTAINS '阴雨' OR n.name CONTAINS '雨天'
            RETURN n.id, n.name, n.type, labels(n) as labels
        """, user_id=TEST_USER_ID)
        
        rain_nodes = list(result)
        print(f"\n阴雨天相关节点: {len(rain_nodes)}")
        for r in rain_nodes:
            print(f"  - {r['n.name']} (type={r['n.type']})")
        
        # 查找用户的 DISLIKES 关系
        result = session.run("""
            MATCH (u:User {id: $user_id})-[r:DISLIKES]->(t)
            RETURN t.name, t.type
        """, user_id=TEST_USER_ID)
        
        dislikes = list(result)
        print(f"\n用户的 DISLIKES 关系: {len(dislikes)}")
        for r in dislikes:
            print(f"  - 讨厌 {r['t.name']} ({r['t.type']})")
    
    driver.close()


def check_outbox_events():
    """检查最近的 Outbox 事件"""
    from sqlalchemy import create_engine, text
    
    engine = create_engine(settings.DATABASE_URL)
    
    print("\n" + "="*60)
    print("检查最近的 Outbox 事件")
    print("="*60)
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT event_id, status, error_message, created_at, processed_at
            FROM outbox_events
            WHERE created_at > NOW() - INTERVAL '1 hour'
            ORDER BY created_at DESC
            LIMIT 10
        """))
        
        events = list(result)
        print(f"\n最近1小时的事件: {len(events)}")
        for e in events:
            print(f"  - {e.event_id[:8]}... status={e.status}, error={e.error_message}")


async def test_entity_extraction():
    """测试实体抽取"""
    from app.services.llm_extraction_service import extract_ir
    
    print("\n" + "="*60)
    print("测试实体抽取")
    print("="*60)
    
    test_messages = [
        "我认识的人谁住在海边 而且我讨厌吃蛋糕",
        "我讨厌阴雨天",
        "昊哥住在大连",
    ]
    
    for msg in test_messages:
        print(f"\n消息: {msg}")
        result = extract_ir(text=msg, user_id=TEST_USER_ID, context_entities=[])
        
        if result.success:
            print(f"  实体: {[e['name'] for e in result.entities]}")
            print(f"  关系: {[(r['source'], r['type'], r['target']) for r in result.relations]}")
        else:
            print(f"  抽取失败: {result.error}")


if __name__ == "__main__":
    check_neo4j_data()
    check_outbox_events()
    asyncio.run(test_entity_extraction())
