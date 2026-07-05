from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from agent.contracts.execution import Fill, OrderRequest, OrderSide, OrderStatus


class PaperBroker:
    """In-memory broker for paper trading.

    It avoids external execution clients and is intended for deterministic
    local tests and safe ECS paper mode.
    """

    def __init__(self):
        self.orders: dict[str, OrderRequest] = {}
        self.statuses: dict[str, OrderStatus] = {}
        self.fills: dict[str, list[Fill]] = defaultdict(list)
        self.positions: dict[str, int] = defaultdict(int)

    def place_order(self, order: OrderRequest) -> OrderStatus:
        if order.client_order_id in self.orders:
            return self.statuses[order.client_order_id]

        fill_price = order.price or order.stop_loss or order.target_price
        if fill_price is None:
            self.statuses[order.client_order_id] = OrderStatus.REJECTED
            return OrderStatus.REJECTED

        self.orders[order.client_order_id] = order
        self.statuses[order.client_order_id] = OrderStatus.FILLED
        self.fills[order.client_order_id].append(
            Fill(
                fill_id=f"paper-fill-{order.client_order_id}-1",
                client_order_id=order.client_order_id,
                broker_order_id=f"paper-order-{order.client_order_id}",
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                fill_price=fill_price,
                filled_at=datetime.now(timezone.utc),
                source="paper",
            )
        )
        self._apply_position(order.symbol, order.side, order.quantity)
        return OrderStatus.FILLED

    def get_order_status(self, client_order_id: str) -> OrderStatus:
        return self.statuses.get(client_order_id, OrderStatus.CREATED)

    def get_fills(self, client_order_id: str) -> list[Fill]:
        return list(self.fills.get(client_order_id, []))

    def square_off(self, symbol: str, quantity: int) -> OrderStatus:
        current_quantity = self.positions.get(symbol, 0)
        if current_quantity == 0:
            return OrderStatus.REJECTED

        square_off_quantity = min(abs(current_quantity), quantity)
        if current_quantity > 0:
            self.positions[symbol] -= square_off_quantity
        else:
            self.positions[symbol] += square_off_quantity

        return OrderStatus.FILLED

    def position_for(self, symbol: str) -> int:
        return self.positions.get(symbol, 0)

    @staticmethod
    def _signed_quantity(side: OrderSide, quantity: int) -> int:
        if side == OrderSide.BUY:
            return quantity
        return -quantity

    def _apply_position(self, symbol: str, side: OrderSide, quantity: int) -> None:
        self.positions[symbol] += self._signed_quantity(side, quantity)
