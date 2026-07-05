import json
from decimal import Decimal

from agent.observability import build_log_event, log_event


def test_build_log_event_includes_required_execution_fields():
    event = build_log_event(
        "order_submitted",
        symbol="RELIANCE",
        signal_id="sig-1",
        order_id="order-1",
        mode="paper",
        reason="accepted",
        quantity=10,
    )

    assert event["event_type"] == "order_submitted"
    assert event["symbol"] == "RELIANCE"
    assert event["signal_id"] == "sig-1"
    assert event["order_id"] == "order-1"
    assert event["mode"] == "paper"
    assert event["reason"] == "accepted"
    assert event["quantity"] == 10
    assert event["timestamp"].endswith("+00:00")


def test_log_event_writes_json_with_decimal_fields(caplog):
    with caplog.at_level("INFO", logger="trading_bot"):
        event = log_event(
            "risk_rejected",
            symbol="TCS",
            signal_id="sig-2",
            mode="live",
            reason="low confidence",
            risk_amount=Decimal("125.50"),
        )

    payload = json.loads(caplog.records[0].message)

    assert payload["event_type"] == "risk_rejected"
    assert payload["symbol"] == "TCS"
    assert payload["signal_id"] == "sig-2"
    assert payload["mode"] == "live"
    assert payload["reason"] == "low confidence"
    assert payload["risk_amount"] == 125.5
    assert event["risk_amount"] == Decimal("125.50")


def test_trading_bot_source_logs_safety_critical_events():
    import inspect
    import agent.main as main_module

    source = inspect.getsource(main_module.TradingBot)

    assert '"risk_rejected"' in source
    assert '"order_submitted"' in source
    assert '"order_failed"' in source
    assert '"order_error"' in source
    assert '"square_off_submitted"' in source
    assert '"square_off_failed"' in source
    assert '"square_off_error"' in source
