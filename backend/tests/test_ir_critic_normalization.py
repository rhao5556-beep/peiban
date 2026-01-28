from app.services.ir_critic_service import critique_ir


def test_ir_critic_dedupes_by_normalized_entity_id_and_name():
    res = critique_ir(
        entities=[
            {"id": "user", "name": "我", "type": "Person", "is_user": True, "confidence": 1.0},
            {"id": "Alice", "name": "Alice", "type": "Person", "confidence": 0.9},
            {"id": "alice ", "name": " alice  ", "type": "Person", "confidence": 0.9},
        ],
        relations=[],
        strict_mode=False,
    )
    assert len([e for e in res.entities if e.get("id") != "user"]) == 1
    assert res.stats["filtered_duplicate_entities"] >= 1


def test_ir_critic_dedupes_relations_by_normalized_key():
    res = critique_ir(
        entities=[
            {"id": "user", "name": "我", "type": "Person", "is_user": True, "confidence": 1.0},
            {"id": "Alice", "name": "Alice", "type": "Person", "confidence": 0.9},
            {"id": "足球", "name": "足球", "type": "Preference", "confidence": 0.9},
        ],
        relations=[
            {"source": "user", "target": "Alice", "type": "friend_of", "confidence": 0.9},
            {"source": "USER", "target": "alice ", "type": "FRIEND_OF", "confidence": 0.9},
        ],
        strict_mode=False,
    )
    assert len(res.relations) == 1
    assert res.stats["filtered_duplicate_relations"] >= 1

