from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from agent.contracts.execution import Fill, OrderRequest, OrderSide, OrderStatus, OrderType
from agent.contracts.risk import RiskDecision, RiskDecisionStatus
from agent.contracts.signals import SignalAction, TradeSignal
from agent.backtest.costs import CostModel
from agent.main import TradingBot
import agent.main as main_module
from agent.micro import MicroTradeSetup


def _bot_stub():
    bot = TradingBot.__new__(TradingBot)
    bot.events = []
    bot.active_positions = {}
    bot.micro_engine = object()
    bot._check_circuit_breakers = lambda: True
    bot._should_square_off = lambda: False
    bot._is_new_trade_allowed = lambda: True
    bot._run_micro_trading_cycle = lambda: bot.events.append("micro")
    bot._monitor_positions = lambda: bot.events.append("monitor")
    bot._square_off_all = lambda: bot.events.append("square_off")
    bot.daily_pnl = 0.0
    bot.consecutive_losses = 0
    bot._micro_recent_losses = {}
    bot._micro_symbol_health = {}
    bot._micro_expectancy = {}
    bot._micro_cost_model = CostModel()
    return bot


def test_micro_market_cycle_runs_fast_lane_without_owning_exit_monitor():
    bot = _bot_stub()

    bot._run_micro_market_cycle()

    assert bot.events == ["micro"]


def test_micro_market_cycle_square_off_takes_priority():
    bot = _bot_stub()
    bot._should_square_off = lambda: True

    bot._run_micro_market_cycle()

    assert bot.events == ["square_off"]


def test_micro_market_cycle_only_monitors_after_new_trade_cutoff():
    bot = _bot_stub()
    bot._is_new_trade_allowed = lambda: False

    bot._run_micro_market_cycle()

    assert bot.events == ["monitor"]


def test_outside_market_sleep_is_capped_to_short_poll_interval(monkeypatch):
    bot = _bot_stub()
    bot.market_clock = SimpleNamespace(seconds_until_next_open=lambda: 3600)

    assert bot._outside_market_sleep_seconds() <= 60


def test_startup_reconciliation_closes_stale_paper_positions():
    bot = _bot_stub()
    bot.paper_trading = True
    bot.current_session_id = "session-now"

    open_row = {
        "symbol": "RELIANCE",
        "session_id": "old-session",
        "quantity": 10,
        "average_price": Decimal("1400"),
        "last_price": Decimal("1398"),
        "side": "LONG",
        "status": "OPEN",
    }
    captured = SimpleNamespace(closed=[])
    bot._audit_repositories = SimpleNamespace(
        positions=SimpleNamespace(
            list_open=lambda: [open_row],
            put_snapshot=captured.closed.append,
        )
    )

    bot._reconcile_positions_on_startup()

    assert captured.closed[0].symbol == "RELIANCE"
    assert captured.closed[0].quantity == 0
    assert captured.closed[0].status == "CLOSED"
    assert bot.active_positions == {}


def test_live_startup_reconciliation_blocks_new_entries_when_broker_cannot_list_positions():
    bot = _bot_stub()
    bot.paper_trading = False
    bot.broker = SimpleNamespace()
    bot._entry_block_reason = None
    bot._audit_repositories = SimpleNamespace(
        positions=SimpleNamespace(
            list_open=lambda: [{"symbol": "RELIANCE", "quantity": 10, "status": "OPEN"}],
        )
    )

    bot._reconcile_positions_on_startup()

    assert bot._entry_block_reason == "live_position_reconciliation_unavailable"


def test_manual_service_start_skips_overnight_analysis_by_default(monkeypatch):
    bot = _bot_stub()
    bot.paper_trading = True
    bot.running = True
    bot.cycle_count = 0
    bot._is_market_hours = lambda: True
    bot._record_heartbeat = lambda status: bot.events.append(f"heartbeat:{status}")
    bot._run_overnight_analysis = lambda: bot.events.append("overnight")
    bot._start_position_monitor_thread = lambda: bot.events.append("monitor_thread")

    def cycle_once():
        bot.events.append("cycle")
        bot.running = False

    bot._run_micro_market_cycle = cycle_once
    monkeypatch.setattr(main_module, "RUN_STARTUP_OVERNIGHT_ANALYSIS", False)
    monkeypatch.setattr(main_module.time, "sleep", lambda seconds: None)

    bot.run()

    assert "overnight" not in bot.events
    assert "monitor_thread" in bot.events
    assert "cycle" in bot.events


