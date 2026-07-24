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
