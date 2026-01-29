import pytest


@pytest.mark.parametrize(
    "text, expected_seconds",
    [
        ("8 minutes 40 seconds", 520),
        ("8分钟40秒", 520),
        ("90分钟", 5400),
        ("1小时30分钟", 5400),
    ],
)
def test_parse_duration_seconds(text, expected_seconds):
    from app.services.temporal_normalizer import parse_duration_seconds

    assert parse_duration_seconds(text) == expected_seconds


def test_parse_date_iso_ymd():
    from app.services.temporal_normalizer import extract_dates

    dates = extract_dates("我在2023-05-07去了大连")
    assert "2023-05-07" in dates


def test_parse_date_cn_ymd():
    from app.services.temporal_normalizer import extract_dates

    dates = extract_dates("我在2023年5月7日去了大连")
    assert "2023-05-07" in dates


@pytest.mark.parametrize(
    "text, iso",
    [
        ("I went there on 9 June 2023.", "2023-06-09"),
        ("Record from August 15, 1969", "1969-08-15"),
    ],
)
def test_parse_date_english(text, iso):
    from app.services.temporal_normalizer import extract_dates

    assert iso in extract_dates(text)


def test_relative_date_cn_days_after():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.services.temporal_normalizer import extract_temporal_constraints

    anchor = datetime(2026, 1, 28, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    constraints = extract_temporal_constraints("三天后提醒我", anchor_dt=anchor, timezone="Asia/Shanghai")
    assert any(c["start"] == "2026-01-31" for c in constraints)


def test_relative_date_en_next_weekday():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.services.temporal_normalizer import extract_temporal_constraints

    anchor = datetime(2026, 1, 28, 10, 0, tzinfo=ZoneInfo("UTC"))
    constraints = extract_temporal_constraints("next Wednesday", anchor_dt=anchor, timezone="UTC")
    assert any(c["start"] == "2026-02-04" for c in constraints)


def test_quantity_chinese_number():
    from app.services.quantity_parser import extract_quantities

    got = extract_quantities("花了两百三十元")
    assert any(x["unit"] == "CNY" and x["value"] == 230.0 for x in got)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("花了300元", [{"value": 300.0, "unit": "CNY"}]),
        ("跑了3.5km", [{"value": 3.5, "unit": "km"}]),
        ("体温是37℃", [{"value": 37.0, "unit": "C"}]),
        ("涨了10%", [{"value": 10.0, "unit": "%"}]),
    ],
)
def test_extract_quantities(text, expected):
    from app.services.quantity_parser import extract_quantities

    got = extract_quantities(text)
    for e in expected:
        assert any(x["unit"] == e["unit"] and x["value"] == e["value"] for x in got)


def test_augment_ir_with_deterministic_facts():
    from app.services.structured_fact_extractor import augment_ir_with_structured_facts

    ir = {
        "entities": [
            {"id": "user", "name": "我", "type": "Person", "is_user": True, "confidence": 1.0},
            {"id": "event1", "name": "看牙", "type": "Event", "is_user": False, "confidence": 0.9},
        ],
        "relations": [
            {"source": "user", "target": "event1", "type": "RELATED_TO", "desc": "我 看牙", "weight": 0.8, "confidence": 0.8},
        ],
        "metadata": {"source": "llm", "model_version": "test", "timestamp": "t", "overall_confidence": 0.9},
    }

    out = augment_ir_with_structured_facts(ir, "我2023-05-07去看牙，花了300元，用了1小时30分钟")
    types = {e.get("type") for e in out.get("entities", [])}
    assert "TimeExpression" in types
    assert "Quantity" in types
    assert "Duration" in types
    assert any(r.get("type") == "HAPPENED_AT" for r in out.get("relations", []))
    assert any(r.get("type") == "COST" for r in out.get("relations", []))
    assert any(r.get("type") == "LASTED" for r in out.get("relations", []))


def test_augment_creates_default_event():
    from app.services.structured_fact_extractor import augment_ir_with_structured_facts

    ir = {
        "entities": [{"id": "user", "name": "我", "type": "Person", "is_user": True, "confidence": 1.0}],
        "relations": [],
        "metadata": {"source": "llm", "model_version": "test", "timestamp": "t", "overall_confidence": 0.9},
    }
    out = augment_ir_with_structured_facts(
        ir,
        "Record from August 15, 1969: it took 8 minutes 40 seconds.",
        default_event_id="event_x",
        default_event_name="bus trip",
    )
    assert any(e.get("id") == "event_x" and e.get("type") == "Event" for e in out.get("entities", []))
    assert any(r.get("source") == "event_x" and r.get("type") == "LASTED" for r in out.get("relations", []))
