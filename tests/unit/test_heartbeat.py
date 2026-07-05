from datetime import datetime, timezone
from decimal import Decimal

from agent.storage import MarketStateRepository, build_bot_heartbeat


def test_heartbeat_item_matches_market_state_table_key_shape():
    heartbeat = build_bot_heartbeat(
        bot_id="trading-bot",
        status="market_cycle_start",
        mode="paper",
        environment="test",
        cycle=7,
        market_open=True,
        active_positions=2,
        daily_pnl=Decimal("-125.50"),
        updated_at=datetime(2026, 7, 4, 9, 15, tzinfo=timezone.utc),
    )

    item = heartbeat.to_item()

    assert item["date"] == "heartbeat#trading-bot"
    assert item["timestamp"] == "2026-07-04T09:15:00+00:00"
    assert item["record_type"] == "bot_heartbeat"
    assert item["status"] == "market_cycle_start"
    assert item["mode"] == "paper"
    assert item["environment"] == "test"
    assert item["cycle"] == 7
    assert item["market_open"] is True
    assert item["active_positions"] == 2
    assert item["daily_pnl"] == Decimal("-125.50")


def test_market_state_repository_writes_heartbeat_item():
    calls = []

    class FakeTable:
        def put_item(self, **kwargs):
            calls.append(kwargs)

    heartbeat = build_bot_heartbeat(
        bot_id="bot-1",
        status="started",
        mode="live",
        environment="prod",
        cycle=0,
        market_open=False,
        active_positions=0,
        daily_pnl=Decimal("0"),
        updated_at=datetime(2026, 7, 4, 8, 0, tzinfo=timezone.utc),
    )

    MarketStateRepository(FakeTable()).put_heartbeat(heartbeat)

    assert len(calls) == 1
    assert calls[0]["Item"]["date"] == "heartbeat#bot-1"
    assert calls[0]["Item"]["status"] == "started"
    assert calls[0]["Item"]["mode"] == "live"


def test_trading_bot_source_records_runtime_heartbeats():
    import inspect
    import agent.main as main_module

    source = inspect.getsource(main_module.TradingBot)

    assert '_record_heartbeat("started")' in source
    assert '_record_heartbeat("market_cycle_start")' in source
    assert '_record_heartbeat("market_cycle_complete")' in source
    assert '_record_heartbeat("waiting_for_market")' in source
    assert '_record_heartbeat("runtime_error")' in source
    assert "build_bot_heartbeat" in inspect.getsource(main_module)
