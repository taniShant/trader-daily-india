from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from agent.contracts.signals import RiskLevel, SignalAction, TradeSignal
from agent.signals.derivatives import DerivativesFeatures
from agent.signals.sentiment import SentimentFeatures
from agent.signals.technical import TechnicalFeatures


@dataclass(frozen=True)
class SignalScore:
    action: SignalAction
    confidence: int
    score: float
    reasons: list[str]
    risk_level: RiskLevel


def score_signal(
    *,
    symbol: str,
    technical: TechnicalFeatures,
    sentiment: SentimentFeatures,
    derivatives: DerivativesFeatures | None = None,
) -> TradeSignal:
    score, reasons = _weighted_score(technical, sentiment, derivatives)
    action = SignalAction.BUY if score >= 0.35 else SignalAction.SELL if score <= -0.35 else SignalAction.HOLD
    if sentiment.live_trade_blocked:
        action = SignalAction.HOLD
        reasons.append("source_quality_block")
        reasons.extend(sentiment.source_quality_reasons or [])
    confidence = min(95, max(0, int(abs(score) * 100)))
    if sentiment.source_quality_score < 1.0:
        confidence = int(confidence * sentiment.source_quality_score)
    if sentiment.live_trade_blocked:
        confidence = 0
    risk_level = _risk_level(technical, sentiment, derivatives)
    if sentiment.live_trade_blocked:
        risk_level = RiskLevel.HIGH
    raw_features: dict[str, Any] = {
        "technical": technical.to_dict(),
        "sentiment": sentiment.to_dict(),
        "source_quality": {
            "score": sentiment.source_quality_score,
            "reasons": sentiment.source_quality_reasons or [],
            "live_trade_blocked": sentiment.live_trade_blocked,
        },
    }
    if derivatives is not None:
        raw_features["derivatives"] = derivatives.to_dict()

    common = {
        "signal_id": f"{symbol}-{datetime.now(timezone.utc).isoformat()}",
        "symbol": symbol,
        "action": action,
        "confidence": confidence,
        "generated_at": datetime.now(timezone.utc),
        "risk_level": risk_level,
        "sentiment_score": sentiment.combined_score,
        "reasons": reasons,
        "raw_features": raw_features,
    }
    if action == SignalAction.HOLD:
        return TradeSignal(**common)

    entry = Decimal(str(technical.close))
    atr = Decimal(str(max(technical.atr, technical.close * 0.005)))
    if action == SignalAction.BUY:
        return TradeSignal(
            **common,
            entry_price=entry,
            stop_loss=entry - atr,
            target_price=entry + (atr * Decimal("1.8")),
            holding_window_minutes=30,
        )
    return TradeSignal(
        **common,
        entry_price=entry,
        stop_loss=entry + atr,
        target_price=entry - (atr * Decimal("1.8")),
        holding_window_minutes=30,
    )


def _weighted_score(
    technical: TechnicalFeatures,
    sentiment: SentimentFeatures,
    derivatives: DerivativesFeatures | None,
) -> tuple[float, list[str]]:
    technical_score = _bias_score(technical.trend_bias)
    sentiment_score = sentiment.combined_score
    derivative_score = _bias_score(derivatives.bias) if derivatives and derivatives.available else 0.0
    score = round(technical_score * 0.55 + sentiment_score * 0.30 + derivative_score * 0.15, 4)
    reasons = [f"technical:{technical.trend_bias}", f"sentiment:{sentiment.bias}"]
    if derivatives is not None:
        reasons.append(f"derivatives:{derivatives.bias}")
    reasons.extend(sentiment.reasons[:3])
    return score, reasons


def _bias_score(value: str) -> float:
    if value == "bullish":
        return 1.0
    if value == "bearish":
        return -1.0
    return 0.0


def _risk_level(
    technical: TechnicalFeatures,
    sentiment: SentimentFeatures,
    derivatives: DerivativesFeatures | None,
) -> RiskLevel:
    if technical.atr / technical.close > 0.04 or abs(sentiment.combined_score) > 0.75:
        return RiskLevel.HIGH
    if derivatives and derivatives.volatility_bias == "high":
        return RiskLevel.HIGH
    if technical.atr / technical.close > 0.02:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW
