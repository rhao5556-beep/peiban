"""
Demo 数据生成脚本 - "小明的 30 天"

生成小明 30 天对话历史数据，用于演示和测试
"""
import json
from datetime import datetime, timedelta
import uuid

# 小明的 30 天对话剧本
XIAOMING_SCRIPT = [
    # Day 1: 初识
    {
        "day": 1,
        "messages": [
            {
                "role": "user",
                "content": "我妈妈最近身体不太好，有点担心。",
                "emotion": {"primary_emotion": "worry", "valence": -0.3},
                "entities": [
                    {"name": "妈妈", "type": "person"},
                    {"name": "健康", "type": "concern"}
                ],
                "edges": [
                    {"source": "小明", "target": "妈妈", "relation": "family", "weight": 1.0},
                    {"source": "妈妈", "target": "健康", "relation": "concern", "weight": 0.8}
                ]
            },
            {
                "role": "assistant",
                "content": "我记住了，你妈妈的健康状况让你担心。希望她早日康复。",
                "affinity_delta": 0.02
            }
        ]
    },
    
    # Day 5: 建立日常
    {
        "day": 5,
        "messages": [
            {
                "role": "user",
                "content": "今天去跑步了，感觉不错。",
                "emotion": {"primary_emotion": "happy", "valence": 0.5},
                "entities": [
                    {"name": "跑步", "type": "preference"}
                ],
                "edges": [
                    {"source": "小明", "target": "跑步", "relation": "like", "weight": 1.0}
                ]
            },
            {
                "role": "assistant",
                "content": "跑步是个好习惯！你最近心情似乎好了一些。",
                "affinity_delta": 0.03
            }
        ]
    },
    
    # Day 10: 分享更多
    {
        "day": 10,
        "messages": [
            {
                "role": "user",
                "content": "我最近在学吉他，想给妈妈弹一首歌。",
                "emotion": {"primary_emotion": "excited", "valence": 0.6},
                "entities": [
                    {"name": "吉他", "type": "preference"},
                    {"name": "音乐", "type": "preference"}
                ],
                "edges": [
                    {"source": "小明", "target": "吉他", "relation": "like", "weight": 1.0},
                    {"source": "吉他", "target": "妈妈", "relation": "concern", "weight": 0.5}
                ]
            },
            {
                "role": "assistant",
                "content": "学吉他真棒！给妈妈弹歌一定会让她很开心。你打算弹什么歌呢？",
                "affinity_delta": 0.03
            }
        ]
    },
    
    # Day 15: 回忆共同经历
    {
        "day": 15,
        "messages": [
            {
                "role": "user",
                "content": "妈妈说她好多了。",
                "emotion": {"primary_emotion": "relief", "valence": 0.7},
                "entities": [],
                "edges": [],
                "refresh_edges": [
                    {"source": "小明", "target": "妈妈", "relation": "family"}
                ]
            },
            {
                "role": "assistant",
                "content": "太好了！还记得你 2 周前说她身体不太好，我也一直挂念着。她现在恢复了，你一定松了口气吧？",
                "affinity_delta": 0.03,
                "memories_used": ["妈妈身体不好"]
            }
        ]
    },
    
    # Day 20: 深入交流
    {
        "day": 20,
        "messages": [
            {
                "role": "user",
                "content": "工作压力有点大，最近加班很多。",
                "emotion": {"primary_emotion": "stressed", "valence": -0.4},
                "entities": [
                    {"name": "工作", "type": "event"},
                    {"name": "加班", "type": "event"}
                ],
                "edges": [
                    {"source": "小明", "target": "工作", "relation": "concern", "weight": 0.7},
                    {"source": "工作", "target": "加班", "relation": "concern", "weight": 0.8}
                ]
            },
            {
                "role": "assistant",
                "content": "工作压力大确实很累。记得你之前说跑步让你感觉不错，最近还有坚持吗？运动可以帮助缓解压力。",
                "affinity_delta": 0.02,
                "memories_used": ["跑步"]
            }
        ]
    },
    
    # Day 25: 情感支持
    {
        "day": 25,
        "messages": [
            {
                "role": "user",
                "content": "今天终于把项目交付了，可以休息一下了。",
                "emotion": {"primary_emotion": "relieved", "valence": 0.6},
                "entities": [
                    {"name": "项目", "type": "event"}
                ],
                "edges": [
                    {"source": "工作", "target": "项目", "relation": "concern", "weight": 0.5}
                ]
            },
            {
                "role": "assistant",
                "content": "恭喜！之前看你加班那么辛苦，现在终于可以喘口气了。打算怎么庆祝一下？",
                "affinity_delta": 0.03,
                "memories_used": ["加班"]
            }
        ]
    },
    
    # Day 30: 关系维护
    {
        "day": 30,
        "messages": [
            {
                "role": "user",
                "content": "周末想回家看看妈妈。",
                "emotion": {"primary_emotion": "warm", "valence": 0.5},
                "entities": [],
                "edges": [],
                "refresh_edges": [
                    {"source": "小明", "target": "妈妈", "relation": "family"}
                ]
            },
            {
                "role": "assistant",
                "content": "好主意！妈妈一定很想你。上次你说想给她弹吉他，学得怎么样了？可以趁这次回家表演一下。",
                "affinity_delta": 0.03,
                "memories_used": ["妈妈", "吉他"]
            }
        ]
    }
]


