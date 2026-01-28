from app.services.proactive_service import TriggerEngine, _build_trigger_rules_from_dicts


def test_build_trigger_rules_from_dicts_accepts_valid_items():
    rules = _build_trigger_rules_from_dicts([
        {
            "trigger_type": "time",
            "condition": {"time": "09:00", "type": "morning"},
            "action": "morning_greeting",
            "priority": 9,
            "cooldown_hours": 12,
            "min_affinity_state": "acquaintance",
            "enabled": True,
        }
    ])
    assert len(rules) == 1
    assert rules[0].trigger_type.value == "time"
    assert rules[0].condition["time"] == "09:00"


def test_trigger_engine_can_override_default_rules():
    engine = TriggerEngine(db_session=None)
    original_count = len(engine.rules)
    engine.load_rules_from_config([
        {
            "trigger_type": "silence",
            "condition": {"days": 3},
            "action": "care_message",
        }
    ])
    assert len(engine.rules) == 1
    assert len(engine.rules) != original_count

