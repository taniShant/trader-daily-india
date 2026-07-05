from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any


class PositionAction(StrEnum):
    HOLD = "HOLD"
    SQUARE_OFF = "SQUARE_OFF"


@dataclass(frozen=True)
class PositionDecision:
    symbol: str
    action: PositionAction
    reason: str


class PositionMonitor:
    def evaluate(
        self,
        symbol: str,
        position: dict[str, Any],
        *,
        current_price: Decimal,
        now: datetime | None = None,
        square_off_due: bool = False,
    ) -> PositionDecision:
        current_time = _as_utc(now or datetime.now(timezone.utc))
        quantity = int(position.get("quantity", 0))
        if quantity == 0:
            return PositionDecision(symbol, PositionAction.HOLD, "no open quantity")

        entry_price = Decimal(str(position.get("entry_price")))
        stop_loss = Decimal(str(position.get("stop_loss")))
        target = Decimal(str(position.get("target")))
        opened_at = _parse_time(position.get("opened_at")) if position.get("opened_at") else None
        timeout_minutes = int(position.get("timeout_minutes", 30))
        side = str(position.get("side", "")).upper()
        is_long = side != "SELL" if side else quantity > 0

        if square_off_due:
            return PositionDecision(symbol, PositionAction.SQUARE_OFF, "scheduled square-off window")
        if is_long and current_price <= stop_loss:
            return PositionDecision(symbol, PositionAction.SQUARE_OFF, "stop loss hit")
        if not is_long and current_price >= stop_loss:
            return PositionDecision(symbol, PositionAction.SQUARE_OFF, "stop loss hit")
        if is_long and current_price >= target:
            return PositionDecision(symbol, PositionAction.SQUARE_OFF, "target hit")
        if not is_long and current_price <= target:
            return PositionDecision(symbol, PositionAction.SQUARE_OFF, "target hit")
        if opened_at and current_time - opened_at >= timedelta(minutes=timeout_minutes):
            return PositionDecision(symbol, PositionAction.SQUARE_OFF, "holding window expired")
        return PositionDecision(symbol, PositionAction.HOLD, "position within limits")


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str):
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    raise ValueError(f"Unsupported opened_at value: {value!r}")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
