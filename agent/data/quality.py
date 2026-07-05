from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from agent.contracts.market import OHLCVBar, Quote


@dataclass(frozen=True)
class DataQualityResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)

    def fail_closed_reason(self) -> str:
        return "; ".join(self.reasons) if self.reasons else "data quality rejected"


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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
