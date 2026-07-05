from datetime import datetime, timezone
from decimal import Decimal

from agent.contracts.execution import OrderRequest, OrderSide, OrderStatus, OrderType
from agent.execution.paper_broker import PaperBroker


def make_order(**overrides):
    data = {
        "client_order_id": "paper-1",
        "signal_id": "sig-1",
        "risk_decision_id": "risk-1",
        "symbol": "RELIANCE",
        "side": OrderSide.BUY,
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "price": Decimal("100"),
        "stop_loss": Decimal("95"),
        "target_price": Decimal("112"),
        "requested_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return OrderRequest(**data)


def test_place_order_fills_immediately_and_records_fill():
    broker = PaperBroker()
    order = make_order()

    status = broker.place_order(order)
    fills = broker.get_fills(order.client_order_id)

    assert status == OrderStatus.FILLED
    assert broker.get_order_status(order.client_order_id) == OrderStatus.FILLED
    assert len(fills) == 1
    assert fills[0].source == "paper"
    assert fills[0].fill_price == Decimal("100")
    assert fills[0].quantity == 10
    assert broker.position_for("RELIANCE") == 10


def test_repeated_client_order_id_is_idempotent():
    broker = PaperBroker()
    order = make_order()

    assert broker.place_order(order) == OrderStatus.FILLED
    assert broker.place_order(order) == OrderStatus.FILLED

    assert len(broker.get_fills(order.client_order_id)) == 1
    assert broker.position_for("RELIANCE") == 10


def test_sell_order_creates_short_position():
    broker = PaperBroker()
    order = make_order(
        client_order_id="paper-sell-1",
        side=OrderSide.SELL,
        price=Decimal("200"),
        stop_loss=Decimal("210"),
        target_price=Decimal("180"),
    )

    assert broker.place_order(order) == OrderStatus.FILLED
    assert broker.position_for("RELIANCE") == -10


def test_square_off_reduces_open_position_without_oracle_call():
    broker = PaperBroker()
    broker.place_order(make_order(quantity=10))

    assert broker.square_off("RELIANCE", 4) == OrderStatus.FILLED
    assert broker.position_for("RELIANCE") == 6
    assert broker.square_off("RELIANCE", 20) == OrderStatus.FILLED
    assert broker.position_for("RELIANCE") == 0


def test_square_off_rejects_unknown_position():
    broker = PaperBroker()

    assert broker.square_off("TCS", 1) == OrderStatus.REJECTED


def test_unknown_order_status_is_created_and_has_no_fills():
    broker = PaperBroker()

    assert broker.get_order_status("missing") == OrderStatus.CREATED
    assert broker.get_fills("missing") == []


def test_paper_broker_source_does_not_reference_oracle_or_breeze():
    import inspect
    import agent.execution.paper_broker as paper_broker_module

    source = inspect.getsource(paper_broker_module).lower()

    assert "oracle" not in source
    assert "breeze" not in source
    assert "requests" not in source
    assert "urllib" not in source
