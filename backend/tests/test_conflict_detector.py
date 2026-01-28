from datetime import datetime, timedelta

from app.services.conflict_detector_service import ConflictDetector


def test_conflict_detector_detects_same_topic_opposites():
    detector = ConflictDetector()
    now = datetime.utcnow()
    conflicts = detector.detect_conflicts(
        [
            {"id": "1", "content": "我喜欢茶", "created_at": now - timedelta(days=3)},
            {"id": "2", "content": "我讨厌茶", "created_at": now},
        ],
        threshold=0.6,
    )
    assert len(conflicts) == 1
    assert conflicts[0]["conflict_type"] == "opposite"
    assert "茶" in conflicts[0]["common_topic"]


def test_conflict_detector_ignores_different_topics():
    detector = ConflictDetector()
    now = datetime.utcnow()
    conflicts = detector.detect_conflicts(
        [
            {"id": "1", "content": "我喜欢茶", "created_at": now - timedelta(days=3)},
            {"id": "2", "content": "我讨厌咖啡", "created_at": now},
        ],
        threshold=0.6,
    )
    assert conflicts == []


def test_conflict_detector_handles_negation_pair():
    detector = ConflictDetector()
    now = datetime.utcnow()
    conflicts = detector.detect_conflicts(
        [
            {"id": "1", "content": "我爱踢足球", "created_at": now - timedelta(days=2)},
            {"id": "2", "content": "我恨踢足球", "created_at": now},
        ],
        threshold=0.6,
    )
    assert len(conflicts) == 1
    assert any("足球" in t for t in conflicts[0]["common_topic"])

