from __future__ import annotations

from dataclasses import dataclass

from agent.contracts.execution import Fill, OrderStatus
from agent.execution.broker import Broker


TERMINAL_STATUSES = {
    OrderStatus.FILLED,
    OrderStatus.REJECTED,
    OrderStatus.CANCELLED,
    OrderStatus.FAILED,
}


@dataclass(frozen=True)
class OrderMonitorResult:
    client_order_id: str
    status: OrderStatus
    fills: list[Fill]
    filled_quantity: int
    is_terminal: bool
    should_retry: bool
    reason: str


class OrderMonitor:
    def __init__(self, broker: Broker):
        self.broker = broker

    def check(self, client_order_id: str) -> OrderMonitorResult:
        status = self.broker.get_order_status(client_order_id)
        fills = self.broker.get_fills(client_order_id)
        filled_quantity = sum(fill.quantity for fill in fills)
        return OrderMonitorResult(
            client_order_id=client_order_id,
            status=status,
            fills=fills,
            filled_quantity=filled_quantity,
            is_terminal=status in TERMINAL_STATUSES,
            should_retry=status in {OrderStatus.REJECTED, OrderStatus.FAILED},
            reason=_reason(status, filled_quantity),
        )


def _reason(status: OrderStatus, filled_quantity: int) -> str:
    if status == OrderStatus.FILLED:
        return "order filled"
    if status == OrderStatus.PARTIALLY_FILLED:
        return f"partial fill quantity {filled_quantity}"
    if status in {OrderStatus.ACCEPTED, OrderStatus.SUBMITTED, OrderStatus.CREATED}:
        return "order still open"
    if status == OrderStatus.REJECTED:
        return "order rejected"
    if status == OrderStatus.CANCELLED:
        return "order cancelled"
    return "order failed"
