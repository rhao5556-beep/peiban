from app.services.psychoanalysis_reasoner import compute_psychoanalysis_from_record_excerpt


def test_psychoanalysis_risk_penalty():
    msg = """Below is the record excerpt. Use it as the only factual source.
>> [id 10] 1975-07-24 10:00:00 @ home: inner_thought: I worry about penalties and risks if I break the rules.

Question: What do I prioritize most when making decisions?
Answer:"""
    r = compute_psychoanalysis_from_record_excerpt(msg)
    assert r and r["kind"] == "psychoanalysis"
    assert r["answer"] == "Avoiding potential risks and penalties."
    assert r["evidence"]


def test_psychoanalysis_authority_public_challenge():
    msg = """Below is the record excerpt. Use it as the only factual source.
>> [id 11] 1975-07-24 10:00:00 @ home: background: My father is strict and I never publicly challenge his authority.

Question: What is my bottom line?
Answer:"""
    r = compute_psychoanalysis_from_record_excerpt(msg)
    assert r and r["kind"] == "psychoanalysis"
    assert "father" in r["answer"].lower()
    assert r["evidence"]


def test_psychoanalysis_refuses_without_evidence():
    assert compute_psychoanalysis_from_record_excerpt("What do I prioritize?") is None
