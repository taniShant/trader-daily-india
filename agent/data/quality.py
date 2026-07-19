from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from agent.contracts.market import OHLCVBar, Quote


@dataclass(frozen=True)
class DataQualityResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)

    def fail_closed_reason(self) -> str:
        return "; ".join(self.reasons) if self.reasons else "data quality rejected"


@dataclass(frozen=True)
class SourceQualityResult:
    passed: bool
    score: float
    reasons: list[str] = field(default_factory=list)
    source_count: int = 0
    stale_count: int = 0
    unavailable_count: int = 0
    simulated_count: int = 0
    live_trade_blocked: bool = False

    def fail_closed_reason(self) -> str:
        return "; ".join(self.reasons) if self.reasons else "source quality rejected"

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "reasons": list(self.reasons),
            "source_count": self.source_count,
            "stale_count": self.stale_count,
            "unavailable_count": self.unavailable_count,
            "simulated_count": self.simulated_count,
            "live_trade_blocked": self.live_trade_blocked,
        }


def check_quote_quality(
    quote: Quote,
    *,
    now: datetime | None = None,
    max_age_seconds: int = 300,
    require_volume: bool = False,
) -> DataQualityResult:
    reasons: list[str] = []
    current_time = _as_utc(now or datetime.now(timezone.utc))
    quote_time = _as_utc(quote.timestamp)

    if quote_time > current_time + timedelta(seconds=5):
        reasons.append("quote timestamp is in the future")
    if current_time - quote_time > timedelta(seconds=max_age_seconds):
        reasons.append("stale quote")
    if quote.ltp <= 0:
        reasons.append("invalid quote price")
    if quote.high is not None and quote.low is not None and quote.high < quote.low:
        reasons.append("invalid quote high/low range")
    if require_volume and (quote.volume is None or quote.volume <= 0):
        reasons.append("missing quote volume")

    return DataQualityResult(passed=not reasons, reasons=reasons)


def check_ohlcv_quality(
    bars: list[OHLCVBar],
    *,
    symbol: str | None = None,
    interval: str | None = None,
    now: datetime | None = None,
    max_last_bar_age_seconds: int | None = None,
    min_bars: int = 1,
    require_nonzero_volume: bool = True,
) -> DataQualityResult:
    reasons: list[str] = []
    if len(bars) < min_bars:
        reasons.append("missing candles")
        return DataQualityResult(passed=False, reasons=reasons)

    if symbol is not None:
        mismatched = {bar.symbol for bar in bars if bar.symbol != symbol}
        if mismatched:
            reasons.append("symbol mismatch")

    if interval is not None:
        mismatched_intervals = {bar.interval for bar in bars if bar.interval != interval}
        if mismatched_intervals:
            reasons.append("interval mismatch")

    previous_timestamp: datetime | None = None
    for bar in bars:
        if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
            reasons.append("invalid candle price")
        if bar.high < bar.low:
            reasons.append("invalid candle high/low range")
        if not (bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high):
            reasons.append("candle price outside high/low")
        if require_nonzero_volume and bar.volume <= 0:
            reasons.append("zero volume candle")

        bar_time = _as_utc(bar.timestamp)
        if previous_timestamp is not None and bar_time <= previous_timestamp:
            reasons.append("candles out of order")
        previous_timestamp = bar_time

    if max_last_bar_age_seconds is not None:
        current_time = _as_utc(now or datetime.now(timezone.utc))
        last_bar_time = _as_utc(bars[-1].timestamp)
        if current_time - last_bar_time > timedelta(seconds=max_last_bar_age_seconds):
            reasons.append("stale candle")
        if last_bar_time > current_time + timedelta(seconds=5):
            reasons.append("candle timestamp is in the future")

    return DataQualityResult(passed=not reasons, reasons=sorted(set(reasons)))


def raise_if_failed(result: DataQualityResult) -> None:
    if not result.passed:
        raise ValueError(result.fail_closed_reason())


