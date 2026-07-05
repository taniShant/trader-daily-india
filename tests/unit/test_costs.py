from decimal import Decimal

from agent.backtest.costs import CostModel


def test_cost_model_includes_brokerage_taxes_and_slippage():
    model = CostModel(
        brokerage_bps=Decimal("1"),
        taxes_bps=Decimal("2"),
        slippage_bps=Decimal("3"),
    )

    costs = model.estimate(entry_price=Decimal("100"), exit_price=Decimal("110"), quantity=10)

    assert costs.brokerage == Decimal("0.21")
    assert costs.taxes == Decimal("0.42")
    assert costs.slippage == Decimal("0.63")
    assert costs.total == Decimal("1.26")


def test_cost_model_reduces_gross_pnl_to_net_pnl():
    model = CostModel(brokerage_bps=Decimal("10"), taxes_bps=Decimal("10"), slippage_bps=Decimal("10"))

    net = model.net_pnl(
        gross_pnl=Decimal("100"),
        entry_price=Decimal("100"),
        exit_price=Decimal("110"),
        quantity=10,
    )

    assert net == Decimal("93.7")
