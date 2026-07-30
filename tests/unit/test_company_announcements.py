from datetime import datetime, timezone

import pytest

from agent.data.company_announcements import (
    AnnouncementCategory,
    AnnouncementImpact,
    announcements_to_event_features,
    classify_announcement,
    infer_impact,
    parse_company_announcement,
    parse_company_announcements,
)


def test_parse_company_announcement_normalizes_symbol_and_event_fields():
    announcement = parse_company_announcement(
        {
            "stock": "reliance.ns",
            "title": "Reliance wins order for new energy partnership",
            "source": "BSE",
            "published_at": "2026-07-05T04:00:00+00:00",
            "url": "https://example.com/announcement",
        }
    )

    assert announcement.symbol == "RELIANCE"
    assert announcement.yahoo_symbol == "RELIANCE.NS"
    assert announcement.breeze_stock_code == "RELIND"
    assert announcement.category == AnnouncementCategory.ORDER_WIN
    assert announcement.impact == AnnouncementImpact.POSITIVE
    assert announcement.impact_score == 0.5
    assert announcement.published_at == datetime(2026, 7, 5, 4, 0, tzinfo=timezone.utc)
    assert announcement.announcement_id.startswith("RELIANCE-2026-07-05-")


def test_announcement_classification_and_impact_rules():
    assert classify_announcement("Board meeting to consider dividend") == AnnouncementCategory.BOARD_MEETING
    assert classify_announcement("Company receives SEBI penalty notice") == AnnouncementCategory.REGULATORY
    assert classify_announcement("Board approves bonus issue") == AnnouncementCategory.CORPORATE_ACTION

    assert infer_impact("Company receives SEBI penalty notice", AnnouncementCategory.REGULATORY) == AnnouncementImpact.NEGATIVE
    assert infer_impact("Company announces dividend", AnnouncementCategory.DIVIDEND) == AnnouncementImpact.POSITIVE
    assert infer_impact("Board meeting scheduled", AnnouncementCategory.BOARD_MEETING) == AnnouncementImpact.NEUTRAL


def test_parse_company_announcements_deduplicates_by_announcement_id():
    payloads = [
        {
            "announcement_id": "ann-1",
            "symbol": "TCS",
            "title": "TCS wins contract",
            "source": "NSE",
            "published_at": "2026-07-05T04:00:00+00:00",
        },
        {
            "announcement_id": "ann-1",
            "symbol": "TCS",
            "title": "TCS wins contract",
            "source": "NSE",
            "published_at": "2026-07-05T04:00:00+00:00",
        },
    ]

    announcements = parse_company_announcements(payloads)

    assert len(announcements) == 1
    assert announcements[0].symbol == "TCS"


def test_announcements_to_event_features_groups_by_symbol():
    announcements = parse_company_announcements(
        [
            {
                "symbol": "INFY",
                "title": "Infosys profit rises in quarter",
                "source": "BSE",
                "published_at": "2026-07-05T04:00:00+00:00",
            },
            {
                "symbol": "INFY",
                "title": "Infosys CFO resigns",
                "source": "BSE",
                "published_at": "2026-07-05T05:00:00+00:00",
            },
        ]
    )

    features = announcements_to_event_features(announcements)
    infy = features["company_announcements"][0]

    assert infy["symbol"] == "INFY"
    assert infy["announcement_count"] == 2
    assert infy["net_impact_score"] == 0.0
    assert "results" in infy["categories"]
    assert "management" in infy["categories"]
    assert len(infy["latest_titles"]) == 2


def test_parse_company_announcement_requires_symbol_and_title():
    with pytest.raises(ValueError, match="title"):
        parse_company_announcement({"symbol": "RELIANCE"})

    with pytest.raises(ValueError, match="symbol"):
        parse_company_announcement({"title": "Reliance announces dividend"})
