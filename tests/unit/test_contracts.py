from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agent.contracts import (
    Fill,
    OHLCVBar,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Quote,
    RiskDecision,
    RiskDecisionStatus,
    SignalAction,
    TradeSignal,
)


NOW = datetime(2026, 6, 29, 9, 30, tzinfo=timezone.utc)


def test_quote_validates_price_range():
    quote = Quote(
        symbol="RELIANCE",
        ltp="2800.50",
        open="2790",
        high="2810",
        low="2780",
        previous_close="2775",
        volume=1000000,
        source="breeze",
        timestamp=NOW,
    )

    assert quote.symbol == "RELIANCE"
    assert quote.exchange == "NSE"


def test_quote_rejects_ltp_outside_day_range():
    with pytest.raises(ValidationError, match="ltp cannot be greater than high"):
        Quote(
            symbol="RELIANCE",
            ltp="2820",
            high="2810",
            low="2780",
            source="breeze",
            timestamp=NOW,
        )


def test_ohlcv_bar_validates_ohlc_range():
    bar = OHLCVBar(
        symbol="TCS",
        timestamp=NOW,
        interval="5m",
        open="3900",
        high="3925",
        low="3890",
        close="3910",
        volume=250000,
        source="yfinance",
    )

    assert bar.interval == "5m"


def test_ohlcv_bar_rejects_close_outside_range():
    with pytest.raises(ValidationError, match="close must be within low/high range"):
        OHLCVBar(
            symbol="TCS",
            timestamp=NOW,
            interval="5m",
            open="3900",
            high="3925",
            low="3890",
            close="3930",
            volume=250000,
            source="yfinance",
        )


def test_buy_signal_requires_valid_stop_and_target():
    signal = TradeSignal(
        signal_id="sig-1",
        symbol="INFY",
        action=SignalAction.BUY,
        confidence=78,
        generated_at=NOW,
        entry_price="1500",
        stop_loss="1470",
        target_price="1545",
        holding_window_minutes=45,
        reasons=["trend and volume aligned"],
    )

    assert signal.action == SignalAction.BUY


def test_actionable_signal_rejects_missing_stop_loss():
    with pytest.raises(ValidationError, match="actionable signals require"):
        TradeSignal(
            signal_id="sig-2",
            symbol="INFY",
            action=SignalAction.BUY,
            confidence=78,
            generated_at=NOW,
            entry_price="1500",
            target_price="1545",
            holding_window_minutes=45,
        )


def test_sell_signal_requires_target_below_entry_and_stop_above_entry():
    with pytest.raises(ValidationError, match="SELL requires"):
        TradeSignal(
            signal_id="sig-3",
            symbol="SBIN",
            action=SignalAction.SELL,
            confidence=74,
            generated_at=NOW,
            entry_price="800",
            stop_loss="780",
            target_price="820",
            holding_window_minutes=30,
        )


def test_hold_signal_does_not_require_prices():
    signal = TradeSignal(
        signal_id="sig-4",
        symbol="HDFCBANK",
        action=SignalAction.HOLD,
        confidence=51,
        generated_at=NOW,
        reasons=["conflicting signals"],
    )

    assert signal.entry_price is None


def test_approved_risk_decision_requires_execution_fields():
    decision = RiskDecision(
        decision_id="risk-1",
        signal_id="sig-1",
        status=RiskDecisionStatus.APPROVED,
        decided_at=NOW,
        approved_quantity=10,
        approved_price="1500",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        max_loss_amount="300",
    )

    assert decision.status == RiskDecisionStatus.APPROVED


def test_rejected_risk_decision_requires_reason():
    with pytest.raises(ValidationError, match="rejected decisions require"):
        RiskDecision(
            decision_id="risk-2",
            signal_id="sig-1",
            status=RiskDecisionStatus.REJECTED,
            decided_at=NOW,
        )


def test_limit_order_requires_price():
    with pytest.raises(ValidationError, match="limit orders require price"):
        OrderRequest(
            client_order_id="order-1",
            signal_id="sig-1",
            risk_decision_id="risk-1",
            symbol="INFY",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            requested_at=NOW,
        )


def test_market_order_and_fill_validate():
    order = OrderRequest(
        client_order_id="order-2",
        signal_id="sig-1",
        risk_decision_id="risk-1",
        symbol="INFY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        requested_at=NOW,
    )
    fill = Fill(
        fill_id="fill-1",
        client_order_id=order.client_order_id,
        broker_order_id="broker-1",
        symbol="INFY",
        side=OrderSide.BUY,
        quantity=10,
        fill_price="1501.25",
        filled_at=NOW,
        source="paper",
    )

    assert fill.client_order_id == "order-2"
    assert OrderStatus.FILLED == "FILLED"
