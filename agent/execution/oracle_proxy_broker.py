from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agent.contracts.execution import Fill, OrderRequest, OrderSide, OrderStatus, OrderType

from .oracle_breeze_client import OracleBreezeClient


class OracleProxyBroker:
    """Broker adapter that routes live AWS execution through the Oracle proxy."""

    def __init__(self, client: OracleBreezeClient):
        self.client = client

    def place_order(self, order: OrderRequest) -> OrderStatus:
        return self.client.place_order(order)

    def get_order_status(self, client_order_id: str) -> OrderStatus:
        return OrderStatus.SUBMITTED

    def get_fills(self, client_order_id: str) -> list[Fill]:
        return []

    def square_off(self, symbol: str, quantity: int) -> OrderStatus:
        order = OrderRequest(
            client_order_id=f"square-off-{symbol}-{uuid4().hex}",
            signal_id=f"square-off-{symbol}",
            risk_decision_id=f"square-off-{symbol}",
            symbol=symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=quantity,
            requested_at=datetime.now(timezone.utc),
        )
        return self.place_order(order)