def generate_sql_seed():
    """生成 SQL 种子数据"""
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    
    sql_statements = []
    
    # 创建用户
    sql_statements.append(f"""
INSERT INTO users (id, created_at, settings)
VALUES ('{user_id}', NOW() - INTERVAL '30 days', '{{"name": "小明"}}');
""")
    
    # 创建会话
    sql_statements.append(f"""
INSERT INTO sessions (id, user_id, started_at, turn_count)
VALUES ('{session_id}', '{user_id}', NOW() - INTERVAL '30 days', {len(XIAOMING_SCRIPT) * 2});
""")
    
    # 创建对话轮次
    base_time = datetime.now() - timedelta(days=30)
    affinity_score = 0.5
    
    for day_data in XIAOMING_SCRIPT:
        day = day_data["day"]
        turn_time = base_time + timedelta(days=day)
        
        for msg in day_data["messages"]:
            turn_id = str(uuid.uuid4())
            
            if msg["role"] == "user":
                emotion_json = json.dumps(msg.get("emotion", {}))
            else:
                emotion_json = "null"
                affinity_score += msg.get("affinity_delta", 0)
            
            sql_statements.append(f"""
INSERT INTO conversation_turns (id, session_id, user_id, role, content, emotion_result, affinity_at_turn, created_at)
VALUES ('{turn_id}', '{session_id}', '{user_id}', '{msg["role"]}', '{msg["content"]}', '{emotion_json}', {affinity_score}, '{turn_time.isoformat()}');
""")
    
    # 创建好感度历史
    affinity_score = 0.5
    for day_data in XIAOMING_SCRIPT:
        day = day_data["day"]
        for msg in day_data["messages"]:
            if msg["role"] == "assistant":
                delta = msg.get("affinity_delta", 0)
                old_score = affinity_score
                affinity_score += delta
                
                history_id = str(uuid.uuid4())
                signals = json.dumps({"user_initiated": True, "emotion_valence": 0.3})
                
                sql_statements.append(f"""
INSERT INTO affinity_history (id, user_id, old_score, new_score, delta, trigger_event, signals, created_at)
VALUES ('{history_id}', '{user_id}', {old_score}, {affinity_score}, {delta}, 'conversation', '{signals}', NOW() - INTERVAL '{30 - day} days');
""")
    
    return "\n".join(sql_statements)


def generate_neo4j_seed():
    """生成 Neo4j 种子数据"""
    user_id = "xiaoming"
    
    cypher_statements = []
    
    # 创建用户节点
    cypher_statements.append(f"""
CREATE (u:User {{id: '{user_id}', name: '小明', created_at: datetime()}});
""")
    
    # 收集所有实体和边
    entities = {}
    edges = []
    
    for day_data in XIAOMING_SCRIPT:
        for msg in day_data["messages"]:
            if msg["role"] == "user":
                for entity in msg.get("entities", []):
                    entities[entity["name"]] = entity["type"]
                
                for edge in msg.get("edges", []):
                    edges.append(edge)
    
    # 创建实体节点
    for name, entity_type in entities.items():
        entity_id = name.replace(" ", "_").lower()
        cypher_statements.append(f"""
CREATE (e:Entity {{
    id: '{entity_id}',
    user_id: '{user_id}',
    name: '{name}',
    type: '{entity_type}',
    mention_count: 1,
    first_mentioned_at: datetime(),
    last_mentioned_at: datetime()
}});
""")
    
    # 创建关系边
    for edge in edges:
        source_id = edge["source"].replace(" ", "_").lower()
        target_id = edge["target"].replace(" ", "_").lower()
        
        cypher_statements.append(f"""
MATCH (e1 {{id: '{source_id}'}})
MATCH (e2 {{id: '{target_id}'}})
CREATE (e1)-[:RELATES_TO {{
    relation_type: '{edge["relation"]}',
    weight: {edge["weight"]},
    decay_rate: 0.03,
    created_at: datetime(),
    updated_at: datetime()
}}]->(e2);
""")
    
    return "\n".join(cypher_statements)


if __name__ == "__main__":
    print("=== PostgreSQL Seed Data ===")
    print(generate_sql_seed())
    
    print("\n=== Neo4j Seed Data ===")
    print(generate_neo4j_seed())
