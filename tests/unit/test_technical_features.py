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


def test_compute_technical_features_uses_only_latest_ist_market_session():
    previous_session = make_bars()
    current_start = datetime(2026, 7, 6, 3, 45, tzinfo=timezone.utc)
    current_session = []
    for index in range(4):
        close = Decimal("200") + Decimal(index)
        current_session.append(
            OHLCVBar(
                symbol="RELIANCE",
                timestamp=current_start + timedelta(minutes=index),
                interval="1m",
                open=close - Decimal("0.5"),
                high=close + Decimal("1"),
                low=close - Decimal("1"),
                close=close,
                volume=2000 + index * 100,
                source="test",
            )
        )

    features = compute_technical_features(previous_session + current_session)

    assert features.close == 203.0
    assert features.opening_range_high == 203.0
    assert features.opening_range_low == 199.0
    assert features.previous_high == 203.0
    assert features.previous_low == 201.0
    assert features.latest_timestamp == current_start + timedelta(minutes=3)


def test_compute_technical_features_treats_naive_breeze_timestamps_as_ist():
    payload = {
        "symbol": "RELIANCE",
        "data": [
            {
                "timestamp": f"2026-07-06T09:{15 + index:02d}:00",
                "open": 100 + index,
                "high": 101 + index,
                "low": 99 + index,
                "close": 100 + index,
                "volume": 1000 + index,
                "source": "breeze",
            }
            for index in range(3)
        ],
    }

    features = compute_technical_features(payload)

    assert features.latest_timestamp == datetime(2026, 7, 6, 3, 47, tzinfo=timezone.utc)
