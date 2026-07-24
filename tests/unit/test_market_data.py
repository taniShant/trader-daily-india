from datetime import datetime, timezone
from decimal import Decimal

import pytest

from agent.data.market_data import (
    bars_to_dataframe,
    normalize_ohlcv_bars,
    normalize_quote,
    ohlcv_bars_to_tool_payload,
    quote_to_tool_payload,
)
from agent.tools.market_data import MarketDataProvider


def test_normalize_quote_accepts_provider_specific_fields():
    quote = normalize_quote(
        {
            "lastPrice": "2500.50",
            "open": "2490",
            "dayHigh": "2510",
            "dayLow": "2485",
            "previousClose": "2475",
            "volume": "120000",
            "timestamp": "2026-07-04T09:15:00+00:00",
        },
        symbol="RELIANCE",
        source="yfinance",
    )

    assert quote.symbol == "RELIANCE"
    assert quote.ltp == Decimal("2500.50")
    assert quote.high == Decimal("2510")
    assert quote.low == Decimal("2485")
    assert quote.previous_close == Decimal("2475")
    assert quote.volume == 120000
    assert quote.timestamp == datetime(2026, 7, 4, 9, 15, tzinfo=timezone.utc)


def test_quote_tool_payload_keeps_legacy_close_key():
    quote = normalize_quote(
        {
            "ltp": "100",
            "open": "99",
            "high": "101",
            "low": "98",
            "close": "97",
            "volume": 1,
        },
        symbol="TCS",
        source="breeze",
        timestamp=datetime(2026, 7, 4, tzinfo=timezone.utc),
    )

    payload = quote_to_tool_payload(quote)

    assert payload["symbol"] == "TCS"
    assert payload["ltp"] == "100"
    assert payload["close"] == "97"
    assert "previous_close" not in payload


def test_normalize_ohlcv_bars_and_dataframe_shape():
    bars = normalize_ohlcv_bars(
        [
            {
                "Date": datetime(2026, 7, 1, tzinfo=timezone.utc),
                "Open": "100",
                "High": "105",
                "Low": "99",
                "Close": "104",
                "Volume": "5000",
            },
            {
                "Date": datetime(2026, 7, 2, tzinfo=timezone.utc),
                "Open": "104",
                "High": "108",
                "Low": "103",
                "Close": "107",
                "Volume": "7000",
            },
        ],
        symbol="INFY",
        interval="1d",
        source="yfinance",
    )

    payload = ohlcv_bars_to_tool_payload(symbol="INFY", days=2, interval="1d", bars=bars)
    df = bars_to_dataframe(payload)

    assert payload["latest_close"] == 107.0
    assert payload["latest_volume"] == 7000
    assert payload["high_52w"] == 108.0
    assert payload["low_52w"] == 99.0
    assert list(df[["open", "high", "low", "close", "volume"]].iloc[-1]) == [
        104,
        108,
        103,
        107,
        7000,
    ]


def test_provider_breeze_quote_path_returns_normalized_payload():
    class FakeBreeze:
        def get_quotes(self, **kwargs):
            return {
                "Success": {
                    "ltp": "100",
                    "open": "99",
                    "high": "101",
                    "low": "98",
                    "close": "97",
                    "volume": "123",
                }
            }

    provider = MarketDataProvider.__new__(MarketDataProvider)
    provider.use_breeze = True
    provider.breeze = FakeBreeze()

    payload = provider.get_live_quote("SBIN")

    assert payload["symbol"] == "SBIN"
    assert payload["exchange"] == "NSE"
    assert payload["ltp"] == "100"
    assert payload["close"] == "97"
    assert payload["volume"] == 123
    assert payload["source"] == "breeze"


def test_provider_prefers_oracle_collector_quote():
    class FakeOracle:
        def fetch_quote(self, symbol):
            return {
                "symbol": symbol,
                "ltp": "12500.50",
                "open": "12400",
                "high": "12600",
                "low": "12350",
                "close": "12375",
                "volume": 100000,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "breeze",
            }

    provider = MarketDataProvider.__new__(MarketDataProvider)
    provider.oracle_client = FakeOracle()
    provider.use_breeze = False
    provider.breeze = None

    payload = provider.get_live_quote("MARUTI.NS")

    assert payload["symbol"] == "MARUTI"
    assert payload["source"] == "breeze"
    assert payload["ltp"] == "12500.50"


def test_provider_prefers_oracle_collector_ohlcv():
    now = datetime.now(timezone.utc)

    class FakeOracle:
        def fetch_ohlcv(self, symbol, *, days, interval):
            return {
                "symbol": symbol,
                "days": days,
                "interval": interval,
                "data": [
                    {
                        "symbol": symbol,
                        "timestamp": (now.replace(microsecond=0)).isoformat(),
                        "interval": interval,
                        "open": "100",
                        "high": "102",
                        "low": "99",
                        "close": "101",
                        "volume": 2500,
                        "source": "breeze",
                    }
                ],
            }

    provider = MarketDataProvider.__new__(MarketDataProvider)
    provider.oracle_client = FakeOracle()
    provider.use_breeze = False
    provider.breeze = None

    payload = provider.get_historical_data("MARUTI.NS", days=5, interval="5m")

    assert payload["symbol"] == "MARUTI"
    assert payload["interval"] == "5m"
    assert payload["latest_close"] == 101.0
    assert payload["data"][0]["source"] == "breeze"


def test_invalid_ohlcv_range_is_rejected():
    with pytest.raises(ValueError, match="within low/high"):
        normalize_ohlcv_bars(
            [
                {
                    "Date": datetime(2026, 7, 1, tzinfo=timezone.utc),
                    "Open": "110",
                    "High": "105",
                    "Low": "99",
                    "Close": "104",
                    "Volume": "5000",
                }
            ],
            symbol="INFY",
            interval="1d",
            source="test",
        )
