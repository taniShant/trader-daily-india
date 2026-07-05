from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent.data.symbols import canonical_symbol, resolve_symbol


class AnnouncementCategory(StrEnum):
    RESULTS = "results"
    ORDER_WIN = "order_win"
    BOARD_MEETING = "board_meeting"
    DIVIDEND = "dividend"
    MANAGEMENT = "management"
    REGULATORY = "regulatory"
    CORPORATE_ACTION = "corporate_action"
    OTHER = "other"


class AnnouncementImpact(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class CompanyAnnouncement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    announcement_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    yahoo_symbol: str = Field(min_length=1)
    breeze_stock_code: str = Field(min_length=1)
    source: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: AnnouncementCategory
    impact: AnnouncementImpact
    impact_score: float = Field(ge=-1, le=1)
    published_at: datetime
    url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


def parse_company_announcement(payload: dict[str, Any]) -> CompanyAnnouncement:
    title = str(payload.get("title") or payload.get("headline") or "").strip()
    symbol = canonical_symbol(str(payload.get("symbol") or payload.get("stock") or ""))
    if not title:
        raise ValueError("announcement title is required")
    if not symbol:
        raise ValueError("announcement symbol is required")

    mapping = resolve_symbol(symbol)
    category = classify_announcement(title)
    impact = infer_impact(title, category)
    published_at = _parse_timestamp(payload.get("published_at") or payload.get("timestamp"))

    return CompanyAnnouncement(
        announcement_id=str(payload.get("announcement_id") or _announcement_id(mapping.canonical, title, published_at)),
        symbol=mapping.canonical,
        yahoo_symbol=mapping.yahoo,
        breeze_stock_code=mapping.breeze,
        source=str(payload.get("source") or "unknown"),
        title=title,
        category=category,
        impact=impact,
        impact_score=_impact_score(impact),
        published_at=published_at,
        url=payload.get("url"),
        raw=dict(payload),
    )


def parse_company_announcements(payloads: list[dict[str, Any]]) -> list[CompanyAnnouncement]:
    announcements = []
    seen_ids: set[str] = set()
    for payload in payloads:
        announcement = parse_company_announcement(payload)
        if announcement.announcement_id in seen_ids:
            continue
        seen_ids.add(announcement.announcement_id)
        announcements.append(announcement)
    return announcements


def announcements_to_event_features(announcements: list[CompanyAnnouncement]) -> dict[str, Any]:
    by_symbol: dict[str, dict[str, Any]] = {}
    for announcement in announcements:
        state = by_symbol.setdefault(
            announcement.symbol,
            {
                "symbol": announcement.symbol,
                "announcement_count": 0,
                "net_impact_score": 0.0,
                "categories": [],
                "latest_titles": [],
            },
        )
        state["announcement_count"] += 1
        state["net_impact_score"] += announcement.impact_score
        if announcement.category not in state["categories"]:
            state["categories"].append(announcement.category)
        state["latest_titles"].append(announcement.title)

    for state in by_symbol.values():
        state["net_impact_score"] = round(state["net_impact_score"], 2)
        state["categories"] = [str(category) for category in state["categories"]]
        state["latest_titles"] = state["latest_titles"][:5]

    return {"company_announcements": list(by_symbol.values())}


def classify_announcement(title: str) -> AnnouncementCategory:
    text = title.lower()
    if any(term in text for term in ["result", "earnings", "profit", "revenue", "quarter"]):
        return AnnouncementCategory.RESULTS
    if any(term in text for term in ["wins order", "order win", "contract", "deal", "agreement", "partnership"]):
        return AnnouncementCategory.ORDER_WIN
    if "board meeting" in text:
        return AnnouncementCategory.BOARD_MEETING
    if "dividend" in text:
        return AnnouncementCategory.DIVIDEND
    if any(term in text for term in ["resigns", "resignation", "appoints", "appointment", "ceo", "cfo"]):
        return AnnouncementCategory.MANAGEMENT
    if any(term in text for term in ["sebi", "rbi", "penalty", "notice", "regulatory"]):
        return AnnouncementCategory.REGULATORY
    if any(term in text for term in ["split", "bonus", "buyback", "merger", "acquisition"]):
        return AnnouncementCategory.CORPORATE_ACTION
    return AnnouncementCategory.OTHER


def infer_impact(title: str, category: AnnouncementCategory) -> AnnouncementImpact:
    text = title.lower()
    negative_terms = ["loss", "decline", "falls", "penalty", "notice", "resigns", "fraud", "default"]
    positive_terms = ["profit rises", "profit jumps", "wins", "order", "contract", "dividend", "buyback", "bonus"]
    if any(term in text for term in negative_terms):
        return AnnouncementImpact.NEGATIVE
    if any(term in text for term in positive_terms):
        return AnnouncementImpact.POSITIVE
    if category in {AnnouncementCategory.ORDER_WIN, AnnouncementCategory.DIVIDEND}:
        return AnnouncementImpact.POSITIVE
    return AnnouncementImpact.NEUTRAL


def _impact_score(impact: AnnouncementImpact) -> float:
    if impact == AnnouncementImpact.POSITIVE:
        return 0.5
    if impact == AnnouncementImpact.NEGATIVE:
        return -0.5
    return 0.0


def _parse_timestamp(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError(f"Unsupported announcement timestamp: {value!r}")


def _announcement_id(symbol: str, title: str, published_at: datetime) -> str:
    normalized_title = "-".join(title.lower().split())[:80]
    return f"{symbol}-{published_at.date()}-{normalized_title}"
