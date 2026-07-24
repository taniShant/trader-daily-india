import pytest

from agent.data.oracle_client import (
    OracleCollectorClient,
    OracleCollectorError,
    get_market_context_with_fallback,
)


class FakeResponse:
    def __init__(self, *, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def test_oracle_collector_client_fetches_and_normalizes_context(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=10):
        calls.append((url, params, timeout))
        return FakeResponse(
            payload={
                "as_of": "2026-07-05T04:00:00+00:00",
                "macro": {"global_sentiment": "positive"},
                "news": [{"title": "RBI policy unchanged"}],
                "sentiment_score": 0.25,
                "key_headlines": ["RBI policy unchanged"],
            }
        )

    monkeypatch.setattr("agent.data.oracle_client.requests.get", fake_get)

    context = OracleCollectorClient("http://80.225.242.6:8090", timeout_seconds=3).fetch_market_context()

    assert calls == [("http://80.225.242.6:8090/market-context/latest", None, 3)]
    assert context["source"] == "oracle"
    assert context["macro"]["global_sentiment"] == "positive"
    assert context["sentiment_score"] == 0.25


def test_oracle_collector_client_fetches_quote(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=10):
        calls.append((url, params, timeout))
        return FakeResponse(
            payload={
                "symbol": "MARUTI",
                "ltp": "12500.50",
                "open": "12400",
                "high": "12600",
                "low": "12350",
                "close": "12375",
                "volume": 100000,
                "timestamp": "2026-07-21T04:00:00+00:00",
                "source": "breeze",
            }
        )

    monkeypatch.setattr("agent.data.oracle_client.requests.get", fake_get)

    quote = OracleCollectorClient("http://80.225.242.6:8090", timeout_seconds=3).fetch_quote("MARUTI")

    assert calls == [("http://80.225.242.6:8090/quotes/MARUTI", None, 3)]
    assert quote["symbol"] == "MARUTI"
    assert quote["source"] == "breeze"


def test_oracle_collector_client_fetches_ohlcv(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=10):
        calls.append((url, params, timeout))
        return FakeResponse(
            payload={
                "symbol": "MARUTI",
                "days": 5,
                "interval": "5m",
                "data": [
                    {
                        "symbol": "MARUTI",
                        "timestamp": "2026-07-21T04:00:00+00:00",
                        "interval": "5m",
                        "open": "100",
                        "high": "101",
                        "low": "99",
                        "close": "100.5",
                        "volume": 1000,
                        "source": "breeze",
                    }
                ],
            }
        )

    monkeypatch.setattr("agent.data.oracle_client.requests.get", fake_get)

    candles = OracleCollectorClient("http://80.225.242.6:8090", timeout_seconds=4).fetch_ohlcv(
        "MARUTI",
        days=5,
        interval="5m",
    )

    assert calls == [("http://80.225.242.6:8090/ohlcv/MARUTI", {"days": 5, "interval": "5m"}, 4)]
    assert candles["data"][0]["source"] == "breeze"


def test_oracle_collector_client_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(
        "agent.data.oracle_client.requests.get",
        lambda url, params=None, timeout=10: FakeResponse(status_code=503, payload={}, text="not ready"),
    )

    with pytest.raises(OracleCollectorError, match="503"):
        OracleCollectorClient("http://oracle.test").fetch_market_context()


def test_market_context_falls_back_when_oracle_unavailable(monkeypatch):
    monkeypatch.setattr(
        "agent.data.oracle_client.requests.get",
        lambda url, params=None, timeout=10: FakeResponse(status_code=503, payload={}, text="not ready"),
    )

    context = get_market_context_with_fallback(
        OracleCollectorClient("http://oracle.test"),
        lambda: {"macro": {"global_sentiment": "neutral"}, "news": []},
    )

    assert context["source"] == "fallback"
    assert context["macro"]["global_sentiment"] == "neutral"
    assert "oracle_error" in context
