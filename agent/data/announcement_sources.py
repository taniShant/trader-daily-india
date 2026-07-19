from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from typing import Any, Iterable
from urllib.parse import urljoin
from xml.etree import ElementTree

import requests

from agent.data.company_announcements import CompanyAnnouncement, parse_company_announcement
from agent.data.symbols import canonical_symbol


NSE_CORPORATE_FILINGS_URL = "https://www.nseindia.com/companies-listing/corporate-filings-application?id=allAnnouncements"
NSE_RSS_FEEDS_URL = "https://www.nseindia.com/static/rss-feed"
BSE_CORPORATE_FILINGS_URL = "https://www.bseindia.com/corporates/ann.html"


class AnnouncementSourceError(RuntimeError):
    """Raised when an official announcement source cannot be read safely."""


def normalize_nse_announcement(payload: dict[str, Any]) -> CompanyAnnouncement:
    """Normalize one NSE corporate-announcement payload into the canonical model."""
    title = _first_text(
        payload,
        "title",
        "headline",
        "subject",
        "desc",
        "description",
        "sm_name",
        "attchmntText",
    )
    symbol = _first_text(payload, "symbol", "symb", "SYMBOL", "ticker")
    published_at = _first_text(payload, "published_at", "timestamp", "broadcastDate", "an_dt", "sort_date", "dt")
    url = _first_text(payload, "url", "link", "attchmntFile", "attachment", "file_url")
    announcement_id = _first_text(payload, "announcement_id", "ann_id", "seq_id", "seqId", "id")

    return parse_company_announcement(
        {
            "announcement_id": announcement_id or _stable_source_id("NSE", symbol, title, published_at),
            "symbol": symbol,
            "title": title,
            "source": "NSE",
            "published_at": parse_source_timestamp(published_at),
            "url": _absolute_url(url, "https://www.nseindia.com/"),
            "raw": payload,
        }
    )


def normalize_bse_announcement(payload: dict[str, Any]) -> CompanyAnnouncement:
    """Normalize one BSE corporate-announcement payload into the canonical model."""
    title = _first_text(
        payload,
        "title",
        "headline",
        "HEADLINE",
        "NEWSSUB",
        "SUBJECT",
        "subject",
        "announcement",
    )
    symbol = _first_text(payload, "symbol", "SYMBOL", "scrip_symbol", "SCRIP_SYMBOL", "SCRIP_CD_NAME")
    published_at = _first_text(payload, "published_at", "timestamp", "DissemDT", "NEWS_DT", "DT_TM", "date")
    url = _first_text(payload, "url", "link", "ATTACHMENTNAME", "NSURL", "attachment")
    announcement_id = _first_text(payload, "announcement_id", "NEWSID", "news_id", "id")

    return parse_company_announcement(
        {
            "announcement_id": announcement_id or _stable_source_id("BSE", symbol, title, published_at),
            "symbol": symbol,
            "title": title,
            "source": "BSE",
            "published_at": parse_source_timestamp(published_at),
            "url": _absolute_url(url, "https://www.bseindia.com/"),
            "raw": payload,
        }
    )


def normalize_official_announcements(source: str, payloads: Iterable[dict[str, Any]]) -> list[CompanyAnnouncement]:
    source_key = source.strip().lower()
    normalizer = {
        "nse": normalize_nse_announcement,
        "bse": normalize_bse_announcement,
    }.get(source_key)
    if normalizer is None:
        raise ValueError(f"Unsupported announcement source: {source!r}")

    announcements: list[CompanyAnnouncement] = []
    seen: set[str] = set()
    for payload in payloads:
        announcement = normalizer(payload)
        if announcement.announcement_id in seen:
            continue
        seen.add(announcement.announcement_id)
        announcements.append(announcement)
    return announcements


def parse_nse_rss(xml_text: str) -> list[CompanyAnnouncement]:
    """Parse NSE RSS XML items that include a symbol in their title or category."""
    root = ElementTree.fromstring(xml_text)
    items = root.findall(".//item")
    payloads: list[dict[str, Any]] = []
    for item in items:
        title = _xml_text(item, "title")
        symbol = _xml_text(item, "symbol") or _xml_text(item, "category") or _symbol_from_title(title)
        if not symbol:
            continue
        payloads.append(
            {
                "title": title,
                "symbol": symbol,
                "published_at": _xml_text(item, "pubDate"),
                "url": _xml_text(item, "link"),
                "announcement_id": _xml_text(item, "guid"),
            }
        )
    return normalize_official_announcements("nse", payloads)


def fetch_nse_rss_announcements(url: str, *, timeout_seconds: int = 15) -> list[CompanyAnnouncement]:
    """Fetch and parse an NSE RSS announcement feed."""
    response = requests.get(url, headers=_source_headers(), timeout=timeout_seconds)
    if response.status_code >= 400:
        raise AnnouncementSourceError(f"NSE RSS returned HTTP {response.status_code}")
    return parse_nse_rss(response.text)


def parse_source_timestamp(value: Any) -> datetime:
    """Parse timestamp formats commonly found in exchange payloads."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value is None or str(value).strip() == "":
        return datetime.now(timezone.utc)

    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    for fmt in [
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y",
        "%d %b %Y %H:%M:%S",
        "%d %b %Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
    ]:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        parsed = parsedate_to_datetime(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass

    raise ValueError(f"Unsupported announcement timestamp: {value!r}")


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _stable_source_id(source: str, symbol: str, title: str, published_at: Any) -> str:
    digest = sha256(f"{source}|{canonical_symbol(symbol)}|{title}|{published_at}".encode("utf-8")).hexdigest()[:16]
    return f"{source.lower()}-{digest}"


def _absolute_url(value: str, base_url: str) -> str | None:
    if not value:
        return None
    return urljoin(base_url, value)


def _xml_text(item: ElementTree.Element, tag: str) -> str:
    element = item.find(tag)
    return element.text.strip() if element is not None and element.text else ""


def _symbol_from_title(title: str) -> str:
    if not title:
        return ""
    first_token = title.split(":", 1)[0].strip()
    if first_token and first_token.replace("-", "").replace("&", "").isalnum() and len(first_token) <= 20:
        return first_token
    return ""


def _source_headers() -> dict[str, str]:
    return {
        "User-Agent": "trader-daily-india/1.0 market-intelligence-audit",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
