from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from agent.contracts.market import OHLCVBar, Quote
from agent.data.quality import check_ohlcv_quality, check_quote_quality, raise_if_failed
from agent.tools.market_data import MarketDataProvider


NOW = datetime(2026, 7, 4, 9, 20, tzinfo=timezone.utc)


def make_quote(**overrides):
    data = {
        "symbol": "RELIANCE",
        "ltp": Decimal("100"),
        "open": Decimal("99"),
        "high": Decimal("101"),
        "low": Decimal("98"),
        "previous_close": Decimal("97"),
        "volume": 1000,
        "source": "test",
        "timestamp": NOW,
    }
    data.update(overrides)
    return Quote(**data)


def make_bar(**overrides):
    data = {
        "symbol": "RELIANCE",
        "timestamp": NOW,
        "interval": "1d",
        "open": Decimal("100"),
        "high": Decimal("105"),
        "low": Decimal("99"),
        "close": Decimal("104"),
        "volume": 1000,
        "source": "test",
    }
    data.update(overrides)
    return OHLCVBar(**data)


def test_fresh_quote_passes_quality_check():
    result = check_quote_quality(make_quote(), now=NOW, max_age_seconds=300, require_volume=True)

    assert result.passed is True
    assert result.reasons == []


def test_stale_quote_fails_closed_with_reason():
    result = check_quote_quality(
        make_quote(timestamp=NOW - timedelta(minutes=10)),
        now=NOW,
        max_age_seconds=300,
    )

    assert result.passed is False
    assert "stale quote" in result.reasons


def test_quote_missing_required_volume_fails_when_requested():
    result = check_quote_quality(make_quote(volume=0), now=NOW, require_volume=True)

    assert result.passed is False
    assert "missing quote volume" in result.reasons


def test_ohlcv_quality_rejects_missing_candles():
    result = check_ohlcv_quality([], min_bars=1)

    assert result.passed is False
    assert result.reasons == ["missing candles"]


def test_ohlcv_quality_rejects_zero_volume_and_mismatch():
    result = check_ohlcv_quality(
        [make_bar(symbol="TCS", volume=0)],
        symbol="RELIANCE",
        interval="1d",
        require_nonzero_volume=True,
    )

    assert result.passed is False
    assert "zero volume candle" in result.reasons
    assert "symbol mismatch" in result.reasons


def test_ohlcv_quality_rejects_stale_last_bar():
    result = check_ohlcv_quality(
        [make_bar(timestamp=NOW - timedelta(days=2))],
        now=NOW,
        max_last_bar_age_seconds=3600,
    )

    assert result.passed is False
    assert "stale candle" in result.reasons


def test_raise_if_failed_raises_combined_reason():
    result = check_ohlcv_quality([], min_bars=1)

    with pytest.raises(ValueError, match="missing candles"):
        raise_if_failed(result)


def test_market_data_provider_returns_quality_error_for_bad_breeze_quote():
    class FakeBreeze:
        def get_quotes(self, **kwargs):
            return {
                "Success": {
                    "ltp": "100",
                    "open": "99",
                    "high": "101",
                    "low": "98",
                    "close": "97",
                    "volume": "0",
                }
            }

    provider = MarketDataProvider.__new__(MarketDataProvider)
    provider.use_breeze = True
    provider.breeze = FakeBreeze()

    payload = provider.get_live_quote("RELIANCE")

    assert payload["error"] == "data_quality_failed"
    assert payload["symbol"] == "RELIANCE"
    assert "missing quote volume" in payload["reasons"]
