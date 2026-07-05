from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class TradeLike(Protocol):
    net_pnl: Decimal


@dataclass(frozen=True)
class PerformanceReport:
    total_trades: int
    win_rate: Decimal
    expectancy: Decimal
    max_drawdown: Decimal
    profit_factor: Decimal
    consecutive_losses: int
    net_pnl: Decimal


def calculate_performance_report(trades: list[TradeLike]) -> PerformanceReport:
    if not trades:
        return PerformanceReport(
            total_trades=0,
            win_rate=Decimal("0"),
            expectancy=Decimal("0"),
            max_drawdown=Decimal("0"),
            profit_factor=Decimal("0"),
            consecutive_losses=0,
            net_pnl=Decimal("0"),
        )

    pnls = [trade.net_pnl for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    gross_profit = sum(wins, Decimal("0"))
    gross_loss = abs(sum(losses, Decimal("0")))
    net_pnl = sum(pnls, Decimal("0"))

    return PerformanceReport(
        total_trades=len(trades),
        win_rate=Decimal(len(wins)) / Decimal(len(trades)) * Decimal("100"),
        expectancy=net_pnl / Decimal(len(trades)),
        max_drawdown=_max_drawdown(pnls),
        profit_factor=gross_profit / gross_loss if gross_loss else Decimal("0"),
        consecutive_losses=_max_consecutive_losses(pnls),
        net_pnl=net_pnl,
    )


def _max_drawdown(pnls: list[Decimal]) -> Decimal:
    equity = Decimal("0")
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


def _max_consecutive_losses(pnls: list[Decimal]) -> int:
    current = 0
    worst = 0
    for pnl in pnls:
        if pnl < 0:
            current += 1
            worst = max(worst, current)
        else:
            current = 0
    return worst
