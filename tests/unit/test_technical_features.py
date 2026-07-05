from datetime import datetime, timedelta, timezone
from decimal import Decimal

from agent.contracts.market import OHLCVBar
from agent.signals.technical import compute_technical_features


def make_bars():
    start = datetime(2026, 7, 5, 3, 45, tzinfo=timezone.utc)
    bars = []
    for index in range(30):
        close = Decimal("100") + Decimal(index)
        bars.append(
            OHLCVBar(
                symbol="RELIANCE",
                timestamp=start + timedelta(minutes=index),
                interval="1m",
                open=close - Decimal("0.5"),
                high=close + Decimal("1"),
                low=close - Decimal("1"),
                close=close,
                volume=1000 + index * 10,
                source="test",
            )
        )
    return bars


def test_compute_technical_features_contains_required_indicators():
    features = compute_technical_features(make_bars())

    assert features.symbol == "RELIANCE"
    assert features.close == 129.0
    assert features.vwap > 0
    assert 0 <= features.rsi <= 100
    assert features.macd > 0
    assert features.atr > 0
    assert features.relative_volume > 1
    assert features.opening_range_high == 103.0
    assert features.opening_range_low == 99.0
    assert features.previous_high == 129.0
    assert features.previous_low == 127.0
    assert features.trend_bias in {"bullish", "bearish", "neutral"}


def test_compute_technical_features_requires_enough_bars():
    try:
        compute_technical_features(make_bars()[:1])
    except ValueError as exc:
        assert "at least two" in str(exc)
    else:
        raise AssertionError("expected ValueError")
