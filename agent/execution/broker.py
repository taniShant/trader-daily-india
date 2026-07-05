from typing import Protocol

from agent.contracts.execution import Fill, OrderRequest, OrderStatus


class Broker(Protocol):
    """Common interface for paper and Oracle-backed live execution."""

    def place_order(self, order: OrderRequest) -> OrderStatus:
        """Submit an order and return the broker status."""
        ...

    def get_order_status(self, client_order_id: str) -> OrderStatus:
        """Fetch the latest known broker status for an order."""
        ...

    def get_fills(self, client_order_id: str) -> list[Fill]:
        """Fetch fills for an order."""
        ...

    def square_off(self, symbol: str, quantity: int) -> OrderStatus:
        """Close an open intraday position."""
        ...
