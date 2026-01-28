from app.services.affinity_service import AffinitySignals, cap_affinity_signals


def test_cap_affinity_signals_disables_user_initiated_when_too_frequent():
    signals = AffinitySignals(user_initiated=True, emotion_valence=0.2)
    capped = cap_affinity_signals(signals, recent_updates=999)
    assert capped.user_initiated is False
    assert capped.emotion_valence == signals.emotion_valence


def test_cap_affinity_signals_keeps_user_initiated_when_under_threshold():
    signals = AffinitySignals(user_initiated=True, emotion_valence=0.2)
    capped = cap_affinity_signals(signals, recent_updates=10)
    assert capped.user_initiated is True

