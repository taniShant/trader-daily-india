from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from agent.contracts.execution import OrderSide, OrderStatus
from agent.execution.paper_broker import PaperBroker
from agent.micro import MicroSetupDetector, MicroTradeConfig, MicroTradePosition, MicroTradeSetup, MicroTradingEngine
from agent.risk import RiskLimits, RiskManager, RiskState
from agent.signals.technical import TechnicalFeatures


def test_micro_detector_flags_clean_breakout_buy():
    detector = MicroSetupDetector(MicroTradeConfig(min_confidence=72))
    setup = detector.detect(
        TechnicalFeatures(
            symbol="MARUTI",
            close=110.0,
            vwap=108.5,
            rsi=62.0,
            macd=1.2,
            macd_signal=0.8,
            atr=1.2,
            relative_volume=2.4,
            opening_range_high=108.8,
            opening_range_low=104.0,
            previous_high=109.0,
            previous_low=106.0,
            trend_bias="bullish",
        )
    )

    assert setup.action == "BUY"
    assert setup.confidence >= 80
    assert setup.setup == "micro_opening_range_breakout"
    assert setup.entry_price == Decimal("110.0")
    assert setup.stop_loss == Decimal("109.78")
    assert setup.target_price == Decimal("110.44")


def test_micro_detector_holds_when_volume_is_weak():
    detector = MicroSetupDetector(MicroTradeConfig(min_relative_volume=1.8))
    setup = detector.detect(
        TechnicalFeatures(
            symbol="RELIANCE",
            close=110.0,
            vwap=108.5,
            rsi=62.0,
            macd=1.2,
            macd_signal=0.8,
            atr=1.2,
            relative_volume=1.1,
            opening_range_high=108.8,
            opening_range_low=104.0,
            previous_high=109.0,
            previous_low=106.0,
            trend_bias="bullish",
        )
    )

    assert setup.action == "HOLD"
    assert "relative volume too weak" in " ".join(setup.reasons)


def test_micro_position_exits_on_target_stop_and_time():
    opened_at = datetime(2026, 7, 30, 6, 0, tzinfo=timezone.utc)
    long_position = MicroTradePosition(
        symbol="MARUTI",
        side=OrderSide.BUY,
        quantity=1,
        entry_price=Decimal("100"),
        stop_loss=Decimal("99"),
        target_price=Decimal("101"),
        opened_at=opened_at,
        max_hold_minutes=10,
        client_order_id="order-1",
    )
    short_position = MicroTradePosition(
        symbol="RELIANCE",
        side=OrderSide.SELL,
        quantity=1,
        entry_price=Decimal("100"),
        stop_loss=Decimal("101"),
        target_price=Decimal("99"),
        opened_at=opened_at,
        max_hold_minutes=10,
        client_order_id="order-2",
    )

    assert long_position.exit_reason(Decimal("101.1"), opened_at) == "target"
    assert long_position.exit_reason(Decimal("98.9"), opened_at) == "stop_loss"
    assert short_position.exit_reason(Decimal("98.9"), opened_at) == "target"
    assert short_position.exit_reason(Decimal("101.1"), opened_at) == "stop_loss"
    assert long_position.exit_reason(Decimal("100.1"), opened_at + timedelta(minutes=10)) == "time_exit"


def test_micro_engine_places_paper_order_after_risk_approval():
    class Detector:
        def detect(self, features):
            return MicroTradeSetup(
                symbol="MARUTI",
                action="BUY",
                confidence=82,
                setup="micro_opening_range_breakout",
                entry_price=Decimal("110"),
                stop_loss=Decimal("109.78"),
                target_price=Decimal("110.44"),
                reasons=["test setup"],
                features=features.to_dict(),
            )

        def to_plan(self, setup, signal_id):
            return MicroSetupDetector().to_plan(setup, signal_id)

    provider = SimpleNamespace(
        get_historical_data=lambda symbol, days, interval: {
            "symbol": symbol,
            "days": days,
            "interval": interval,
            "data": [
                {"timestamp": "2026-07-30T03:45:00+00:00", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000},
                {"timestamp": "2026-07-30T03:46:00+00:00", "open": 100, "high": 111, "low": 100, "close": 110, "volume": 2500},
            ],
        }
    )
    broker = PaperBroker()
    risk_manager = RiskManager(
        RiskLimits(
            capital=Decimal("100000"),
            max_daily_loss_percent=Decimal("4"),
            max_position_size_percent=Decimal("10"),
            min_confidence=70,
            max_quantity_per_order=50,
        )
    )
    engine = MicroTradingEngine(
        market_data_provider=provider,
        broker=broker,
        risk_manager=risk_manager,
        config=MicroTradeConfig(enabled=True),
        detector=Detector(),
    )

    attempts = engine.scan_once(["MARUTI"], risk_state=RiskState(new_trades_allowed=True))

    assert len(attempts) == 1
    assert attempts[0].executed is True
    assert attempts[0].order_status == OrderStatus.FILLED
    assert broker.position_for("MARUTI") > 0
