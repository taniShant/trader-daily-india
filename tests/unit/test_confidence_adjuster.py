from agent.learning.confidence_adjuster import ConfidenceAdjuster


def test_confidence_adjuster_keeps_base_threshold_with_tiny_sample(monkeypatch):
    monkeypatch.setenv("MIN_CONFIDENCE_THRESHOLD", "70")
    adjuster = ConfidenceAdjuster.__new__(ConfidenceAdjuster)
    adjuster.base_threshold = 70
    adjuster.adjustment = 0
    adjuster._get_latest_patterns = lambda: {
        "total_trades": 1,
        "winning_trades": 0,
        "rsi_buckets": {},
        "sentiment_buckets": {},
    }

    assert adjuster.update_from_patterns() == 70
    assert adjuster.adjustment == 0
