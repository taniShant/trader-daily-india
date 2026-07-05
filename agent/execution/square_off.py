from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.contracts.execution import OrderStatus
from agent.execution.broker import Broker


@dataclass(frozen=True)
class SquareOffResult:
    symbol: str
    quantity: int
    status: OrderStatus
    success: bool
    reason: str


def square_off_positions(broker: Broker, positions: dict[str, dict[str, Any]]) -> list[SquareOffResult]:
    results: list[SquareOffResult] = []
    for symbol, position in positions.items():
        quantity = abs(int(position.get("quantity", 0)))
        if quantity == 0:
            results.append(SquareOffResult(symbol, 0, OrderStatus.REJECTED, False, "no open quantity"))
            continue
        try:
            status = broker.square_off(symbol, quantity)
            success = status in {
                OrderStatus.SUBMITTED,
                OrderStatus.ACCEPTED,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.FILLED,
            }
            results.append(SquareOffResult(symbol, quantity, status, success, f"square-off {status}"))
        except Exception as exc:
            results.append(SquareOffResult(symbol, quantity, OrderStatus.FAILED, False, str(exc)))
    return results
