from __future__ import annotations

from decimal import Decimal

from agent.contracts.signals import RiskLevel, SignalAction, TradeSignal


def daily_loss_breached(daily_pnl: Decimal, max_daily_loss_amount: Decimal) -> bool:
    return daily_pnl <= -abs(max_daily_loss_amount)


def confidence_too_low(signal: TradeSignal, minimum_confidence: int) -> bool:
    return signal.confidence < minimum_confidence


def high_risk_signal(signal: TradeSignal) -> bool:
    return signal.risk_level == RiskLevel.HIGH


def non_actionable_signal(signal: TradeSignal) -> bool:
    return signal.action == SignalAction.HOLD


def calculate_quantity(
    *,
    capital: Decimal,
    max_position_size_percent: Decimal,
    confidence: int,
    entry_price: Decimal,
    max_quantity: int,
) -> int:
    max_position_value = capital * (max_position_size_percent / Decimal("100"))
    confidence_scaled_value = max_position_value * (Decimal(confidence) / Decimal("100"))
    quantity = int(confidence_scaled_value / entry_price)
    return max(0, min(quantity, max_quantity))
