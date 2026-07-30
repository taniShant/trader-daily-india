from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from agent.contracts.execution import OrderRequest, OrderStatus
from agent.contracts.risk import RiskDecision, RiskDecisionStatus
from agent.contracts.signals import RiskLevel, SignalAction, TradeSignal
from agent.execution.broker import Broker
from agent.risk import RiskManager, RiskState
from agent.signals.technical import compute_technical_features

from .models import MicroTradeConfig, MicroTradePlan, MicroTradeSetup
from .setups import MicroSetupDetector


@dataclass(frozen=True)
class MicroTradeAttempt:
    symbol: str
    setup: MicroTradeSetup
    signal: TradeSignal | None = None
    risk_decision: RiskDecision | None = None
    order_status: OrderStatus | None = None
    skipped_reason: str | None = None

    @property
    def executed(self) -> bool:
        return self.order_status in {
            OrderStatus.SUBMITTED,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
        }


class MicroTradingEngine:
    """Fast deterministic 5-10 minute trading lane.

    The engine intentionally avoids LLM calls. It is designed to run from the
    market-hours loop only when explicitly enabled.
    """

    def __init__(
        self,
        *,
        market_data_provider: Any,
        broker: Broker,
        risk_manager: RiskManager,
        config: MicroTradeConfig | None = None,
        detector: MicroSetupDetector | None = None,
    ):
        self.market_data_provider = market_data_provider
        self.broker = broker
        self.risk_manager = risk_manager
        self.config = config or MicroTradeConfig()
        self.detector = detector or MicroSetupDetector(self.config)

    def scan_once(
        self,
        symbols: Iterable[str],
        *,
        risk_state: RiskState | None = None,
    ) -> list[MicroTradeAttempt]:
        if not self.config.enabled:
            return []

        attempts: list[MicroTradeAttempt] = []
        for symbol in list(symbols)[: self.config.max_symbols_per_cycle]:
            attempts.append(self.evaluate_symbol(symbol, risk_state=risk_state))
        return attempts

    def evaluate_symbol(
        self,
        symbol: str,
        *,
        risk_state: RiskState | None = None,
    ) -> MicroTradeAttempt:
        try:
            payload = self.market_data_provider.get_historical_data(
                symbol,
                days=self.config.lookback_days,
                interval=self.config.interval,
            )
            if payload.get("error"):
                setup = _hold_setup(symbol, f"market_data_unavailable:{payload['error']}")
                return MicroTradeAttempt(symbol=symbol, setup=setup, skipped_reason=setup.reasons[0])

            features = compute_technical_features(payload)
            setup = self.detector.detect(features)
        except Exception as exc:
            setup = _hold_setup(symbol, f"micro_setup_error:{exc}")
            return MicroTradeAttempt(symbol=symbol, setup=setup, skipped_reason=setup.reasons[0])

        if not setup.is_actionable:
            return MicroTradeAttempt(symbol=symbol, setup=setup, skipped_reason="no_actionable_micro_setup")

        signal_id = _signal_id(setup.symbol, setup.action)
        plan = self.detector.to_plan(setup, signal_id=signal_id)
        signal = self._to_signal(plan)
        risk_decision = self.risk_manager.evaluate(signal, risk_state)
        if risk_decision.status == RiskDecisionStatus.REJECTED:
            return MicroTradeAttempt(
                symbol=symbol,
                setup=setup,
                signal=signal,
                risk_decision=risk_decision,
                skipped_reason="; ".join(risk_decision.reasons),
            )

        order = self._to_order(plan, risk_decision)
        order_status = self.broker.place_order(order)
        return MicroTradeAttempt(
            symbol=symbol,
            setup=setup,
            signal=signal,
            risk_decision=risk_decision,
            order_status=order_status,
        )

    @staticmethod
    def _to_signal(plan: MicroTradePlan) -> TradeSignal:
        return TradeSignal(
            signal_id=plan.signal_id,
            symbol=plan.symbol,
            action=SignalAction.BUY if plan.side.value == "BUY" else SignalAction.SELL,
            confidence=plan.confidence,
            generated_at=datetime.now(timezone.utc),
            entry_price=plan.entry_price,
            stop_loss=plan.stop_loss,
            target_price=plan.target_price,
            holding_window_minutes=plan.max_hold_minutes,
            risk_level=RiskLevel.MEDIUM,
            sentiment_score=0.0,
            reasons=plan.reasons,
            raw_features={"micro_trade": True, **plan.features},
        )

    @staticmethod
    def _to_order(plan: MicroTradePlan, decision: RiskDecision) -> OrderRequest:
        return OrderRequest(
            client_order_id=f"{plan.signal_id}-{decision.decision_id}",
            signal_id=plan.signal_id,
            risk_decision_id=decision.decision_id,
            symbol=plan.symbol,
            side=decision.side,
            order_type=decision.order_type,
            quantity=decision.approved_quantity,
            price=decision.approved_price,
            stop_loss=plan.stop_loss,
            target_price=plan.target_price,
            requested_at=datetime.now(timezone.utc),
        )


def _hold_setup(symbol: str, reason: str) -> MicroTradeSetup:
    return MicroTradeSetup(
        symbol=symbol,
        action="HOLD",
        confidence=0,
        setup="micro_data_unavailable",
        entry_price=None,
        stop_loss=None,
        target_price=None,
        reasons=[reason],
    )


def _signal_id(symbol: str, action: str) -> str:
    return f"micro-{symbol}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}-{action}"
