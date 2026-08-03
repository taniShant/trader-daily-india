from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from agent.contracts.execution import Fill, OrderRequest, OrderSide, OrderStatus, OrderType
from agent.contracts.risk import RiskDecision, RiskDecisionStatus
from agent.contracts.signals import SignalAction, TradeSignal
from agent.main import TradingBot
from agent.micro import MicroTradeSetup


def _bot_stub():
    bot = TradingBot.__new__(TradingBot)
    bot.events = []
    bot.micro_engine = object()
    bot._check_circuit_breakers = lambda: True
    bot._should_square_off = lambda: False
    bot._is_new_trade_allowed = lambda: True
    bot._run_micro_trading_cycle = lambda: bot.events.append("micro")
    bot._monitor_positions = lambda: bot.events.append("monitor")
    bot._square_off_all = lambda: bot.events.append("square_off")
    return bot


def test_micro_market_cycle_runs_fast_lane_and_monitors_positions():
    bot = _bot_stub()

    bot._run_micro_market_cycle()

    assert bot.events == ["micro", "monitor"]


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
