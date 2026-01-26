"""清理测试数据，准备重新测试"""
from neo4j import GraphDatabase

uri = "bolt://localhost:7687"
driver = GraphDatabase.driver(uri, auth=("neo4j", "neo4j_secret"))

USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"

with driver.session() as session:
    # 删除该用户的所有关系和节点
    print("清理用户数据...")
    
    # 删除所有关系
    result = session.run("""
        MATCH (u:User {id: $user_id})-[r]->()
        DELETE r
        RETURN count(r) AS deleted
    """, user_id=USER_ID)
    print(f"  删除 User 出边: {result.single()['deleted']}")
    
    # 删除用户的实体节点的关系
    result = session.run("""
        MATCH (e {user_id: $user_id})-[r]-()
        DELETE r
        RETURN count(r) AS deleted
    """, user_id=USER_ID)
    print(f"  删除实体关系: {result.single()['deleted']}")
    
    # 删除用户的实体节点
    result = session.run("""
        MATCH (e {user_id: $user_id})
        WHERE NOT e:User
        DELETE e
        RETURN count(e) AS deleted
    """, user_id=USER_ID)
    print(f"  删除实体节点: {result.single()['deleted']}")
    
    # 保留 User 节点
    print("✅ 清理完成，保留 User 节点")
    
    # 验证
    result = session.run("""
        MATCH (n)
        WHERE n.user_id = $user_id OR n.id = $user_id
        RETURN count(n) AS count
    """, user_id=USER_ID)
    print(f"  剩余节点数: {result.single()['count']}")

driver.close()
