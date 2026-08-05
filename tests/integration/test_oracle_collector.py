import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "oracle" / "collector" / "app.py"


def load_collector_app(monkeypatch):
    monkeypatch.setenv("ORACLE_COLLECTOR_MODE", "mock")
    monkeypatch.setenv("ORACLE_STATIC_IP", "80.225.242.6")
    sys.modules.pop("oracle_collector_app_test", None)
    spec = importlib.util.spec_from_file_location("oracle_collector_app_test", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["oracle_collector_app_test"] = module
    spec.loader.exec_module(module)
    return module.app


def test_oracle_collector_health_and_market_context_cache(monkeypatch):
    client = TestClient(load_collector_app(monkeypatch))

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["static_ip"] == "80.225.242.6"

    payload = {
        "as_of": "2026-07-05T04:00:00+00:00",
        "macro": {"global_sentiment": "positive"},
        "news": [{"title": "US markets close higher"}],
        "sentiment_score": 0.35,
        "key_headlines": ["US markets close higher"],
    }
    stored = client.post("/market-context/latest", json=payload)
    latest = client.get("/market-context/latest")

    assert stored.status_code == 200
    assert stored.json()["status"] == "stored"
    assert latest.status_code == 200
    assert latest.json()["macro"]["global_sentiment"] == "positive"
    assert latest.json()["sentiment_score"] == 0.35


def test_oracle_collector_mock_quote_and_ohlcv_endpoints(monkeypatch):
    client = TestClient(load_collector_app(monkeypatch))

    quote = client.get("/quotes/MARUTI.NS")
    candles = client.get("/ohlcv/MARUTI.NS", params={"days": 2, "interval": "5m"})

    assert quote.status_code == 200
    assert quote.json()["symbol"] == "MARUTI"
    assert quote.json()["exchange"] == "NSE"
    assert float(quote.json()["ltp"]) > 0
    assert quote.json()["volume"] > 0

    assert candles.status_code == 200
    assert candles.json()["symbol"] == "MARUTI"
    assert candles.json()["interval"] == "5m"
    assert candles.json()["latest_close"] > 0
    assert len(candles.json()["data"]) >= 8
    assert candles.json()["data"][-1]["volume"] > 0


def test_oracle_collector_live_ohlcv_uses_breeze_datetime_format(monkeypatch):
    load_collector_app(monkeypatch)
    collector_module = sys.modules["oracle_collector_app_test"]
    calls = []

    class FakeBreeze:
        def generate_session(self, **kwargs):
            pass

        def get_historical_data_v2(self, **kwargs):
            calls.append(kwargs)
            return {
                "Success": [
                    {
                        "datetime": "2026-07-24T09:15:00.000Z",
                        "open": "100",
                        "high": "101",
                        "low": "99",
                        "close": "100.5",
                        "volume": "12345",
                    }
                ]
            }

    client = collector_module.BreezeMarketDataClient.__new__(collector_module.BreezeMarketDataClient)
    client.client = FakeBreeze()

    payload = client.ohlcv("MARUTI", interval="5m", days=5)

    assert payload["symbol"] == "MARUTI"
    assert calls[0]["interval"] == "5minute"
    assert calls[0]["stock_code"] == "MARUTI"
    assert calls[0]["from_date"].endswith("T09:15:00.000Z")
    assert calls[0]["from_date"].endswith(".000Z")
    assert calls[0]["to_date"].endswith(".000Z")
    assert "+" not in calls[0]["from_date"]
    assert calls[0]["product_type"] == "cash"


def test_oracle_collector_breeze_intraday_range_uses_india_market_wall_clock(monkeypatch):
    load_collector_app(monkeypatch)
    collector_module = sys.modules["oracle_collector_app_test"]

    during_market = collector_module.datetime(2026, 8, 5, 6, 5, tzinfo=collector_module.timezone.utc)
    after_market = collector_module.datetime(2026, 8, 5, 12, 0, tzinfo=collector_module.timezone.utc)
    before_market = collector_module.datetime(2026, 8, 5, 2, 0, tzinfo=collector_module.timezone.utc)

    start, end = collector_module._breeze_date_range(days=1, interval="1m", now=during_market)
    assert collector_module._breeze_datetime(start).endswith("T09:15:00.000Z")
    assert collector_module._breeze_datetime(end).endswith("T11:35:00.000Z")

    _, end = collector_module._breeze_date_range(days=1, interval="1m", now=after_market)
    assert collector_module._breeze_datetime(end).endswith("T15:30:00.000Z")

    _, end = collector_module._breeze_date_range(days=1, interval="1m", now=before_market)
    assert collector_module._breeze_datetime(end).endswith("T09:15:00.000Z")


def test_oracle_collector_live_ohlcv_accepts_technical_lookback(monkeypatch):
    client = TestClient(load_collector_app(monkeypatch))

    candles = client.get("/ohlcv/MARUTI", params={"days": 60, "interval": "5m"})

    assert candles.status_code == 200
    assert candles.json()["symbol"] == "MARUTI"


def test_oracle_collector_maps_nse_symbols_to_breeze_codes(monkeypatch):
    load_collector_app(monkeypatch)
    collector_module = sys.modules["oracle_collector_app_test"]

    assert collector_module._breeze_stock_code("ADANIPORTS") == "ADAPOR"
    assert collector_module._breeze_stock_code("RELIANCE") == "RELIANCE"
    assert collector_module._breeze_stock_code("INFY") == "INFY"
    assert collector_module._breeze_stock_code("HDFCBANK") == "HDFBAN"
    assert collector_module._breeze_stock_code("ICICIBANK") == "ICICIBAN"
    assert collector_module._breeze_stock_code("BHARTIARTL") == "BHAART"
    assert collector_module._breeze_stock_code("KOTAKBANK") == "KOTMAH"
    assert collector_module._breeze_stock_code("BAJFINANCE") == "BAJFIN"
    assert collector_module._breeze_stock_code("HINDUNILVR") == "HINLEV"
    assert collector_module._breeze_stock_code("AXISBANK") == "AXIBAN"
    assert collector_module._breeze_stock_code("LT") == "LARTOU"
    assert collector_module._breeze_stock_code("HEROMOTOCO") == "HERHON"
    assert collector_module._breeze_stock_code("TITAN") == "TITAN"
    assert collector_module._breeze_stock_code("TECHM") == "TECMAH"
    assert collector_module._breeze_stock_code("ASIANPAINT") == "ASIPAI"
    assert collector_module._breeze_stock_code("HCLTECH") == "HCLTEC"
    assert collector_module._breeze_stock_code("DIVISLAB") == "DIVLAB"
    assert collector_module._breeze_stock_code("BAJAJFINSV") == "BAJFSV"
    assert collector_module._breeze_stock_code("EICHERMOT") == "EICMOT"
    assert collector_module._breeze_stock_code("SUNPHARMA") == "SUNPHA"
    assert collector_module._breeze_stock_code("JSWSTEEL") == "JSWSTE"
    assert collector_module._breeze_stock_code("M&M") == "MAHMAH"
    assert collector_module._breeze_stock_code("TATAMOTORS") == "TATMOT"
    assert collector_module._breeze_stock_code("TMCV") == "TATMOT"
    assert collector_module._breeze_stock_code("TMPV") == "TATMOT"
    assert collector_module._breeze_stock_code("TATASTEEL") == "TATSTE"
    assert collector_module._breeze_stock_code("HINDALCO") == "HINDAL"
    assert collector_module._breeze_stock_code("BRITANNIA") == "BRITAN"
    assert collector_module._breeze_stock_code("DRREDDY") == "DRREDD"
    assert collector_module._breeze_stock_code("COALINDIA") == "COALIN"
    assert collector_module._breeze_stock_code("BAJAJ-AUTO") == "BAAUTO"
    assert collector_module._breeze_stock_code("MARUTI") == "MARUTI"
    assert collector_module._breeze_stock_code("WIPRO") == "WIPRO"
    assert collector_module._breeze_stock_code("ONGC") == "ONGC"
    assert collector_module._breeze_stock_code("NTPC") == "NTPC"
    assert collector_module._breeze_stock_code("POWERGRID") == "POWGRID"
    assert collector_module._breeze_stock_code("ULTRACEMCO") == "ULTECO"
    assert collector_module._breeze_stock_code("GRASIM") == "GRAIND"
    assert collector_module._breeze_stock_code("NESTLEIND") == "NESIND"
    assert collector_module._breeze_stock_code("INDUSINDBK") == "INDBAN"
    assert collector_module._breeze_stock_code("SBILIFE") == "SBILIF"
    assert collector_module._breeze_stock_code("HDFCLIFE") == "HDFLIF"
    assert collector_module._breeze_stock_code("UPL") == "UPLLTD"
    assert collector_module._breeze_stock_code("SHREECEM") == "SHRCEM"
    assert collector_module._breeze_stock_code("CIPLA") == "CIPLA"
    assert collector_module._breeze_stock_code("BPCL") == "BPCL"
    assert collector_module._breeze_stock_code("IOC") == "IOC"
    assert collector_module._breeze_stock_code("TATACONSUM") == "TATGLO"
