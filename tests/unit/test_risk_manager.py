from datetime import datetime, timezone
from decimal import Decimal

from agent.contracts.risk import RiskDecisionStatus
from agent.contracts.signals import RiskLevel, SignalAction, TradeSignal
from agent.risk.manager import RiskLimits, RiskManager, RiskState


def make_signal(**overrides):
    data = {
        "signal_id": "sig-1",
        "symbol": "RELIANCE",
        "action": SignalAction.BUY,
        "confidence": 80,
        "generated_at": datetime.now(timezone.utc),
        "entry_price": Decimal("100"),
        "stop_loss": Decimal("95"),
        "target_price": Decimal("112"),
        "holding_window_minutes": 30,
        "risk_level": RiskLevel.MEDIUM,
    }
    data.update(overrides)
    return TradeSignal(**data)


def make_manager(**overrides):
    data = {
        "capital": Decimal("100000"),
        "max_daily_loss_percent": Decimal("4"),
        "max_position_size_percent": Decimal("10"),
        "min_confidence": 70,
        "max_quantity_per_order": 50,
    }
    data.update(overrides)
    return RiskManager(RiskLimits(**data))


def rejection_reasons(decision):
    return " | ".join(decision.reasons)


def test_approves_actionable_signal_with_limit_order_fields():
    decision = make_manager().evaluate(make_signal())

    assert decision.status == RiskDecisionStatus.APPROVED
    assert decision.approved_quantity == 50
    assert decision.approved_price == Decimal("100")
    assert decision.side == "BUY"
    assert decision.order_type == "LIMIT"
    assert decision.max_loss_amount == Decimal("4000")


def test_rejects_low_confidence_signal():
    decision = make_manager().evaluate(make_signal(confidence=60))

    assert decision.status == RiskDecisionStatus.REJECTED
    assert "confidence 60% below minimum 70%" in rejection_reasons(decision)


def test_rejects_high_risk_signal():
    decision = make_manager().evaluate(make_signal(risk_level=RiskLevel.HIGH))

    assert decision.status == RiskDecisionStatus.REJECTED
    assert "risk level HIGH" in rejection_reasons(decision)


def test_rejects_when_daily_loss_limit_is_breached():
    decision = make_manager().evaluate(
        make_signal(),
        RiskState(daily_pnl=Decimal("-4000")),
    )

    assert decision.status == RiskDecisionStatus.REJECTED
    assert "daily loss limit breached" in rejection_reasons(decision)


def test_rejects_when_new_trade_cutoff_is_reached():
    decision = make_manager().evaluate(
        make_signal(),
        RiskState(new_trades_allowed=False),
    )

    assert decision.status == RiskDecisionStatus.REJECTED
    assert "new-trade cutoff reached" in rejection_reasons(decision)


def test_rejects_after_three_consecutive_losses():
    decision = make_manager().evaluate(
        make_signal(),
        RiskState(consecutive_losses=3),
    )

    assert decision.status == RiskDecisionStatus.REJECTED
    assert "consecutive loss limit breached" in rejection_reasons(decision)


def test_rejects_hold_signal_with_reason():
    decision = make_manager().evaluate(
        make_signal(action=SignalAction.HOLD, entry_price=None, stop_loss=None, target_price=None, holding_window_minutes=None)
    )

    assert decision.status == RiskDecisionStatus.REJECTED
    assert "signal action is HOLD" in rejection_reasons(decision)


def test_rejects_when_position_size_rounds_to_zero():
    decision = make_manager(capital=Decimal("100")).evaluate(
        make_signal(entry_price=Decimal("100000"), stop_loss=Decimal("99000"), target_price=Decimal("101000"))
    )

    assert decision.status == RiskDecisionStatus.REJECTED
    assert "position size rounds to zero" in rejection_reasons(decision)


def test_sell_signal_maps_to_sell_side():
    decision = make_manager().evaluate(
        make_signal(
            action=SignalAction.SELL,
            entry_price=Decimal("100"),
            stop_loss=Decimal("105"),
            target_price=Decimal("90"),
        )
    )

    assert decision.status == RiskDecisionStatus.APPROVED
    assert decision.side == "SELL"
