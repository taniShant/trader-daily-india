from agent.data.company_announcements import parse_company_announcements
from agent.signals.sentiment import compute_sentiment_features


def test_sentiment_scoring_separates_sources_and_combines_scores():
    announcements = parse_company_announcements(
        [
            {
                "symbol": "RELIANCE",
                "title": "Reliance wins contract",
                "source": "BSE",
                "published_at": "2026-07-05T04:00:00+00:00",
            }
        ]
    )

    features = compute_sentiment_features(
        global_context={"global_sentiment": "positive"},
        indian_news=[{"title": "Indian market shows growth"}],
        company_news=[{"title": "Reliance profit rises"}],
        announcements=announcements,
    )

    assert features.global_score == 0.4
    assert features.indian_market_score > 0
    assert features.company_news_score > 0
    assert features.announcement_score == 0.5
    assert features.combined_score > 0.2
    assert features.bias == "bullish"
    assert features.event_count == 3


def test_sentiment_scoring_handles_negative_company_events():
    features = compute_sentiment_features(
        global_context={"sentiment_score": -0.5},
        indian_news=[{"title": "RBI penalty notice shakes banks"}],
        company_news=[{"title": "Company profit falls"}],
        announcements=[],
    )

    assert features.combined_score < -0.2
    assert features.bias == "bearish"
    assert any(reason.startswith("global") for reason in features.reasons)
