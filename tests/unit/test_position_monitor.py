from datetime import datetime, timedelta, timezone
from decimal import Decimal

from agent.execution.position_monitor import PositionAction, PositionMonitor


NOW = datetime(2026, 7, 5, 9, 0, tzinfo=timezone.utc)


def position(**overrides):
    data = {
        "quantity": 10,
        "entry_price": 100,
        "stop_loss": 98,
        "target": 104,
        "side": "BUY",
        "opened_at": NOW.isoformat(),
        "timeout_minutes": 30,
    }
    data.update(overrides)
    return data


def test_position_monitor_triggers_long_stop_loss_and_target():
    monitor = PositionMonitor()

    stop = monitor.evaluate("RELIANCE", position(), current_price=Decimal("97.5"), now=NOW)
    target = monitor.evaluate("RELIANCE", position(), current_price=Decimal("104.5"), now=NOW)

    assert stop.action == PositionAction.SQUARE_OFF
    assert stop.reason == "stop loss hit"
    assert target.action == PositionAction.SQUARE_OFF
    assert target.reason == "target hit"


def test_position_monitor_handles_short_position_rules():
    monitor = PositionMonitor()
    short = position(quantity=10, side="SELL", entry_price=100, stop_loss=102, target=96)

    target = monitor.evaluate("RELIANCE", short, current_price=Decimal("95.5"), now=NOW)
    stop = monitor.evaluate("RELIANCE", short, current_price=Decimal("102.5"), now=NOW)

    assert target.reason == "target hit"
    assert stop.reason == "stop loss hit"


def test_position_monitor_triggers_timeout_and_square_off_window():
    monitor = PositionMonitor()

    expired = monitor.evaluate(
        "RELIANCE",
        position(opened_at=(NOW - timedelta(minutes=31)).isoformat()),
        current_price=Decimal("100"),
        now=NOW,
    )
    due = monitor.evaluate("RELIANCE", position(), current_price=Decimal("100"), now=NOW, square_off_due=True)

    assert expired.action == PositionAction.SQUARE_OFF
    assert expired.reason == "holding window expired"
    assert due.reason == "scheduled square-off window"


def test_position_monitor_holds_when_within_limits():
    decision = PositionMonitor().evaluate("RELIANCE", position(), current_price=Decimal("101"), now=NOW)

    assert decision.action == PositionAction.HOLD
    assert decision.reason == "position within limits"
