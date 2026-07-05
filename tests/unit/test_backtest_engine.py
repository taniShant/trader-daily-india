from datetime import datetime, timedelta, timezone
from decimal import Decimal

from agent.backtest.engine import BacktestEngine
from agent.contracts.market import OHLCVBar
from agent.contracts.signals import SignalAction, TradeSignal


def bar(index: int, close: str, *, high: str | None = None, low: str | None = None) -> OHLCVBar:
    close_value = Decimal(close)
    return OHLCVBar(
        symbol="RELIANCE",
        timestamp=datetime(2026, 7, 6, 9, 15, tzinfo=timezone.utc) + timedelta(minutes=3 * index),
        interval="3m",
        open=close_value,
        high=Decimal(high or close),
        low=Decimal(low or close),
        close=close_value,
        volume=1000,
        source="test",
    )


def test_backtest_engine_passes_only_historical_bars_to_strategy():
    seen_lengths = []
    bars = [bar(0, "100"), bar(1, "101"), bar(2, "102")]

    def strategy(history):
        seen_lengths.append(len(history))
        assert history[-1] is bars[len(history) - 1]
        return None

    result = BacktestEngine().run(bars, strategy)

    assert result.trades == []
    assert seen_lengths == [1, 2, 3]


def test_backtest_engine_closes_trade_on_target_without_lookahead():
    bars = [
        bar(0, "100"),
        bar(1, "101"),
        bar(2, "102", high="106", low="101"),
    ]

    def strategy(history):
        if len(history) == 1:
            return TradeSignal(
                signal_id="sig-1",
                symbol="RELIANCE",
                action=SignalAction.BUY,
                confidence=80,
                generated_at=history[-1].timestamp,
                entry_price=Decimal("100"),
                stop_loss=Decimal("98"),
                target_price=Decimal("105"),
                holding_window_minutes=30,
            )
        return None

    result = BacktestEngine(quantity=10).run(bars, strategy)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "target"
    assert result.trades[0].gross_pnl == Decimal("50")
    assert result.trades[0].net_pnl < result.trades[0].gross_pnl
