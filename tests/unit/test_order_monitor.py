from datetime import datetime, timezone
from decimal import Decimal

from agent.contracts.execution import Fill, OrderSide, OrderStatus
from agent.execution.order_monitor import OrderMonitor


class FakeBroker:
    def __init__(self, status, fills=None):
        self.status = status
        self.fills = fills or []

    def get_order_status(self, client_order_id):
        return self.status

    def get_fills(self, client_order_id):
        return self.fills


def fill(quantity=5):
    return Fill(
        fill_id="fill-1",
        client_order_id="order-1",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=quantity,
        fill_price=Decimal("100"),
        filled_at=datetime.now(timezone.utc),
        source="test",
    )


def test_order_monitor_handles_filled_order():
    result = OrderMonitor(FakeBroker(OrderStatus.FILLED, [fill(10)])).check("order-1")

    assert result.status == OrderStatus.FILLED
    assert result.filled_quantity == 10
    assert result.is_terminal is True
    assert result.should_retry is False
    assert result.reason == "order filled"


def test_order_monitor_handles_partial_fill():
    result = OrderMonitor(FakeBroker(OrderStatus.PARTIALLY_FILLED, [fill(3)])).check("order-1")

    assert result.is_terminal is False
    assert result.filled_quantity == 3
    assert "partial fill" in result.reason


def test_order_monitor_marks_rejected_as_retryable_terminal():
    result = OrderMonitor(FakeBroker(OrderStatus.REJECTED)).check("order-1")

    assert result.is_terminal is True
    assert result.should_retry is True
    assert result.reason == "order rejected"