def check_source_quality(
    *,
    global_news: list[dict[str, Any]] | None = None,
    indian_news: list[dict[str, Any]] | None = None,
    company_news: list[dict[str, Any]] | None = None,
    announcements: list[Any] | None = None,
    regulatory_events: list[Any] | None = None,
    now: datetime | None = None,
    max_news_age_minutes: int = 30,
    max_announcement_age_minutes: int = 15,
    max_regulatory_age_minutes: int = 15,
    require_official_events: bool = True,
) -> SourceQualityResult:
    """Score market-intelligence freshness and reliability for live-readiness gates."""
    current_time = _as_utc(now or datetime.now(timezone.utc))
    reasons: list[str] = []
    source_count = 0
    stale_count = 0
    unavailable_count = 0
    simulated_count = 0

    for label, items, max_age in [
        ("global_news", global_news or [], max_news_age_minutes),
        ("indian_news", indian_news or [], max_news_age_minutes),
        ("company_news", company_news or [], max_news_age_minutes),
    ]:
        result = _check_items(label, items, current_time, timedelta(minutes=max_age))
        source_count += result["source_count"]
        stale_count += result["stale_count"]
        unavailable_count += result["unavailable_count"]
        simulated_count += result["simulated_count"]
        reasons.extend(result["reasons"])

    for label, items, max_age in [
        ("announcements", announcements or [], max_announcement_age_minutes),
        ("regulatory_events", regulatory_events or [], max_regulatory_age_minutes),
    ]:
        result = _check_items(label, items, current_time, timedelta(minutes=max_age))
        source_count += result["source_count"]
        stale_count += result["stale_count"]
        unavailable_count += result["unavailable_count"]
        simulated_count += result["simulated_count"]
        reasons.extend(result["reasons"])

    if require_official_events and not announcements:
        reasons.append("missing official announcements")
        unavailable_count += 1
    if require_official_events and not regulatory_events:
        reasons.append("missing regulatory events")
        unavailable_count += 1

    penalty = stale_count * 0.15 + unavailable_count * 0.25 + simulated_count * 0.35
    score = round(max(0.0, min(1.0, 1.0 - penalty)), 4)
    live_trade_blocked = bool(unavailable_count or simulated_count or score < 0.7)
    passed = not live_trade_blocked and not stale_count

    return SourceQualityResult(
        passed=passed,
        score=score,
        reasons=sorted(set(reasons)),
        source_count=source_count,
        stale_count=stale_count,
        unavailable_count=unavailable_count,
        simulated_count=simulated_count,
        live_trade_blocked=live_trade_blocked,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _check_items(label: str, items: list[Any], now: datetime, max_age: timedelta) -> dict[str, Any]:
    reasons: list[str] = []
    source_count = 0
    stale_count = 0
    unavailable_count = 0
    simulated_count = 0

    for item in items:
        source_count += 1
        mode = _field(item, "source_mode")
        status = _field(item, "source_status")
        if mode == "unavailable" or "unavailable" in str(status):
            unavailable_count += 1
            reasons.append(f"{label} unavailable")
        if mode == "simulated" or status == "simulated":
            simulated_count += 1
            reasons.append(f"{label} simulated")

        timestamp = _timestamp(item)
        if timestamp is None:
            stale_count += 1
            reasons.append(f"{label} missing timestamp")
            continue
        if now - timestamp > max_age:
            stale_count += 1
            reasons.append(f"{label} stale")
        if timestamp > now + timedelta(seconds=5):
            stale_count += 1
            reasons.append(f"{label} timestamp is in the future")

    return {
        "reasons": reasons,
        "source_count": source_count,
        "stale_count": stale_count,
        "unavailable_count": unavailable_count,
        "simulated_count": simulated_count,
    }


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def _timestamp(item: Any) -> datetime | None:
    value = _field(item, "published_at") or _field(item, "timestamp")
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str):
        try:
            return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None
