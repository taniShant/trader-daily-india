"""Breeze execution boundary for the Oracle proxy.

The proxy talks to this module only when it needs broker execution. Tests can
use MockBreezeClient; live mode uses IciciBreezeClient and imports Breeze lazily.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable, Protocol
from uuid import uuid4


class BreezeClientError(RuntimeError):
    """Raised when the Breeze client cannot be configured or called."""


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True)
class ProxyOrder:
    client_order_id: str
    symbol: str
    exchange: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float | None = None
    product_type: str = "intraday"


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    status: str
    client_order_id: str
    broker_order_id: str | None
    symbol: str
    exchange: str
    side: str
    order_type: str
    quantity: int
    price: float | None
    mode: str
    message: str
    accepted_at: str

    def to_response(self) -> dict[str, object]:
        return {
            "success": self.success,
            "status": self.status,
            "client_order_id": self.client_order_id,
            "broker_order_id": self.broker_order_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "side": self.side,
            "order_type": self.order_type,
            "quantity": self.quantity,
            "price": self.price,
            "mode": self.mode,
            "message": self.message,
            "accepted_at": self.accepted_at,
        }


class BreezeExecutionClient(Protocol):
    def place_order(self, order: ProxyOrder) -> ExecutionResult:
        """Place an order through the configured execution backend."""
        ...


class MockBreezeClient:
    def place_order(self, order: ProxyOrder) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            status="ACCEPTED",
            client_order_id=order.client_order_id,
            broker_order_id=f"mock-{uuid4().hex[:12]}",
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side.value,
            order_type=order.order_type.value,
            quantity=order.quantity,
            price=order.price,
            mode="mock",
            message="Mock order accepted. No Breeze API call was made.",
            accepted_at=datetime.now(timezone.utc).isoformat(),
        )


class IciciBreezeClient:
    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        session_token: str,
        breeze_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not all([api_key, api_secret, session_token]):
            raise BreezeClientError("ICICI Breeze credentials are required for live mode")

        if breeze_factory is None:
            try:
                from breeze_connect import BreezeConnect
            except ImportError as exc:
                raise BreezeClientError("breeze-connect is not installed") from exc
            breeze_factory = BreezeConnect

        self.breeze = breeze_factory(api_key=api_key)
        self.breeze.generate_session(api_secret=api_secret, session_token=session_token)

    def place_order(self, order: ProxyOrder) -> ExecutionResult:
        params: dict[str, Any] = {
            "stock_code": order.symbol,
            "exchange_code": order.exchange,
            "action": order.side.value.lower(),
            "order_type": order.order_type.value.lower(),
            "quantity": order.quantity,
            "validity": "day",
            "product_type": order.product_type,
        }
        if order.order_type == OrderType.LIMIT:
            if order.price is None:
                raise BreezeClientError("limit orders require price")
            params["price"] = order.price

        response = self.breeze.place_order(**params)
        if response and response.get("Success"):
            success = response["Success"]
            return ExecutionResult(
                success=True,
                status="ACCEPTED",
                client_order_id=order.client_order_id,
                broker_order_id=success.get("order_id"),
                symbol=order.symbol,
                exchange=order.exchange,
                side=order.side.value,
                order_type=order.order_type.value,
                quantity=order.quantity,
                price=order.price,
                mode="live",
                message="Breeze order accepted.",
                accepted_at=datetime.now(timezone.utc).isoformat(),
            )

        error = response.get("Error", "Breeze order placement failed") if response else "Empty Breeze response"
        raise BreezeClientError(str(error))


def create_execution_client(settings: dict[str, str]) -> BreezeExecutionClient:
    mode = settings.get("mode", "mock")
    if mode == "mock":
        return MockBreezeClient()
    if mode == "live":
        return IciciBreezeClient(
            api_key=settings.get("icici_api_key", ""),
            api_secret=settings.get("icici_secret_key", ""),
            session_token=settings.get("icici_session_token", ""),
        )
    raise BreezeClientError(f"Unsupported Oracle proxy mode: {mode}")
