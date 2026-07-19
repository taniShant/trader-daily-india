from datetime import datetime, timezone

import pytest

from agent.data.announcement_sources import (
    BSE_CORPORATE_FILINGS_URL,
    NSE_CORPORATE_FILINGS_URL,
    NSE_RSS_FEEDS_URL,
    AnnouncementSourceError,
    fetch_nse_rss_announcements,
    normalize_bse_announcement,
    normalize_nse_announcement,
    normalize_official_announcements,
    parse_nse_rss,
    parse_source_timestamp,
)
from agent.data.company_announcements import AnnouncementCategory, AnnouncementImpact


def test_normalize_nse_announcement_payload_to_company_announcement():
    announcement = normalize_nse_announcement(
        {
            "symbol": "MARUTI",
            "desc": "Board Meeting Intimation to consider dividend",
            "broadcastDate": "18-Jul-2026 13:22:00",
            "attchmntFile": "/corporate/MARUTI_18072026.pdf",
            "seq_id": "nse-123",
        }
    )

    assert announcement.announcement_id == "nse-123"
    assert announcement.symbol == "MARUTI"
    assert announcement.source == "NSE"
    assert announcement.category == AnnouncementCategory.BOARD_MEETING
    assert announcement.impact == AnnouncementImpact.POSITIVE
    assert announcement.published_at == datetime(2026, 7, 18, 13, 22, tzinfo=timezone.utc)
    assert announcement.url == "https://www.nseindia.com/corporate/MARUTI_18072026.pdf"


def test_normalize_bse_announcement_payload_to_company_announcement():
    announcement = normalize_bse_announcement(
        {
            "SYMBOL": "INFY",
            "NEWSSUB": "Infosys CFO resigns from the company",
            "DissemDT": "18 Jul 2026 09:45:00",
            "ATTACHMENTNAME": "xml-data/corpfiling/AttachLive/INFY_18072026.pdf",
            "NEWSID": "bse-456",
        }
    )

    assert announcement.announcement_id == "bse-456"
    assert announcement.symbol == "INFY"
    assert announcement.source == "BSE"
    assert announcement.category == AnnouncementCategory.MANAGEMENT
    assert announcement.impact == AnnouncementImpact.NEGATIVE
    assert announcement.published_at == datetime(2026, 7, 18, 9, 45, tzinfo=timezone.utc)
    assert announcement.url == "https://www.bseindia.com/xml-data/corpfiling/AttachLive/INFY_18072026.pdf"


def test_normalize_official_announcements_deduplicates_and_rejects_unknown_source():
    payloads = [
        {
            "SYMBOL": "TCS",
            "NEWSSUB": "TCS wins contract",
            "DissemDT": "18/07/2026 10:00:00",
            "NEWSID": "duplicate-id",
        },
        {
            "SYMBOL": "TCS",
            "NEWSSUB": "TCS wins contract",
            "DissemDT": "18/07/2026 10:00:00",
            "NEWSID": "duplicate-id",
        },
    ]

    announcements = normalize_official_announcements("bse", payloads)

    assert len(announcements) == 1
    assert announcements[0].symbol == "TCS"

    with pytest.raises(ValueError, match="Unsupported announcement source"):
        normalize_official_announcements("other", payloads)


def test_parse_nse_rss_uses_symbol_from_category_or_title():
    rss = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>RELIANCE: Disclosure under Regulation 30 - acquisition update</title>
        <link>https://www.nseindia.com/corporate/reliance.pdf</link>
        <guid>rss-1</guid>
        <pubDate>Sat, 18 Jul 2026 10:30:00 GMT</pubDate>
      </item>
      <item>
        <title>Dividend announcement</title>
        <category>HDFCBANK</category>
        <link>https://www.nseindia.com/corporate/hdfc.pdf</link>
        <guid>rss-2</guid>
        <pubDate>Sat, 18 Jul 2026 11:30:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    announcements = parse_nse_rss(rss)

    assert [item.symbol for item in announcements] == ["RELIANCE", "HDFCBANK"]
    assert announcements[0].category == AnnouncementCategory.CORPORATE_ACTION
    assert announcements[1].category == AnnouncementCategory.DIVIDEND


def test_fetch_nse_rss_announcements_uses_official_rss_fetch_shape(monkeypatch):
    class Response:
        status_code = 200
        text = """<rss><channel><item>
        <title>MARUTI: Board approves buyback</title>
        <guid>rss-3</guid>
        <pubDate>Sat, 18 Jul 2026 12:30:00 GMT</pubDate>
        </item></channel></rss>"""

    calls = []

    def fake_get(url, headers, timeout):
        calls.append((url, headers, timeout))
        return Response()

    monkeypatch.setattr("agent.data.announcement_sources.requests.get", fake_get)

    announcements = fetch_nse_rss_announcements("https://www.nseindia.com/rss/corporate.xml")

    assert announcements[0].symbol == "MARUTI"
    assert calls[0][0] == "https://www.nseindia.com/rss/corporate.xml"
    assert "User-Agent" in calls[0][1]
    assert calls[0][2] == 15


def test_fetch_nse_rss_announcements_rejects_http_errors(monkeypatch):
    class Response:
        status_code = 503
        text = ""

    monkeypatch.setattr("agent.data.announcement_sources.requests.get", lambda url, headers, timeout: Response())

    with pytest.raises(AnnouncementSourceError, match="HTTP 503"):
        fetch_nse_rss_announcements("https://www.nseindia.com/rss/corporate.xml")


def test_parse_source_timestamp_formats_and_source_urls_are_tracked():
    assert parse_source_timestamp("18-Jul-2026") == datetime(2026, 7, 18, tzinfo=timezone.utc)
    assert parse_source_timestamp("2026-07-18T12:00:00Z") == datetime(2026, 7, 18, 12, tzinfo=timezone.utc)

    assert "nseindia.com" in NSE_CORPORATE_FILINGS_URL
    assert "nseindia.com" in NSE_RSS_FEEDS_URL
    assert "bseindia.com" in BSE_CORPORATE_FILINGS_URL
