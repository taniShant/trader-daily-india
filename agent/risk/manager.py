from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from agent.contracts.execution import OrderSide, OrderType
from agent.contracts.risk import RiskDecision, RiskDecisionStatus
from agent.contracts.signals import SignalAction, TradeSignal

from .rules import (
    calculate_quantity,
    confidence_too_low,
    daily_loss_breached,
    high_risk_signal,
    non_actionable_signal,
)


@dataclass(frozen=True)
class RiskLimits:
    capital: Decimal
    max_daily_loss_percent: Decimal
    max_position_size_percent: Decimal
    min_confidence: int
    max_quantity_per_order: int = 50

    @property
    def max_daily_loss_amount(self) -> Decimal:
        return self.capital * (self.max_daily_loss_percent / Decimal("100"))


@dataclass(frozen=True)
class RiskState:
    daily_pnl: Decimal = Decimal("0")
    consecutive_losses: int = 0
    new_trades_allowed: bool = True


class RiskManager:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def evaluate(self, signal: TradeSignal, state: RiskState | None = None) -> RiskDecision:
        state = state or RiskState()
        reasons = self._rejection_reasons(signal, state)

        if reasons:
            return RiskDecision(
                decision_id=self._decision_id(signal),
                signal_id=signal.signal_id,
                status=RiskDecisionStatus.REJECTED,
                decided_at=datetime.now(timezone.utc),
                reasons=reasons,
                max_loss_amount=self.limits.max_daily_loss_amount,
            )

        quantity = calculate_quantity(
            capital=self.limits.capital,
            max_position_size_percent=self.limits.max_position_size_percent,
            confidence=signal.confidence,
            entry_price=signal.entry_price,
            max_quantity=self.limits.max_quantity_per_order,
        )
        if quantity <= 0:
            return RiskDecision(
                decision_id=self._decision_id(signal),
                signal_id=signal.signal_id,
                status=RiskDecisionStatus.REJECTED,
                decided_at=datetime.now(timezone.utc),
                reasons=["position size rounds to zero"],
                max_loss_amount=self.limits.max_daily_loss_amount,
            )

        return RiskDecision(
            decision_id=self._decision_id(signal),
            signal_id=signal.signal_id,
            status=RiskDecisionStatus.APPROVED,
            decided_at=datetime.now(timezone.utc),
            reasons=[],
            approved_quantity=quantity,
            approved_price=signal.entry_price,
            side=self._order_side(signal),
            order_type=OrderType.LIMIT,
            max_loss_amount=self.limits.max_daily_loss_amount,
        )

    def _rejection_reasons(self, signal: TradeSignal, state: RiskState) -> list[str]:
        reasons = []
        if non_actionable_signal(signal):
            reasons.append("signal action is HOLD")
        if not state.new_trades_allowed:
            reasons.append("new-trade cutoff reached")
        if daily_loss_breached(state.daily_pnl, self.limits.max_daily_loss_amount):
            reasons.append("daily loss limit breached")
        if state.consecutive_losses >= 3:
            reasons.append("consecutive loss limit breached")
        if confidence_too_low(signal, self.limits.min_confidence):
            reasons.append(
                f"confidence {signal.confidence}% below minimum {self.limits.min_confidence}%"
            )
        if high_risk_signal(signal):
            reasons.append("risk level HIGH")
        return reasons

    @staticmethod
    def _order_side(signal: TradeSignal) -> OrderSide:
        if signal.action == SignalAction.BUY:
            return OrderSide.BUY
        return OrderSide.SELL

    @staticmethod
    def _decision_id(signal: TradeSignal) -> str:
        return f"risk-{signal.signal_id}-{uuid4().hex[:12]}"
