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
    order: OrderRequest | None = None
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
        self._last_execution_at: dict[str, datetime] = {}

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
            stale_reason = self._stale_candle_reason(features)
            if stale_reason:
                setup = _hold_setup(symbol, stale_reason)
                return MicroTradeAttempt(symbol=symbol, setup=setup, skipped_reason=stale_reason)
            setup = self.detector.detect(features)
        except Exception as exc:
            setup = _hold_setup(symbol, f"micro_setup_error:{exc}")
            return MicroTradeAttempt(symbol=symbol, setup=setup, skipped_reason=setup.reasons[0])

        if not setup.is_actionable:
            return MicroTradeAttempt(symbol=symbol, setup=setup, skipped_reason="no_actionable_micro_setup")

        signal_id = _signal_id(setup.symbol, setup.action)
        plan = self.detector.to_plan(setup, signal_id=signal_id)
        position_attempt = self._handle_existing_position(plan, setup)
        if position_attempt is not None:
            return position_attempt

        cooldown_skip = self._cooldown_skip_reason(plan.symbol)
        if cooldown_skip:
            return MicroTradeAttempt(symbol=symbol, setup=setup, skipped_reason=cooldown_skip)

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

        live_stop_skip = self._live_stop_skip_reason(plan)
        if live_stop_skip:
            return MicroTradeAttempt(
                symbol=symbol,
                setup=setup,
                signal=signal,
                risk_decision=risk_decision,
                skipped_reason=live_stop_skip,
            )

        order = self._to_order(plan, risk_decision)
        order_status = self.broker.place_order(order)
        if order_status in {
            OrderStatus.SUBMITTED,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
        }:
            self._last_execution_at[plan.symbol] = datetime.now(timezone.utc)
        return MicroTradeAttempt(
            symbol=symbol,
            setup=setup,
            signal=signal,
            risk_decision=risk_decision,
            order=order,
            order_status=order_status,
        )

    def _stale_candle_reason(self, features) -> str | None:
        latest_timestamp = getattr(features, "latest_timestamp", None)
        if latest_timestamp is None:
            return "stale_or_missing_candle_timestamp"
        if latest_timestamp.tzinfo is None:
            latest_timestamp = latest_timestamp.replace(tzinfo=timezone.utc)

        age_seconds = (datetime.now(timezone.utc) - latest_timestamp.astimezone(timezone.utc)).total_seconds()
        if age_seconds < -60:
            return f"future_candle_timestamp:{latest_timestamp.isoformat()}"
        if age_seconds > self.config.max_candle_age_seconds:
            return f"stale_candle:{int(age_seconds)}s"
        return None

    def _live_stop_skip_reason(self, plan: MicroTradePlan) -> str | None:
        quote_fetcher = getattr(self.market_data_provider, "get_live_quote", None)
        if not callable(quote_fetcher):
            return None

        try:
            quote = quote_fetcher(plan.symbol)
        except Exception as exc:
            return f"live_quote_unavailable_before_entry:{exc}"
        if not isinstance(quote, dict) or quote.get("error"):
            return f"live_quote_unavailable_before_entry:{quote.get('error', 'invalid_quote') if isinstance(quote, dict) else 'invalid_quote'}"

        ltp_value = quote.get("ltp") or quote.get("last_price") or quote.get("price")
        if ltp_value is None:
            return "live_quote_unavailable_before_entry:missing_ltp"
        live_price = Decimal(str(ltp_value))
        if plan.side.value == "BUY" and live_price <= plan.stop_loss:
            return f"live_price_already_below_stop:{live_price}"
        if plan.side.value == "SELL" and live_price >= plan.stop_loss:
            return f"live_price_already_above_stop:{live_price}"
        return None

    def _handle_existing_position(
        self,
        plan: MicroTradePlan,
        setup: MicroTradeSetup,
    ) -> MicroTradeAttempt | None:
        position_for = getattr(self.broker, "position_for", None)
        if not callable(position_for):
            return None

        current_position = int(position_for(plan.symbol) or 0)
        if current_position == 0:
            return None

        if (current_position > 0 and plan.side.value == "BUY") or (
            current_position < 0 and plan.side.value == "SELL"
        ):
            return MicroTradeAttempt(
                symbol=plan.symbol,
                setup=setup,
                skipped_reason=f"position_already_open:{plan.symbol}:{current_position}",
            )

        order_status = self.broker.square_off(plan.symbol, abs(current_position))
        if order_status in {
            OrderStatus.SUBMITTED,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
        }:
            self._last_execution_at[plan.symbol] = datetime.now(timezone.utc)
        return MicroTradeAttempt(
            symbol=plan.symbol,
            setup=setup,
            order_status=order_status,
            skipped_reason=f"opposite_signal_exit:{plan.symbol}:{current_position}",
        )

    def _cooldown_skip_reason(self, symbol: str) -> str | None:
        if self.config.reentry_cooldown_seconds <= 0:
            return None

        last_execution = self._last_execution_at.get(symbol)
        if last_execution is None:
            return None

        elapsed = (datetime.now(timezone.utc) - last_execution).total_seconds()
        if elapsed < self.config.reentry_cooldown_seconds:
            remaining = int(self.config.reentry_cooldown_seconds - elapsed)
            return f"reentry_cooldown_active:{symbol}:{remaining}s"
        return None

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
