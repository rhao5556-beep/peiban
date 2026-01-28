from datetime import datetime, timedelta

from app.worker.tasks.decay import calculate_decayed_weight


def test_calculate_decayed_weight_decays_over_time():
    updated_at = datetime.now() - timedelta(days=10)
    w = calculate_decayed_weight(1.0, decay_rate=0.1, updated_at=updated_at)
    assert w < 1.0

