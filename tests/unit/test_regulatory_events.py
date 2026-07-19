from datetime import datetime, timezone

import pytest

from agent.data.regulatory_events import (
    RBI_NOTIFICATIONS_RSS_URL,
    RBI_PRESS_RELEASES_RSS_URL,
    RBI_RSS_PAGE_URL,
    SEBI_RSS_PAGE_URL,
    SEBI_RSS_URL,
    RegulatoryEventCategory,
    RegulatoryImpact,
    RegulatorySource,
    RegulatorySourceError,
    classify_regulatory_event,
    fetch_regulatory_rss,
    parse_regulatory_event,
    parse_regulatory_events,
    parse_regulatory_rss,
    parse_regulatory_timestamp,
    regulatory_events_to_features,
)


def test_parse_rbi_policy_event_payload():
    event = parse_regulatory_event(
        {
            "source": "RBI",
            "title": "Monetary Policy Committee keeps repo rate unchanged",
            "published_at": "Jul 18, 2026",
            "url": "https://www.rbi.org.in/example",
            "event_id": "rbi-1",
        }
    )

    assert event.event_id == "rbi-1"
    assert event.source == RegulatorySource.RBI
    assert event.category == RegulatoryEventCategory.MONETARY_POLICY
    assert event.impact == RegulatoryImpact.NEUTRAL
    assert event.published_at == datetime(2026, 7, 18, tzinfo=timezone.utc)


def test_parse_sebi_enforcement_event_payload_as_caution():
    event = parse_regulatory_event(
        {
            "source": "SEBI",
            "type": "Orders / Rulings",
            "title": "SEBI imposes penalty and restrains entity from securities market",
            "published_at": "18-Jul-2026 10:15:00",
            "event_id": "sebi-1",
        }
    )

    assert event.source == RegulatorySource.SEBI
    assert event.category == RegulatoryEventCategory.ENFORCEMENT
    assert event.impact == RegulatoryImpact.CAUTION
    assert event.impact_score == -0.2


def test_parse_regulatory_events_deduplicates():
    events = parse_regulatory_events(
        [
            {"source": "SEBI", "title": "Circular on settlement margins", "event_id": "same"},
            {"source": "SEBI", "title": "Circular on settlement margins", "event_id": "same"},
        ]
    )

    assert len(events) == 1
    assert events[0].category == RegulatoryEventCategory.MARKET_STRUCTURE


def test_parse_regulatory_rss_for_rbi_and_sebi_items():
    rss = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>RBI announces liquidity infusion through auction</title>
        <link>https://www.rbi.org.in/item1</link>
        <guid>rbi-rss-1</guid>
        <pubDate>Sat, 18 Jul 2026 10:30:00 GMT</pubDate>
      </item>
      <item>
        <title>RBI imposes monetary penalty on a bank</title>
        <link>https://www.rbi.org.in/item2</link>
        <guid>rbi-rss-2</guid>
        <pubDate>Sat, 18 Jul 2026 11:30:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    events = parse_regulatory_rss(rss, source="RBI")

    assert [event.event_id for event in events] == ["rbi-rss-1", "rbi-rss-2"]
    assert events[0].category == RegulatoryEventCategory.LIQUIDITY
    assert events[1].impact == RegulatoryImpact.CAUTION


def test_fetch_regulatory_rss_uses_source_headers_and_raises_on_http_errors(monkeypatch):
    class GoodResponse:
        status_code = 200
        text = """<rss><channel><item>
        <title>SEBI operationalises fast-track mechanism</title>
        <guid>sebi-rss-1</guid>
        <pubDate>Sat, 18 Jul 2026 12:30:00 GMT</pubDate>
        </item></channel></rss>"""

    calls = []

    def fake_get(url, headers, timeout):
        calls.append((url, headers, timeout))
        return GoodResponse()

    monkeypatch.setattr("agent.data.regulatory_events.requests.get", fake_get)

    events = fetch_regulatory_rss(SEBI_RSS_URL, source="SEBI")

    assert events[0].source == RegulatorySource.SEBI
    assert events[0].impact == RegulatoryImpact.POSITIVE
    assert calls[0][0] == SEBI_RSS_URL
    assert "User-Agent" in calls[0][1]
    assert calls[0][2] == 15

    class BadResponse:
        status_code = 503
        text = ""

    monkeypatch.setattr("agent.data.regulatory_events.requests.get", lambda url, headers, timeout: BadResponse())

    with pytest.raises(RegulatorySourceError, match="HTTP 503"):
        fetch_regulatory_rss(SEBI_RSS_URL, source="SEBI")


def test_regulatory_events_to_features_summarizes_live_risk_flags():
    events = parse_regulatory_events(
        [
            {"source": "SEBI", "title": "SEBI imposes penalty on entity", "event_id": "e1"},
            {"source": "RBI", "title": "RBI announces relaxation for banks", "event_id": "e2"},
        ]
    )

    features = regulatory_events_to_features(events)

    assert features["regulatory_event_count"] == 2
    assert features["regulatory_caution_count"] == 1
    assert features["regulatory_net_impact_score"] == 0.2
    assert features["regulatory_events"][0]["source"] == "SEBI"


def test_regulatory_timestamp_formats_and_official_urls_are_tracked():
    assert parse_regulatory_timestamp("2026-07-18T12:00:00Z") == datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
    assert parse_regulatory_timestamp("18/07/2026") == datetime(2026, 7, 18, tzinfo=timezone.utc)

    assert classify_regulatory_event("Circular on settlement margin", source=RegulatorySource.SEBI) == RegulatoryEventCategory.MARKET_STRUCTURE
    assert "rbi.org.in" in RBI_RSS_PAGE_URL
    assert "rbi.org.in" in RBI_PRESS_RELEASES_RSS_URL
    assert "rbi.org.in" in RBI_NOTIFICATIONS_RSS_URL
    assert "sebi.gov.in" in SEBI_RSS_PAGE_URL
    assert "sebi.gov.in" in SEBI_RSS_URL
