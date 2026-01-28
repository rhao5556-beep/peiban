from app.api.endpoints.memory import generate_audit_hash, verify_audit_hash_integrity


def test_verify_audit_hash_integrity_detects_tampering():
    audit_data = {
        "audit_id": "a",
        "user_id": "u",
        "deletion_type": "memories",
        "affected_records": {"count": 1, "memory_ids": ["m1"]},
        "requested_at": "2026-01-01T00:00:00",
    }
    h = generate_audit_hash(audit_data)
    assert verify_audit_hash_integrity(audit_data, h) is True

    tampered = dict(audit_data)
    tampered["affected_records"] = {"count": 2}
    assert verify_audit_hash_integrity(tampered, h) is False

