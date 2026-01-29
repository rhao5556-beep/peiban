from app.services.evidence_reasoner import compute_answer_from_record_excerpt


def test_record_excerpt_duration_from_times():
    msg = """Below is the record excerpt. Use it as the only factual source.
[id 1] 1975-07-24 14:00:00 @ hill: action: saw the bus
[id 2] 1975-07-24 14:08:40 @ red house: action: arrived

Question: How long did it take?
Answer:"""
    r = compute_answer_from_record_excerpt(msg)
    assert r and r["kind"] == "duration"
    assert r["seconds"] == 520
    assert r["answer"] == "8 minutes 40 seconds"


def test_record_excerpt_returns_none_without_excerpt():
    r = compute_answer_from_record_excerpt("What year was it?")
    assert r is None

