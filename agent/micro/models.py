from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from agent.contracts.execution import OrderSide


@dataclass(frozen=True)
class MicroTradeConfig:
    """Runtime knobs for 5-10 minute deterministic intraday trades."""

    enabled: bool = False
    interval: str = "1m"
    lookback_days: int = 1
    max_hold_minutes: int = 10
    min_confidence: int = 72
    min_relative_volume: float = 1.8
    min_atr_ratio: float = 0.0015
    max_atr_ratio: float = 0.025
    max_vwap_extension_atr: float = 2.0
    target_pct: Decimal = Decimal("0.004")
    stop_pct: Decimal = Decimal("0.002")
    max_symbols_per_cycle: int = 20


@dataclass(frozen=True)
class MicroTradeSetup:
    symbol: str
    action: str
    confidence: int
    setup: str
    entry_price: Decimal | None
    stop_loss: Decimal | None
    target_price: Decimal | None
    reasons: list[str]
    features: dict[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        return self.action in {"BUY", "SELL"} and all(
            value is not None for value in [self.entry_price, self.stop_loss, self.target_price]
        )


@dataclass(frozen=True)
class MicroTradePlan:
    signal_id: str
    symbol: str
    side: OrderSide
    entry_price: Decimal
    stop_loss: Decimal
    target_price: Decimal
    confidence: int
    max_hold_minutes: int
    reasons: list[str]
    features: dict[str, Any] = field(default_factory=dict)


@dataclass
class MicroTradePosition:
    symbol: str
    side: OrderSide
    quantity: int
    entry_price: Decimal
    stop_loss: Decimal
    target_price: Decimal
    opened_at: datetime
    max_hold_minutes: int
    client_order_id: str

    def exit_reason(self, current_price: Decimal, now: datetime | None = None) -> str | None:
        now = now or datetime.now(timezone.utc)
        age_seconds = (now - self.opened_at).total_seconds()
        if age_seconds >= self.max_hold_minutes * 60:
            return "time_exit"

        if self.side == OrderSide.BUY:
            if current_price <= self.stop_loss:
                return "stop_loss"
            if current_price >= self.target_price:
                return "target"
        else:
            if current_price >= self.stop_loss:
                return "stop_loss"
            if current_price <= self.target_price:
                return "target"

        return None
