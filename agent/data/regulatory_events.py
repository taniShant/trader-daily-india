from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import StrEnum
from hashlib import sha256
import re
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree

import requests
from pydantic import BaseModel, ConfigDict, Field


RBI_RSS_PAGE_URL = "https://www.rbi.org.in/Scripts/rss.aspx"
RBI_PRESS_RELEASES_RSS_URL = "https://www.rbi.org.in/pressrelease_rss.xml"
RBI_NOTIFICATIONS_RSS_URL = "https://www.rbi.org.in/notifications_rss.xml"
SEBI_RSS_PAGE_URL = "https://www.sebi.gov.in/rss.html"
SEBI_RSS_URL = "https://www.sebi.gov.in/sebirss.xml"


class RegulatorySource(StrEnum):
    RBI = "RBI"
    SEBI = "SEBI"


class RegulatoryEventCategory(StrEnum):
    MONETARY_POLICY = "monetary_policy"
    LIQUIDITY = "liquidity"
    BANKING_REGULATION = "banking_regulation"
    MARKET_STRUCTURE = "market_structure"
    ENFORCEMENT = "enforcement"
    CIRCULAR = "circular"
    PRESS_RELEASE = "press_release"
    SPEECH = "speech"
    OTHER = "other"


class RegulatoryImpact(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    CAUTION = "caution"


class RegulatoryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    source: RegulatorySource
    title: str = Field(min_length=1)
    category: RegulatoryEventCategory
    impact: RegulatoryImpact
    impact_score: float = Field(ge=-1, le=1)
    published_at: datetime
    url: str | None = None
    summary: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class RegulatorySourceError(RuntimeError):
    """Raised when an official regulatory source cannot be read safely."""


def parse_regulatory_event(payload: dict[str, Any]) -> RegulatoryEvent:
    source = RegulatorySource(str(_first_text(payload, "source", "authority")).upper())
    title = _first_text(payload, "title", "headline", "subject")
    if not title:
        raise ValueError("regulatory event title is required")

    published_at = parse_regulatory_timestamp(_first_text(payload, "published_at", "timestamp", "date", "pubDate"))
    category = classify_regulatory_event(title, source=source, event_type=_first_text(payload, "type", "category"))
    impact = infer_regulatory_impact(title, category)
    event_id = _first_text(payload, "event_id", "id", "guid") or _stable_event_id(source, title, published_at)

    return RegulatoryEvent(
        event_id=event_id,
        source=source,
        title=title,
        category=category,
        impact=impact,
        impact_score=_impact_score(impact),
        published_at=published_at,
        url=_first_text(payload, "url", "link") or None,
        summary=_first_text(payload, "summary", "description") or None,
        raw=dict(payload),
    )


def parse_regulatory_events(payloads: list[dict[str, Any]]) -> list[RegulatoryEvent]:
    events: list[RegulatoryEvent] = []
    seen: set[str] = set()
    for payload in payloads:
        event = parse_regulatory_event(payload)
        if event.event_id in seen:
            continue
        seen.add(event.event_id)
        events.append(event)
    return events


def parse_regulatory_rss(xml_text: str, *, source: RegulatorySource | str) -> list[RegulatoryEvent]:
    source_value = RegulatorySource(str(source).upper())
    root = ElementTree.fromstring(xml_text)
    payloads: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = _xml_text(item, "title")
        if not title:
            continue
        payloads.append(
            {
                "source": source_value,
                "title": title,
                "summary": _xml_text(item, "description"),
                "published_at": _xml_text(item, "pubDate"),
                "url": _xml_text(item, "link"),
                "event_id": _xml_text(item, "guid"),
                "type": _xml_text(item, "category"),
            }
        )
    return parse_regulatory_events(payloads)


def fetch_regulatory_rss(
    url: str,
    *,
    source: RegulatorySource | str,
    timeout_seconds: int = 15,
) -> list[RegulatoryEvent]:
    response = requests.get(url, headers=_source_headers(), timeout=timeout_seconds)
    if response.status_code >= 400:
        raise RegulatorySourceError(f"{source} RSS returned HTTP {response.status_code}")
    return parse_regulatory_rss(response.text, source=source)


def classify_regulatory_event(
    title: str,
    *,
    source: RegulatorySource,
    event_type: str = "",
) -> RegulatoryEventCategory:
    text = f"{event_type} {title}".lower()
    if any(term in text for term in ["monetary policy", "mpc", "repo rate", "policy rate"]):
        return RegulatoryEventCategory.MONETARY_POLICY
    if any(term in text for term in ["liquidity", "variable rate", "vr r", "auction", "omo", "crr", "slr"]):
        return RegulatoryEventCategory.LIQUIDITY
    if any(term in text for term in ["bank", "nbfc", "payments bank", "co-operative bank"]):
        return RegulatoryEventCategory.BANKING_REGULATION
    if any(term in text for term in ["market structure", "derivatives", "settlement", "margin", "short selling"]):
        return RegulatoryEventCategory.MARKET_STRUCTURE
    if any(term in text for term in ["penalty", "order", "ban", "restrain", "enforcement", "fraud"]):
        return RegulatoryEventCategory.ENFORCEMENT
    if "circular" in text or event_type.lower() == "circulars":
        return RegulatoryEventCategory.CIRCULAR
    if "speech" in text:
        return RegulatoryEventCategory.SPEECH
    if "press release" in text or event_type.lower() == "press releases":
        return RegulatoryEventCategory.PRESS_RELEASE
    return RegulatoryEventCategory.PRESS_RELEASE if source == RegulatorySource.SEBI else RegulatoryEventCategory.OTHER


def infer_regulatory_impact(title: str, category: RegulatoryEventCategory) -> RegulatoryImpact:
    text = title.lower()
    if _contains_terms(text, ["penalty", "ban", "restrain", "fraud", "default", "caution"]):
        return RegulatoryImpact.CAUTION
    if _contains_terms(text, ["tighten", "increase crr", "hike", "withdraw liquidity"]):
        return RegulatoryImpact.NEGATIVE
    if _contains_terms(text, ["ease", "relaxation", "cut", "liquidity infusion", "fast-track"]):
        return RegulatoryImpact.POSITIVE
    if category in {RegulatoryEventCategory.ENFORCEMENT, RegulatoryEventCategory.MARKET_STRUCTURE}:
        return RegulatoryImpact.CAUTION
    return RegulatoryImpact.NEUTRAL


def parse_regulatory_timestamp(value: Any) -> datetime:
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
        "%b %d, %Y",
        "%d-%b-%Y",
        "%d-%b-%Y %H:%M:%S",
        "%d %b %Y",
        "%d %b %Y %H:%M:%S",
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M:%S",
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

    raise ValueError(f"Unsupported regulatory timestamp: {value!r}")


def regulatory_events_to_features(events: list[RegulatoryEvent]) -> dict[str, Any]:
    impact_score = round(sum(event.impact_score for event in events), 2)
    caution_count = sum(1 for event in events if event.impact == RegulatoryImpact.CAUTION)
    return {
        "regulatory_events": [
            {
                "event_id": event.event_id,
                "source": str(event.source),
                "title": event.title,
                "category": str(event.category),
                "impact": str(event.impact),
                "impact_score": event.impact_score,
                "published_at": event.published_at.isoformat(),
                "url": event.url,
            }
            for event in events
        ],
        "regulatory_event_count": len(events),
        "regulatory_caution_count": caution_count,
        "regulatory_net_impact_score": impact_score,
    }


def _impact_score(impact: RegulatoryImpact) -> float:
    if impact == RegulatoryImpact.POSITIVE:
        return 0.4
    if impact == RegulatoryImpact.NEGATIVE:
        return -0.4
    if impact == RegulatoryImpact.CAUTION:
        return -0.2
    return 0.0


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _xml_text(item: ElementTree.Element, tag: str) -> str:
    element = item.find(tag)
    return element.text.strip() if element is not None and element.text else ""


def _stable_event_id(source: RegulatorySource, title: str, published_at: datetime) -> str:
    digest = sha256(f"{source}|{title}|{published_at.isoformat()}".encode("utf-8")).hexdigest()[:16]
    return f"{source.lower()}-{digest}"


def _source_headers() -> dict[str, str]:
    return {
        "User-Agent": "trader-daily-india/1.0 regulatory-event-ingestion",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }


def _contains_terms(text: str, terms: list[str]) -> bool:
    for term in terms:
        pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            return True
    return False
