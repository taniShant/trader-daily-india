from datetime import datetime, timezone
from decimal import Decimal

from agent.contracts.execution import Fill, OrderRequest, OrderSide, OrderStatus, OrderType
from agent.contracts.risk import RiskDecision, RiskDecisionStatus
from agent.contracts.signals import RiskLevel, SignalAction, TradeSignal
from agent.storage.repositories import (
    FillsRepository,
    OrdersRepository,
    PnlRecord,
    PnlRepository,
    PositionSnapshot,
    PositionsRepository,
    RiskEventsRepository,
    SignalsRepository,
    TradeEventRecord,
)


class FakeTable:
    def __init__(self):
        self.items = []

    def put_item(self, **kwargs):
        self.items.append(kwargs["Item"])

    def scan(self, **kwargs):
        return {"Items": list(self.items)}


def test_signal_repository_persists_signal_with_table_keys():
    table = FakeTable()
    signal = TradeSignal(
        signal_id="sig-1",
        symbol="RELIANCE",
        action=SignalAction.BUY,
        confidence=82,
        generated_at=datetime(2026, 7, 6, 9, 20, tzinfo=timezone.utc),
        entry_price=Decimal("2800"),
        stop_loss=Decimal("2775"),
        target_price=Decimal("2860"),
        holding_window_minutes=45,
        risk_level=RiskLevel.MEDIUM,
    )

    SignalsRepository(table).put_signal(signal, session_id="session-1")

    assert table.items[0]["signal_id"] == "sig-1"
    assert table.items[0]["created_at"] == "2026-07-06T09:20:00+00:00"
    assert table.items[0]["session_id"] == "session-1"


def test_execution_repositories_persist_order_fill_and_risk_decision():
    order_table = FakeTable()
    fill_table = FakeTable()
    risk_table = FakeTable()
    requested_at = datetime(2026, 7, 6, 9, 21, tzinfo=timezone.utc)

    order = OrderRequest(
        client_order_id="client-1",
        signal_id="sig-1",
        risk_decision_id="risk-1",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=Decimal("2800"),
        requested_at=requested_at,
    )
    fill = Fill(
        fill_id="fill-1",
        client_order_id="client-1",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=10,
        fill_price=Decimal("2800"),
        filled_at=requested_at,
        source="paper",
    )
    decision = RiskDecision(
        decision_id="risk-1",
        signal_id="sig-1",
        status=RiskDecisionStatus.APPROVED,
        decided_at=requested_at,
        approved_quantity=10,
        approved_price=Decimal("2800"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
    )

    OrdersRepository(order_table).put_order(order, status=OrderStatus.ACCEPTED, broker_order_id="broker-1")
    FillsRepository(fill_table).put_fill(fill)
    RiskEventsRepository(risk_table).put_decision(decision)

    assert order_table.items[0]["client_order_id"] == "client-1"
    assert order_table.items[0]["status"] == "ACCEPTED"
    assert order_table.items[0]["updated_at"] == "2026-07-06T09:21:00+00:00"
    assert fill_table.items[0]["fill_id"] == "fill-1"
    assert fill_table.items[0]["filled_at"] == "2026-07-06T09:21:00+00:00"
    assert risk_table.items[0]["risk_decision_id"] == "risk-1"
    assert risk_table.items[0]["created_at"] == "2026-07-06T09:21:00+00:00"


def test_position_and_pnl_repositories_persist_consistent_snapshots():
    position_table = FakeTable()
    pnl_table = FakeTable()
    updated_at = datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc)

    PositionsRepository(position_table).put_snapshot(
        PositionSnapshot(
            symbol="INFY",
            session_id="session-1",
            quantity=20,
            average_price=Decimal("1500"),
            last_price=Decimal("1512"),
            unrealized_pnl=Decimal("240"),
            updated_at=updated_at,
        )
    )
    PnlRepository(pnl_table).put_pnl(
        PnlRecord(
            trade_id="trade-1",
            date="2026-07-06",
            symbol="INFY",
            realized_pnl=Decimal("230"),
            gross_pnl=Decimal("240"),
            costs=Decimal("10"),
            session_id="session-1",
            closed_at=updated_at,
        )
    )

    assert position_table.items[0]["symbol"] == "INFY"
    assert position_table.items[0]["session_id"] == "session-1"
    assert position_table.items[0]["updated_at"] == "2026-07-06T10:00:00+00:00"
    assert pnl_table.items[0]["tradeId"] == "trade-1"
    assert pnl_table.items[0]["stock_symbol"] == "INFY"
    assert pnl_table.items[0]["pnl"] == Decimal("230")


def test_positions_repository_lists_only_open_nonzero_snapshots():
    table = FakeTable()
    repository = PositionsRepository(table)
    updated_at = datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc)

    repository.put_snapshot(
        PositionSnapshot(
            symbol="INFY",
            session_id="session-1",
            quantity=20,
            average_price=Decimal("1500"),
            last_price=Decimal("1510"),
            unrealized_pnl=Decimal("200"),
            updated_at=updated_at,
            status="OPEN",
        )
    )
    repository.put_snapshot(
        PositionSnapshot(
            symbol="MARUTI",
            session_id="session-1",
            quantity=0,
            average_price=Decimal("14000"),
            last_price=Decimal("14000"),
            unrealized_pnl=Decimal("0"),
            updated_at=updated_at,
            status="OPEN",
        )
    )
    repository.put_snapshot(
        PositionSnapshot(
            symbol="RELIANCE",
            session_id="session-1",
            quantity=10,
            average_price=Decimal("1400"),
            last_price=Decimal("1401"),
            unrealized_pnl=Decimal("10"),
            updated_at=updated_at,
            status="CLOSED",
        )
    )

    open_positions = repository.list_open()

    assert [item["symbol"] for item in open_positions] == ["INFY"]


def test_pnl_repository_persists_dashboard_trade_event():
    table = FakeTable()
    timestamp = datetime(2026, 8, 3, 6, 45, tzinfo=timezone.utc)

    PnlRepository(table).put_trade_event(
        TradeEventRecord(
            trade_id="micro-MARUTI-1",
            date="2026-08-03",
            timestamp=timestamp,
            symbol="MARUTI",
            action="BUY",
            price=Decimal("13620"),
            quantity=1,
            pnl=Decimal("0"),
            session_id="session-1",
            signal_id="signal-1",
            order_id="order-1",
            status="FILLED",
            source="paper",
            confidence=82,
        )
    )

    assert table.items[0]["tradeId"] == "micro-MARUTI-1"
    assert table.items[0]["timestamp"] == "2026-08-03T06:45:00+00:00"
    assert table.items[0]["stock_symbol"] == "MARUTI"
    assert table.items[0]["action"] == "BUY"
    assert table.items[0]["price"] == Decimal("13620")


def test_pnl_repository_lists_trade_events_for_date():
    table = FakeTable()
    table.items = [
        {"tradeId": "micro-exit-1", "date": "2026-08-18", "pnl": Decimal("-10")},
        {"tradeId": "micro-exit-2", "date": "2026-08-17", "pnl": Decimal("-20")},
        {"tradeId": "micro-exit-3", "date": "2026-08-18", "pnl": Decimal("5")},
    ]

    rows = PnlRepository(table).list_trade_events_for_date("2026-08-18")

    assert [row["tradeId"] for row in rows] == ["micro-exit-1", "micro-exit-3"]
