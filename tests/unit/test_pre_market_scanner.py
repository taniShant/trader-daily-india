from datetime import datetime, timezone
import sys
import types

import pandas as pd

from agent.overnight.pre_market_scanner import PreMarketScanner


class FakeMarketStateTable:
    def __init__(self, item=None):
        self.item = item or {}
        self.get_keys = []
        self.put_items = []

    def get_item(self, Key):
        self.get_keys.append(Key)
        return {"Item": dict(self.item)} if self.item else {}

    def put_item(self, Item):
        self.put_items.append(Item)
        self.item = Item


def make_scanner(*, watchlist_size=2, min_avg_volume=100000, min_price=20, item=None):
    scanner = PreMarketScanner.__new__(PreMarketScanner)
    scanner.region = "eu-west-2"
    scanner.market_state_table = "market-state-test"
    scanner.watchlist_size = watchlist_size
    scanner.min_avg_volume = min_avg_volume
    scanner.min_price = min_price
    scanner.excluded_symbols = {"TCS", "HDFCBANK", "SBIN"}
    scanner.required_symbols = ["MARUTI"]
    scanner.market_state_db = FakeMarketStateTable(item=item)
    return scanner


def make_history(*, closes, highs=None, lows=None, volumes=None):
    count = len(closes)
    highs = highs or [close + 1 for close in closes]
    lows = lows or [close - 1 for close in closes]
    volumes = volumes or [150000] * count
    return pd.DataFrame(
        {
            "Close": closes,
            "High": highs,
            "Low": lows,
            "Volume": volumes,
        },
        index=pd.date_range("2026-07-01", periods=count, freq="D"),
    )


def test_score_candidate_includes_reason_scores_and_symbol_mappings():
    scanner = make_scanner(min_avg_volume=100000)
    hist = make_history(
        closes=[100, 102],
        highs=[101, 103],
        lows=[99, 101],
        volumes=[100000, 250000],
    )

    candidate = scanner.score_candidate("RELIANCE.NS", hist)

    assert candidate["symbol"] == "RELIANCE"
    assert candidate["yahoo_symbol"] == "RELIANCE.NS"
    assert candidate["breeze_stock_code"] == "RELIANCE"
    assert candidate["direction_bias"] == "bullish"
    assert candidate["volume_ratio"] > 1
    assert candidate["watchlist_score"] > 0
    assert "price move 2.00%" in candidate["reasons"]
    assert any(reason.startswith("avg volume") for reason in candidate["reasons"])


def test_score_candidate_filters_illiquid_or_low_price_names():
    scanner = make_scanner(min_avg_volume=100000, min_price=20)

    assert scanner.score_candidate(
        "RELIANCE",
        make_history(closes=[100, 101], volumes=[1000, 1000]),
    ) is None
    assert scanner.score_candidate(
        "RELIANCE",
        make_history(closes=[10, 11], volumes=[200000, 200000]),
    ) is None


def test_scan_stocks_sorts_by_watchlist_score_and_stores_reasoned_watchlist(monkeypatch):
    scanner = make_scanner(watchlist_size=3, min_avg_volume=1000)
    scanner.get_nifty_stocks = lambda: ["RELIANCE", "TCS", "INFY", "MARUTI"]

    histories = {
        "RELIANCE.NS": make_history(closes=[100, 105], highs=[101, 106], lows=[99, 104], volumes=[1000, 4000]),
        "TCS.NS": make_history(closes=[100, 101], volumes=[1000, 1200]),
        "INFY.NS": make_history(closes=[100, 103], volumes=[1000, 3000]),
        "MARUTI.NS": make_history(closes=[100, 101], volumes=[1000, 1200]),
    }

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period):
            return histories[self.symbol]

    import agent.overnight.pre_market_scanner as scanner_module

    fake_yfinance = types.ModuleType("yfinance")
    fake_yfinance.Ticker = FakeTicker
    monkeypatch.setattr(scanner_module, "datetime", FixedDatetime)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)

    watchlist = scanner.scan_stocks()

    assert [item["symbol"] for item in watchlist] == ["RELIANCE", "INFY", "MARUTI"]
    assert watchlist[0]["watchlist_score"] >= watchlist[1]["watchlist_score"]
    assert watchlist[0]["reasons"]
    stored = scanner.market_state_db.put_items[0]
    assert stored["date"] == "2026-07-05"
    assert stored["timestamp"] == "state#watchlist"
    assert stored["record_type"] == "watchlist"
    assert stored["watchlist_size"] == 3
    assert stored["pre_market_watchlist"][0]["symbol"] == "RELIANCE"
    assert "TCS" not in [item["symbol"] for item in stored["pre_market_watchlist"]]
    assert "MARUTI" in [item["symbol"] for item in stored["pre_market_watchlist"]]


def test_get_watchlist_returns_plain_symbols_for_trading_loop():
    scanner = make_scanner(
        watchlist_size=3,
        item={
            "date": "2026-07-05",
            "pre_market_watchlist": [
                {"symbol": "RELIANCE", "watchlist_score": 75},
                {"symbol": "SBIN", "watchlist_score": 70},
                {"symbol": "INFY", "watchlist_score": 50},
            ],
        }
    )

    assert scanner.get_watchlist() == ["RELIANCE", "INFY", "MARUTI"]
    assert scanner.market_state_db.get_keys[0] == {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "timestamp": "state#watchlist",
    }


def test_default_fallback_watchlist_excludes_unwanted_symbols():
    scanner = make_scanner(watchlist_size=8)

    watchlist = scanner.get_watchlist()

    assert "TCS" not in watchlist
    assert "HDFCBANK" not in watchlist
    assert "SBIN" not in watchlist
    assert "MARUTI" in watchlist


def test_required_symbol_replaces_lowest_ranked_non_required_candidate():
    scanner = make_scanner(watchlist_size=2)
    candidates = [
        {"symbol": "RELIANCE", "watchlist_score": 90},
        {"symbol": "INFY", "watchlist_score": 80},
        {"symbol": "MARUTI", "watchlist_score": 10},
    ]

    watchlist = scanner._with_required_candidates(candidates)

    assert [item["symbol"] for item in watchlist] == ["RELIANCE", "MARUTI"]


class FixedDatetime(datetime):
    @classmethod
    def utcnow(cls):
        return cls(2026, 7, 5, 4, 0, 0)

    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 7, 5, 4, 0, 0)
        if tz is not None:
            return value.replace(tzinfo=timezone.utc)
        return value
