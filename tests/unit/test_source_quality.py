from datetime import datetime, timedelta, timezone

from agent.data.company_announcements import parse_company_announcements
from agent.data.quality import check_source_quality
from agent.data.regulatory_events import parse_regulatory_events
from agent.signals.sentiment import compute_sentiment_features


NOW = datetime(2026, 7, 19, 9, 30, tzinfo=timezone.utc)


def test_source_quality_passes_for_fresh_real_sources():
    announcements = parse_company_announcements(
        [{"symbol": "RELIANCE", "title": "Reliance wins contract", "source": "NSE", "published_at": NOW.isoformat()}]
    )
    regulatory_events = parse_regulatory_events(
        [{"source": "SEBI", "title": "SEBI circular on settlement margins", "published_at": NOW.isoformat()}]
    )

    result = check_source_quality(
        global_news=[{"title": "US markets rally", "published_at": NOW.isoformat()}],
        indian_news=[{"title": "NIFTY gains", "published_at": NOW.isoformat()}],
        company_news=[{"title": "Reliance profit rises", "published_at": NOW.isoformat()}],
        announcements=announcements,
        regulatory_events=regulatory_events,
        now=NOW,
    )

    assert result.passed is True
    assert result.live_trade_blocked is False
    assert result.score == 1.0
    assert result.source_count == 5


def test_source_quality_blocks_unavailable_and_simulated_sources():
    result = check_source_quality(
        global_news=[
            {
                "title": "global news source unavailable",
                "source_mode": "unavailable",
                "source_status": "missing_news_api_key_or_empty_provider_response",
                "published_at": NOW.isoformat(),
            }
        ],
        indian_news=[
            {
                "title": "simulated NIFTY headline",
                "source_mode": "simulated",
                "source_status": "simulated",
                "published_at": NOW.isoformat(),
            }
        ],
        now=NOW,
        require_official_events=False,
    )

    assert result.passed is False
    assert result.live_trade_blocked is True
    assert result.unavailable_count == 1
    assert result.simulated_count == 1
    assert "global_news unavailable" in result.reasons
    assert "indian_news simulated" in result.reasons


def test_source_quality_detects_stale_and_missing_official_events():
    result = check_source_quality(
        company_news=[{"title": "old company headline", "published_at": (NOW - timedelta(hours=2)).isoformat()}],
        announcements=[],
        regulatory_events=[],
        now=NOW,
    )

    assert result.passed is False
    assert result.live_trade_blocked is True
    assert result.stale_count == 1
    assert result.unavailable_count == 2
    assert "company_news stale" in result.reasons
    assert "missing official announcements" in result.reasons
    assert "missing regulatory events" in result.reasons


def test_sentiment_features_include_source_quality_gate():
    source_quality = check_source_quality(
        global_news=[{"title": "global news source unavailable", "source_mode": "unavailable", "published_at": NOW.isoformat()}],
        now=NOW,
        require_official_events=False,
    )

    features = compute_sentiment_features(
        global_context={"global_sentiment": "positive"},
        indian_news=[],
        company_news=[],
        announcements=[],
        source_quality=source_quality,
    )

    assert features.source_quality_score < 1.0
    assert features.live_trade_blocked is True
    assert "source_quality_block" in features.reasons
