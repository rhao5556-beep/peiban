from app.services.evidence_reasoner import compute_answer_from_facts


def test_compute_duration():
    facts = [
        {"entity": "bus", "relation": "LASTED", "target": "520", "weight": 1.0, "hop": 0},
    ]
    r = compute_answer_from_facts("How long did it take?", facts)
    assert r and r["kind"] == "duration"
    assert r["answer"] == "8 minutes 40 seconds"


def test_compute_cost():
    facts = [
        {"entity": "dentist", "relation": "COST", "target": "300 CNY", "weight": 1.0, "hop": 0},
    ]
    r = compute_answer_from_facts("多少钱？", facts)
    assert r and r["kind"] == "cost"
    assert r["answer"] == "300 CNY"


def test_compute_when():
    facts = [
        {"entity": "trip", "relation": "HAPPENED_AT", "target": "2023-06-09", "weight": 1.0, "hop": 0},
    ]
    r = compute_answer_from_facts("When was it?", facts)
    assert r and r["kind"] == "when"
    assert r["answer"] == "2023-06-09"


def test_compute_when_range():
    facts = [
        {"entity": "trip", "relation": "HAPPENED_BETWEEN", "target": "2022-12-25..2022-12-31", "weight": 1.0, "hop": 0},
    ]
    r = compute_answer_from_facts("When was it?", facts)
    assert r and r["kind"] == "when_range"
    assert r["answer"] == "2022-12-25 to 2022-12-31"


def test_compute_year():
    facts = [
        {"entity": "trip", "relation": "HAPPENED_AT", "target": "2023-06-09", "weight": 1.0, "hop": 0},
    ]
    r = compute_answer_from_facts("What year was it?", facts)
    assert r and r["kind"] == "year"
    assert r["answer"] == "2023"


def test_compute_month():
    facts = [
        {"entity": "trip", "relation": "HAPPENED_AT", "target": "2023-01-09", "weight": 1.0, "hop": 0},
    ]
    r = compute_answer_from_facts("What month was it?", facts)
    assert r and r["kind"] == "month"
    assert r["answer"] == "January, 2023"


def test_compute_identity():
    facts = [
        {"entity": "caroline", "relation": "IS", "target": "Transgender woman", "weight": 1.0, "hop": 0},
    ]
    r = compute_answer_from_facts("Who is Caroline?", facts)
    assert r and r["kind"] == "identity"
    assert r["answer"] == "Transgender woman"


def test_compute_research():
    facts = [
        {"entity": "caroline", "relation": "RESEARCHED", "target": "Adoption agencies", "weight": 1.0, "hop": 0},
    ]
    r = compute_answer_from_facts("What did Caroline research?", facts)
    assert r and r["kind"] == "research"
    assert r["answer"] == "Adoption agencies"


def test_compute_commonality():
    facts = [
        {"entity": "jon", "relation": "SHARES", "target": "lost their jobs and decided to start their own businesses", "weight": 1.0, "hop": 0},
    ]
    r = compute_answer_from_facts("What do Jon and Gina have in common?", facts)
    assert r and r["kind"] == "common"
    assert "lost their jobs" in r["answer"]
