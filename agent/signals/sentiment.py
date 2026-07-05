from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.data.company_announcements import CompanyAnnouncement


@dataclass(frozen=True)
class SentimentFeatures:
    global_score: float
    indian_market_score: float
    company_news_score: float
    announcement_score: float
    combined_score: float
    event_count: int
    bias: str
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def compute_sentiment_features(
    *,
    global_context: dict[str, Any] | None = None,
    indian_news: list[dict[str, Any]] | None = None,
    company_news: list[dict[str, Any]] | None = None,
    announcements: list[CompanyAnnouncement] | None = None,
) -> SentimentFeatures:
    global_score = _global_score(global_context or {})
    indian_score = _news_score(indian_news or [])
    company_score = _news_score(company_news or [])
    announcement_score = _announcement_score(announcements or [])
    combined = round(
        global_score * 0.25
        + indian_score * 0.25
        + company_score * 0.30
        + announcement_score * 0.20,
        4,
    )
    reasons = _reasons(global_score, indian_score, company_score, announcement_score)
    return SentimentFeatures(
        global_score=global_score,
        indian_market_score=indian_score,
        company_news_score=company_score,
        announcement_score=announcement_score,
        combined_score=combined,
        event_count=len(indian_news or []) + len(company_news or []) + len(announcements or []),
        bias="bullish" if combined > 0.2 else "bearish" if combined < -0.2 else "neutral",
        reasons=reasons,
    )


def _global_score(context: dict[str, Any]) -> float:
    if "sentiment_score" in context:
        return _clamp(float(context["sentiment_score"]))
    sentiment = str(context.get("global_sentiment") or context.get("macro", {}).get("global_sentiment") or "").lower()
    if sentiment == "positive":
        return 0.4
    if sentiment == "negative":
        return -0.4
    return 0.0


def _news_score(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    total = 0.0
    for item in items:
        if "sentiment_score" in item:
            total += _clamp(float(item["sentiment_score"]))
            continue
        text = " ".join(str(item.get(key, "")) for key in ["title", "summary", "sentiment"]).lower()
        total += _lexical_score(text)
    return round(_clamp(total / len(items)), 4)


def _announcement_score(items: list[CompanyAnnouncement]) -> float:
    if not items:
        return 0.0
    return round(_clamp(sum(item.impact_score for item in items) / len(items)), 4)


def _lexical_score(text: str) -> float:
    positive = ["profit", "rises", "wins", "growth", "upgrade", "dividend", "buyback", "contract", "positive"]
    negative = ["loss", "falls", "penalty", "downgrade", "resigns", "fraud", "default", "negative"]
    score = 0
    score += sum(1 for word in positive if word in text)
    score -= sum(1 for word in negative if word in text)
    return _clamp(score / 3)


def _reasons(global_score: float, indian_score: float, company_score: float, announcement_score: float) -> list[str]:
    reasons = []
    for label, value in [
        ("global", global_score),
        ("indian_market", indian_score),
        ("company_news", company_score),
        ("announcements", announcement_score),
    ]:
        if abs(value) >= 0.2:
            reasons.append(f"{label}:{value:+.2f}")
    return reasons


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))
