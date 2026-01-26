"""直接查询 Neo4j 调试"""
from neo4j import GraphDatabase
import os

# 连接 Neo4j
uri = "bolt://localhost:7687"
driver = GraphDatabase.driver(uri, auth=("neo4j", "neo4j_secret"))

USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"

with driver.session() as session:
    # 查询所有节点
    print("=" * 60)
    print("所有节点（不限标签）")
    print("=" * 60)
    result = session.run("""
        MATCH (n)
        WHERE n.user_id = $user_id OR n.id = $user_id
        RETURN n, labels(n) AS labels
    """, user_id=USER_ID)
    
    for record in result:
        n = record["n"]
        labels = record["labels"]
        print(f"  {labels}: id={n.get('id', '?')[:20]}, name={n.get('name', '?')}, type={n.get('type', '?')}")
    
    # 查询所有关系
    print("\n" + "=" * 60)
    print("所有关系")
    print("=" * 60)
    result = session.run("""
        MATCH (a)-[r]->(b)
        WHERE a.user_id = $user_id OR a.id = $user_id
        RETURN a.name AS src, type(r) AS rel, b.name AS tgt, r.weight AS w
    """, user_id=USER_ID)
    
    for record in result:
        print(f"  {record['src']} --[{record['rel']}]--> {record['tgt']} (w={record['w']})")
    
    # 查询 Entity 标签的节点
    print("\n" + "=" * 60)
    print("Entity 标签的节点")
    print("=" * 60)
    result = session.run("""
        MATCH (e:Entity {user_id: $user_id})
        RETURN e
    """, user_id=USER_ID)
    
    for record in result:
        e = record["e"]
        print(f"  id={e.get('id', '?')[:20]}, name={e.get('name', '?')}, type={e.get('type', '?')}")
    
    # 查询 Person 标签的节点
    print("\n" + "=" * 60)
    print("Person 标签的节点")
    print("=" * 60)
    result = session.run("""
        MATCH (p:Person {user_id: $user_id})
        RETURN p
    """, user_id=USER_ID)
    
    for record in result:
        p = record["p"]
        print(f"  id={p.get('id', '?')[:20]}, name={p.get('name', '?')}, type={p.get('type', '?')}")

    # 查询 er_ya 节点
    print("\n" + "=" * 60)
    print("查找 er_ya 节点")
    print("=" * 60)
    result = session.run("""
        MATCH (n)
        WHERE n.id = 'er_ya' OR n.name = '二丫'
        RETURN n, labels(n) AS labels
    """)
    
    for record in result:
        n = record["n"]
        labels = record["labels"]
        print(f"  {labels}: id={n.get('id', '?')}, name={n.get('name', '?')}, user_id={n.get('user_id', '?')}")

driver.close()
