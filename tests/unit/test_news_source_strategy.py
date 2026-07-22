import json
from pathlib import Path

from agent.config import load_settings
from agent.overnight.news_aggregator import NewsAggregator, _safe_sentiment
from agent.tools.news_fetcher import NewsFetcher


ROOT = Path(__file__).resolve().parents[2]


def test_prod_config_disables_silent_simulated_news_by_default():
    config = json.loads((ROOT / "cicd" / "env" / "prod.json").read_text())

    assert config["apis"]["allow_simulated_news"] is False
    assert load_settings("prod", include_env=False).apis.allow_simulated_news is False


def test_allow_simulated_news_can_be_enabled_for_local_tests(monkeypatch):
    monkeypatch.setenv("ALLOW_SIMULATED_NEWS", "true")

    settings = load_settings("prod", include_env=True)

    assert settings.apis.allow_simulated_news is True


def test_news_fetcher_marks_unavailable_sources_instead_of_simulating():
    fetcher = NewsFetcher.__new__(NewsFetcher)
    fetcher.allow_simulated_news = False

    items = fetcher._fallback_news("global", lambda: [{"title": "fake rally"}])

    assert items == [
        {
            "title": "global news source unavailable",
            "source": "system",
            "category": "global",
            "source_mode": "unavailable",
            "source_status": "missing_news_api_key_or_empty_provider_response",
            "published_at": items[0]["published_at"],
        }
    ]


def test_news_fetcher_marks_simulated_news_only_when_explicitly_allowed():
    fetcher = NewsFetcher.__new__(NewsFetcher)
    fetcher.allow_simulated_news = True

    items = fetcher._fallback_news("india", lambda: [{"title": "simulated headline", "source": "test"}])

    assert items[0]["title"] == "simulated headline"
    assert items[0]["source_mode"] == "simulated"
    assert items[0]["source_status"] == "simulated"


def test_overnight_news_aggregator_uses_same_fallback_policy():
    aggregator = NewsAggregator.__new__(NewsAggregator)
    aggregator.allow_simulated_news = False

    unavailable = aggregator._fallback_news("company", lambda: [{"title": "fake company headline"}])

    assert unavailable[0]["title"] == "company news source unavailable"
    assert unavailable[0]["source_mode"] == "unavailable"

    aggregator.allow_simulated_news = True
    simulated = aggregator._fallback_news("company", lambda: [{"title": "fake company headline"}])

    assert simulated[0]["title"] == "fake company headline"
    assert simulated[0]["source_mode"] == "simulated"


def test_news_sentiment_never_returns_none():
    assert _safe_sentiment(None) == 0.0
    assert _safe_sentiment("", default=0.2) == 0.2
    assert _safe_sentiment("0.35") == 0.35


def test_get_latest_sentiment_coerces_stored_null(monkeypatch):
    aggregator = NewsAggregator.__new__(NewsAggregator)
    aggregator.market_state_db = object()

    monkeypatch.setattr(
        "agent.overnight.news_aggregator.get_daily_state",
        lambda table, date, kind: {"latest_sentiment": None},
    )

    assert aggregator.get_latest_sentiment() == 0.0


def test_realtime_update_preserves_previous_sentiment_when_update_is_none(monkeypatch):
    stored_items = []
    aggregator = NewsAggregator.__new__(NewsAggregator)
    aggregator.market_state_db = object()

    monkeypatch.setattr(
        "agent.overnight.news_aggregator.get_daily_state",
        lambda table, date, kind: {"latest_sentiment": 0.25, "realtime_news_updates": []},
    )
    monkeypatch.setattr(
        "agent.overnight.news_aggregator.put_daily_state",
        lambda table, date, kind, item: stored_items.append(item),
    )

    aggregator._store_realtime_update(
        {
            "timestamp": "2026-07-22T08:00:00",
            "new_news_count": 0,
            "sentiment_update": None,
            "has_breaking": False,
            "new_news": [],
        }
    )

    assert stored_items[0]["latest_sentiment"] == 0.25
