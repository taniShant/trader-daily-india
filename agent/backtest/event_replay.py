from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.contracts.signals import TradeSignal
from agent.data.company_announcements import CompanyAnnouncement, parse_company_announcements
from agent.data.quality import SourceQualityResult, check_source_quality
from agent.data.regulatory_events import RegulatoryEvent, parse_regulatory_events
from agent.signals.scorer import score_signal
from agent.signals.sentiment import SentimentFeatures, compute_sentiment_features
from agent.signals.technical import TechnicalFeatures


@dataclass(frozen=True)
class EventReplayCase:
    case_id: str
    symbol: str
    replay_at: datetime
    description: str
    global_context: dict[str, Any] = field(default_factory=dict)
    indian_news: list[dict[str, Any]] = field(default_factory=list)
    company_news: list[dict[str, Any]] = field(default_factory=list)
    announcement_payloads: list[dict[str, Any]] = field(default_factory=list)
    regulatory_payloads: list[dict[str, Any]] = field(default_factory=list)
    technical: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EventReplayFinding:
    case_id: str
    symbol: str
    action: str
    confidence: int
    source_quality: SourceQualityResult
    signal: TradeSignal
    announcements: list[CompanyAnnouncement]
    regulatory_events: list[RegulatoryEvent]
    matched_expectations: bool
    expectation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "symbol": self.symbol,
            "action": self.action,
            "confidence": self.confidence,
            "source_quality": self.source_quality.to_dict(),
            "signal_reasons": list(self.signal.reasons),
            "announcement_titles": [item.title for item in self.announcements],
            "regulatory_titles": [item.title for item in self.regulatory_events],
            "matched_expectations": self.matched_expectations,
            "expectation_errors": list(self.expectation_errors),
        }


@dataclass(frozen=True)
class EventReplayReport:
    findings: list[EventReplayFinding]

    @property
    def passed(self) -> bool:
        return all(finding.matched_expectations for finding in self.findings)

    def to_markdown(self) -> str:
        lines = [
            "# Market Intelligence Event Replay",
            "",
            "This report replays deterministic high-impact event cases through the source-quality, sentiment, and signal-scoring path.",
            "",
            "| Case | Symbol | Action | Confidence | Source score | Result | Key reasons |",
            "| --- | --- | --- | ---: | ---: | --- | --- |",
        ]
        for finding in self.findings:
            result = "pass" if finding.matched_expectations else "fail"
            reasons = ", ".join(finding.signal.reasons[:6]) or "-"
            lines.append(
                f"| {finding.case_id} | {finding.symbol} | {finding.action} | "
                f"{finding.confidence} | {finding.source_quality.score:.2f} | {result} | {reasons} |"
            )
        return "\n".join(lines) + "\n"


def load_event_replay_cases(path: str | Path) -> list[EventReplayCase]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        EventReplayCase(
            case_id=str(item["case_id"]),
            symbol=str(item["symbol"]),
            replay_at=_parse_time(item["replay_at"]),
            description=str(item.get("description") or ""),
            global_context=dict(item.get("global_context") or {}),
            indian_news=list(item.get("indian_news") or []),
            company_news=list(item.get("company_news") or []),
            announcement_payloads=list(item.get("announcements") or []),
            regulatory_payloads=list(item.get("regulatory_events") or []),
            technical=dict(item.get("technical") or {}),
            expected=dict(item.get("expected") or {}),
        )
        for item in payload.get("cases", [])
    ]


def run_event_replay(cases: list[EventReplayCase]) -> EventReplayReport:
    findings = [_run_case(case) for case in cases]
    return EventReplayReport(findings=findings)


def _run_case(case: EventReplayCase) -> EventReplayFinding:
    announcements = parse_company_announcements(case.announcement_payloads)
    regulatory_events = parse_regulatory_events(case.regulatory_payloads)
    source_quality = check_source_quality(
        global_news=[case.global_context] if case.global_context else [],
        indian_news=case.indian_news,
        company_news=case.company_news,
        announcements=announcements,
        regulatory_events=regulatory_events,
        now=case.replay_at,
        require_official_events=True,
    )
    sentiment = compute_sentiment_features(
        global_context=case.global_context,
        indian_news=case.indian_news,
        company_news=case.company_news,
        announcements=announcements,
        regulatory_events=regulatory_events,
        source_quality=source_quality,
    )
    signal = score_signal(
        symbol=case.symbol,
        technical=_technical_features(case.symbol, case.technical),
        sentiment=sentiment,
    )
    errors = _expectation_errors(case.expected, signal, source_quality, announcements, regulatory_events)
    return EventReplayFinding(
        case_id=case.case_id,
        symbol=case.symbol,
        action=str(signal.action),
        confidence=signal.confidence,
        source_quality=source_quality,
        signal=signal,
        announcements=announcements,
        regulatory_events=regulatory_events,
        matched_expectations=not errors,
        expectation_errors=errors,
    )


def _expectation_errors(
    expected: dict[str, Any],
    signal: TradeSignal,
    source_quality: SourceQualityResult,
    announcements: list[CompanyAnnouncement],
    regulatory_events: list[RegulatoryEvent],
) -> list[str]:
    errors: list[str] = []
    if "action" in expected and str(signal.action) != expected["action"]:
        errors.append(f"expected action {expected['action']}, got {signal.action}")
    if "live_trade_blocked" in expected and source_quality.live_trade_blocked is not bool(expected["live_trade_blocked"]):
        errors.append("source quality block expectation mismatch")
    for reason in expected.get("reason_contains", []):
        if not any(reason in signal_reason for signal_reason in signal.reasons):
            errors.append(f"missing signal reason containing {reason!r}")
    for category in expected.get("announcement_categories", []):
        if category not in {str(item.category) for item in announcements}:
            errors.append(f"missing announcement category {category!r}")
    for category in expected.get("regulatory_categories", []):
        if category not in {str(item.category) for item in regulatory_events}:
            errors.append(f"missing regulatory category {category!r}")
    return errors


def _technical_features(symbol: str, payload: dict[str, Any]) -> TechnicalFeatures:
    trend = str(payload.get("trend_bias") or "bullish")
    close = float(payload.get("close", 1000))
    return TechnicalFeatures(
        symbol=symbol,
        close=close,
        vwap=float(payload.get("vwap", close - 5 if trend == "bullish" else close + 5)),
        rsi=float(payload.get("rsi", 60 if trend == "bullish" else 40)),
        macd=float(payload.get("macd", 2 if trend == "bullish" else -2)),
        macd_signal=float(payload.get("macd_signal", 1 if trend == "bullish" else -1)),
        atr=float(payload.get("atr", max(close * 0.01, 1))),
        relative_volume=float(payload.get("relative_volume", 1.2)),
        opening_range_high=float(payload.get("opening_range_high", close + 10)),
        opening_range_low=float(payload.get("opening_range_low", close - 10)),
        previous_high=float(payload.get("previous_high", close + 8)),
        previous_low=float(payload.get("previous_low", close - 8)),
        trend_bias=trend,
    )


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
