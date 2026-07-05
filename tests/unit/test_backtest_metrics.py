from dataclasses import dataclass
from decimal import Decimal

from agent.backtest.metrics import calculate_performance_report


@dataclass(frozen=True)
class Trade:
    net_pnl: Decimal


def test_performance_report_calculates_core_trading_metrics():
    trades = [
        Trade(Decimal("100")),
        Trade(Decimal("-40")),
        Trade(Decimal("-20")),
        Trade(Decimal("80")),
    ]

    report = calculate_performance_report(trades)

    assert report.total_trades == 4
    assert report.win_rate == Decimal("50.0")
    assert report.expectancy == Decimal("30")
    assert report.max_drawdown == Decimal("60")
    assert report.profit_factor == Decimal("3")
    assert report.consecutive_losses == 2
    assert report.net_pnl == Decimal("120")


def test_performance_report_handles_empty_trade_list():
    report = calculate_performance_report([])

    assert report.total_trades == 0
    assert report.win_rate == Decimal("0")
    assert report.max_drawdown == Decimal("0")