def test_startup_overnight_analysis_can_be_enabled(monkeypatch):
    bot = _bot_stub()
    bot.paper_trading = True
    bot.running = False
    bot.cycle_count = 0
    bot._record_heartbeat = lambda status: None
    bot._run_overnight_analysis = lambda: bot.events.append("overnight")
    bot._start_position_monitor_thread = lambda: bot.events.append("monitor_thread")
    monkeypatch.setattr(main_module, "RUN_STARTUP_OVERNIGHT_ANALYSIS", True)

    bot.run()

    assert bot.events[:2] == ["overnight", "monitor_thread"]


def test_micro_cycle_sleep_uses_cycle_start_not_scan_finish(monkeypatch):
    bot = _bot_stub()
    monkeypatch.setattr(main_module, "MICRO_SCAN_INTERVAL_SECONDS", 90)

    assert bot._micro_cycle_sleep_seconds(100.0, now=125.0) == 65.0


def test_micro_cycle_sleep_returns_zero_when_scan_overruns(monkeypatch):
    bot = _bot_stub()
    monkeypatch.setattr(main_module, "MICRO_SCAN_INTERVAL_SECONDS", 90)

    assert bot._micro_cycle_sleep_seconds(100.0, now=205.0) == 0.0


def test_micro_run_loop_sleeps_remaining_interval_from_cycle_start(monkeypatch):
    bot = _bot_stub()
    bot.paper_trading = True
    bot.running = True
    bot.cycle_count = 0
    bot._is_market_hours = lambda: True
    bot._record_heartbeat = lambda status: bot.events.append(f"heartbeat:{status}")
    bot._run_overnight_analysis = lambda: bot.events.append("overnight")
    bot._start_position_monitor_thread = lambda: bot.events.append("monitor_thread")
    sleeps = []
    monotonic_values = iter([100.0, 125.0])

    def cycle_once():
        bot.events.append("cycle")
        bot.running = False

    bot._run_micro_market_cycle = cycle_once
    monkeypatch.setattr(main_module, "RUN_STARTUP_OVERNIGHT_ANALYSIS", False)
    monkeypatch.setattr(main_module, "MICRO_SCAN_INTERVAL_SECONDS", 90)
    monkeypatch.setattr(main_module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(main_module.time, "sleep", sleeps.append)

    bot.run()

    assert sleeps == [65.0]
    assert "cycle" in bot.events


def test_micro_diagnostics_prints_nearest_hold_setups(capsys):
    bot = _bot_stub()

    attempt = type(
        "Attempt",
        (),
        {
            "setup": MicroTradeSetup(
                symbol="MARUTI",
                action="HOLD",
                confidence=68,
                setup="micro_monitor",
                entry_price=None,
                stop_loss=None,
                target_price=None,
                reasons=["relative volume too weak 1.42x", "no confirmed micro setup"],
                features={
                    "relative_volume": 1.42,
                    "rsi": 61.2,
                    "atr": 19.4,
                    "close": 13420.0,
                    "vwap": 13398.0,
                    "trend_bias": "bullish",
                },
            ),
            "executed": False,
            "skipped_reason": "no_actionable_micro_setup",
        },
    )()

    bot._log_micro_diagnostics([attempt])

    output = capsys.readouterr().out
    assert "Micro nearest setups" in output
    assert "MARUTI" in output
    assert "rv=1.42" in output
    assert "rsi=61.20" in output


def test_micro_rejection_summary_prints_reason_counts(capsys):
    bot = _bot_stub()

    def attempt(symbol, reasons, relative_volume):
        return type(
            "Attempt",
            (),
            {
                "setup": MicroTradeSetup(
                    symbol=symbol,
                    action="HOLD",
                    confidence=50,
                    setup="micro_monitor",
                    entry_price=None,
                    stop_loss=None,
                    target_price=None,
                    reasons=reasons,
                    features={"relative_volume": relative_volume},
                ),
                "executed": False,
                "skipped_reason": "no_actionable_micro_setup",
            },
        )()

    bot._log_micro_rejection_summary(
        [
            attempt("MARUTI", ["relative volume too weak 0.90x"], 0.9),
            attempt("RELIANCE", ["price overextended versus VWAP"], 1.4),
            attempt("INFY", ["price not overextended versus VWAP"], 1.3),
        ]
    )

    output = capsys.readouterr().out
    assert "Micro rejection summary" in output
    assert "volume_failed=1" in output
    assert "continuation_volume_failed=3" in output
    assert "vwap_extension_failed=1" in output


def test_micro_attempt_persists_dashboard_visible_audit_records():
    bot = _bot_stub()
    bot.bot_id = "bot-test"
    bot.current_session_id = "session-test"
    bot.active_positions = {}

    captured = SimpleNamespace(
        signals=[],
        risk_events=[],
        orders=[],
        fills=[],
        positions=[],
        trades=[],
    )
    bot._audit_repositories = SimpleNamespace(
        signals=SimpleNamespace(put_signal=lambda signal, session_id=None: captured.signals.append((signal, session_id))),
        risk_events=SimpleNamespace(put_decision=captured.risk_events.append),
        orders=SimpleNamespace(
            put_order=lambda order, status, broker_order_id=None: captured.orders.append(
                (order, status, broker_order_id)
            )
        ),
        fills=SimpleNamespace(put_fill=captured.fills.append),
        positions=SimpleNamespace(put_snapshot=captured.positions.append),
        pnl=SimpleNamespace(put_trade_event=captured.trades.append),
    )

    generated_at = datetime(2026, 8, 3, 6, 45, tzinfo=timezone.utc)
    signal = TradeSignal(
        signal_id="micro-MARUTI-1-BUY",
        symbol="MARUTI",
        action=SignalAction.BUY,
        confidence=82,
        generated_at=generated_at,
        entry_price=Decimal("13620"),
        stop_loss=Decimal("13592.76"),
        target_price=Decimal("13674.48"),
        holding_window_minutes=10,
    )
    decision = RiskDecision(
        decision_id="risk-1",
        signal_id=signal.signal_id,
        status=RiskDecisionStatus.APPROVED,
        decided_at=generated_at,
        approved_quantity=1,
        approved_price=Decimal("13620"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
    )
    order = OrderRequest(
        client_order_id="order-1",
        signal_id=signal.signal_id,
        risk_decision_id=decision.decision_id,
        symbol="MARUTI",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=1,
        price=Decimal("13620"),
        stop_loss=Decimal("13592.76"),
        target_price=Decimal("13674.48"),
        requested_at=generated_at,
    )
    fill = Fill(
        fill_id="fill-1",
        client_order_id=order.client_order_id,
        broker_order_id="broker-1",
        symbol="MARUTI",
        side=OrderSide.BUY,
        quantity=1,
        fill_price=Decimal("13620"),
        filled_at=generated_at,
        source="paper",
    )
    bot.broker = SimpleNamespace(get_fills=lambda client_order_id: [fill])
    attempt = SimpleNamespace(
        symbol="MARUTI",
        setup=MicroTradeSetup(
            symbol="MARUTI",
            action="BUY",
            confidence=82,
            setup="micro_volume_continuation",
            entry_price=Decimal("13620"),
            stop_loss=Decimal("13592.76"),
            target_price=Decimal("13674.48"),
            reasons=["test setup"],
            features={
                "relative_volume": 3.1,
                "atr_ratio": 0.0012,
                "vwap_extension_atr": 1.4,
                "latest_timestamp": "2026-08-03T06:45:00+00:00",
                "latest_source": "breeze",
            },
        ),
        signal=signal,
        risk_decision=decision,
        order=order,
        order_status=OrderStatus.FILLED,
        executed=True,
    )

    bot._persist_micro_attempts([attempt])

    assert captured.signals == [(signal, "session-test")]
    assert captured.risk_events == [decision]
    assert captured.orders == [(order, OrderStatus.FILLED, "broker-1")]
    assert captured.fills == [fill]
    assert captured.positions[0].symbol == "MARUTI"
    assert captured.positions[0].quantity == 1
    assert captured.trades[0].symbol == "MARUTI"
    assert captured.trades[0].action == "BUY"
    assert captured.trades[0].price == Decimal("13620")
    assert bot.active_positions["MARUTI"]["order_id"] == "order-1"
    assert bot.active_positions["MARUTI"]["setup"] == "micro_volume_continuation"
    assert bot.active_positions["MARUTI"]["entry_relative_volume"] == 3.1
    assert bot.active_positions["MARUTI"]["entry_atr_ratio"] == 0.0012
    assert bot.active_positions["MARUTI"]["entry_vwap_extension_atr"] == 1.4
    assert bot.active_positions["MARUTI"]["expected_r"] == 2.0


def test_position_exit_persists_closed_snapshot_and_realized_pnl():
    bot = _bot_stub()
    bot.bot_id = "bot-test"
    bot.current_session_id = "session-test"
    bot.paper_trading = True

    captured = SimpleNamespace(positions=[], trades=[])
    bot._audit_repositories = SimpleNamespace(
        positions=SimpleNamespace(put_snapshot=captured.positions.append),
        pnl=SimpleNamespace(put_trade_event=captured.trades.append),
    )

    bot._record_position_exit(
        "ASIANPAINT",
        {
            "quantity": 2,
            "entry_price": Decimal("2785.20"),
            "side": OrderSide.BUY,
            "order_id": "order-1",
            "signal_id": "signal-1",
        },
        Decimal("2779.20"),
        OrderStatus.FILLED,
        "stop loss hit",
    )

    assert captured.positions[0].symbol == "ASIANPAINT"
    assert captured.positions[0].quantity == 0
    assert captured.positions[0].status == "CLOSED"
    assert captured.trades[0].action == "SELL"
    assert captured.trades[0].quantity == 2
    assert captured.trades[0].gross_pnl == Decimal("-12.00")
    assert captured.trades[0].costs == Decimal("5.56440")
    assert captured.trades[0].pnl == Decimal("-17.56440")
    assert captured.trades[0].net_pnl == Decimal("-17.56440")
    assert bot.daily_pnl == -17.56440
    assert bot.consecutive_losses == 1


def test_short_position_exit_pnl_is_positive_when_price_falls():
    bot = _bot_stub()
    bot.bot_id = "bot-test"
    bot.current_session_id = "session-test"
    bot.paper_trading = True

    captured = SimpleNamespace(positions=[], trades=[])
    bot._audit_repositories = SimpleNamespace(
        positions=SimpleNamespace(put_snapshot=captured.positions.append),
        pnl=SimpleNamespace(put_trade_event=captured.trades.append),
    )

    bot._record_position_exit(
        "RELIANCE",
        {
            "quantity": -3,
            "entry_price": Decimal("1400"),
            "side": OrderSide.SELL,
            "order_id": "order-2",
            "signal_id": "signal-2",
        },
        Decimal("1395"),
        OrderStatus.FILLED,
        "target hit",
    )

    assert captured.positions[0].side == "SHORT"
    assert captured.trades[0].action == "BUY"
    assert captured.trades[0].gross_pnl == Decimal("15")
    assert captured.trades[0].costs == Decimal("4.1925")
    assert captured.trades[0].pnl == Decimal("10.8075")


def test_micro_early_invalidation_detects_momentum_fade_for_long():
    bot = _bot_stub()
    bot.micro_engine = SimpleNamespace(
        market_data_provider=SimpleNamespace(
            get_historical_data=lambda symbol, days, interval: {
                "symbol": symbol,
                "data": [
                    {"timestamp": "2026-08-14T04:45:00+00:00", "open": 101, "high": 102, "low": 100, "close": 101, "volume": 1000},
                    {"timestamp": "2026-08-14T04:46:00+00:00", "open": 101, "high": 101, "low": 99, "close": 100, "volume": 1100},
                    {"timestamp": "2026-08-14T04:47:00+00:00", "open": 100, "high": 100, "low": 96, "close": 97, "volume": 1600},
                    {"timestamp": "2026-08-14T04:48:00+00:00", "open": 97, "high": 98, "low": 94, "close": 95, "volume": 1800},
                ],
            }
        )
    )
    position = {
        "quantity": 10,
        "side": OrderSide.BUY,
        "entry_price": Decimal("101"),
        "setup": "micro_volume_continuation",
        "opened_at": (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat(),
    }

    reason = bot._micro_early_invalidation_reason("MARUTI", position, Decimal("95"))

    assert reason is not None
    assert reason.startswith("early_invalidation:momentum_fade")
