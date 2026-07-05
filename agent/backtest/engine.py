from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from agent.backtest.costs import CostModel
from agent.contracts.market import OHLCVBar
from agent.contracts.signals import SignalAction, TradeSignal


Strategy = Callable[[Sequence[OHLCVBar]], TradeSignal | None]


@dataclass(frozen=True)
class BacktestTrade:
    symbol: str
    side: SignalAction
    quantity: int
    entry_time: str
    exit_time: str
    entry_price: Decimal
    exit_price: Decimal
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    exit_reason: str


@dataclass(frozen=True)
class BacktestResult:
    trades: list[BacktestTrade] = field(default_factory=list)

    @property
    def net_pnl(self) -> Decimal:
        return sum((trade.net_pnl for trade in self.trades), Decimal("0"))


class BacktestEngine:
    def __init__(self, *, quantity: int = 1, cost_model: CostModel | None = None):
        if quantity <= 0:
            raise ValueError("quantity must be greater than zero")
        self.quantity = quantity
        self.cost_model = cost_model or CostModel()

    def run(self, bars: Sequence[OHLCVBar], strategy: Strategy) -> BacktestResult:
        if len(bars) < 2:
            return BacktestResult()

        trades: list[BacktestTrade] = []
        open_signal: TradeSignal | None = None
        entry_bar: OHLCVBar | None = None

        for index, bar in enumerate(bars):
            if open_signal and entry_bar:
                exit_reason = self._exit_reason(open_signal, bar, is_final_bar=index == len(bars) - 1)
                if exit_reason:
                    trades.append(self._close_trade(open_signal, entry_bar, bar, exit_reason))
                    open_signal = None
                    entry_bar = None
                continue

            signal = strategy(tuple(bars[: index + 1]))
            if signal and signal.action in {SignalAction.BUY, SignalAction.SELL}:
                open_signal = signal
                entry_bar = bar

        return BacktestResult(trades=trades)

    def _exit_reason(self, signal: TradeSignal, bar: OHLCVBar, *, is_final_bar: bool) -> str | None:
        if signal.action == SignalAction.BUY:
            if signal.stop_loss is not None and bar.low <= signal.stop_loss:
                return "stop_loss"
            if signal.target_price is not None and bar.high >= signal.target_price:
                return "target"
        if signal.action == SignalAction.SELL:
            if signal.stop_loss is not None and bar.high >= signal.stop_loss:
                return "stop_loss"
            if signal.target_price is not None and bar.low <= signal.target_price:
                return "target"
        return "end_of_data" if is_final_bar else None

    def _close_trade(self, signal: TradeSignal, entry_bar: OHLCVBar, exit_bar: OHLCVBar, exit_reason: str) -> BacktestTrade:
        entry_price = signal.entry_price or entry_bar.close
        exit_price = self._exit_price(signal, exit_bar, exit_reason)
        multiplier = Decimal("1") if signal.action == SignalAction.BUY else Decimal("-1")
        gross_pnl = (exit_price - entry_price) * Decimal(self.quantity) * multiplier
        costs = self.cost_model.estimate(
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=self.quantity,
        ).total
        return BacktestTrade(
            symbol=signal.symbol,
            side=signal.action,
            quantity=self.quantity,
            entry_time=entry_bar.timestamp.isoformat(),
            exit_time=exit_bar.timestamp.isoformat(),
            entry_price=entry_price,
            exit_price=exit_price,
            gross_pnl=gross_pnl,
            costs=costs,
            net_pnl=gross_pnl - costs,
            exit_reason=exit_reason,
        )

    @staticmethod
    def _exit_price(signal: TradeSignal, bar: OHLCVBar, exit_reason: str) -> Decimal:
        if exit_reason == "stop_loss" and signal.stop_loss is not None:
            return signal.stop_loss
        if exit_reason == "target" and signal.target_price is not None:
            return signal.target_price
        return bar.close
