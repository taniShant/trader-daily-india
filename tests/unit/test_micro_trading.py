from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from agent.contracts.execution import OrderSide, OrderStatus
from agent.execution.paper_broker import PaperBroker
from agent.micro import MicroSetupDetector, MicroTradeConfig, MicroTradePosition, MicroTradeSetup, MicroTradingEngine
from agent.risk import RiskLimits, RiskManager, RiskState
from agent.signals.technical import TechnicalFeatures


def _fresh_timestamp(minutes_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


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
            trend_bias="neutral",
        )
    )

    assert setup.action == "BUY"
    assert setup.confidence >= 80
    assert setup.setup == "micro_opening_range_breakout"
    assert setup.entry_price == Decimal("110.0")
    assert setup.stop_loss == Decimal("109.73")
    assert setup.target_price == Decimal("110.55")


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


def test_micro_detector_rejects_stretched_high_volume_continuation():
    detector = MicroSetupDetector(MicroTradeConfig(min_confidence=72))
    setup = detector.detect(
        TechnicalFeatures(
            symbol="BAJAJFINSV",
            close=120.0,
            vwap=110.0,
            rsi=83.0,
            macd=2.2,
            macd_signal=1.4,
            atr=1.0,
            relative_volume=7.5,
            opening_range_high=118.0,
            opening_range_low=104.0,
            previous_high=119.0,
            previous_low=106.0,
            trend_bias="neutral",
        )
    )

    assert setup.action == "HOLD"
    assert "continuation extension too stretched" in " ".join(setup.reasons)


def test_micro_detector_allows_controlled_high_volume_continuation():
    detector = MicroSetupDetector(MicroTradeConfig(min_confidence=72))
    setup = detector.detect(
        TechnicalFeatures(
            symbol="BAJAJFINSV",
            close=113.0,
            vwap=111.5,
            rsi=68.0,
            macd=2.2,
            macd_signal=1.4,
            atr=1.0,
            relative_volume=3.1,
            opening_range_high=118.0,
            opening_range_low=104.0,
            previous_high=112.8,
            previous_low=106.0,
            trend_bias="bullish",
            latest_open=112.0,
            previous_open=111.0,
            previous_close=112.5,
        )
    )

    assert setup.action == "BUY"
    assert setup.setup == "micro_volume_continuation"
    assert setup.confidence >= 82
    assert "broke prior high" in " ".join(setup.reasons)


def test_micro_detector_rejects_unconfirmed_first_candle_continuation():
    detector = MicroSetupDetector(MicroTradeConfig(min_confidence=72))
    setup = detector.detect(
        TechnicalFeatures(
            symbol="BAJAJFINSV",
            close=113.0,
            vwap=110.0,
            rsi=68.0,
            macd=2.2,
            macd_signal=1.4,
            atr=1.0,
            relative_volume=3.1,
            opening_range_high=118.0,
            opening_range_low=104.0,
            previous_high=119.0,
            previous_low=106.0,
            trend_bias="neutral",
            latest_open=112.0,
            previous_open=112.5,
            previous_close=111.5,
        )
    )

    assert setup.action == "HOLD"
    assert setup.features["bullish_continuation_confirmed"] is False


def test_micro_detector_rejects_exceptional_first_candle_continuation():
    detector = MicroSetupDetector(MicroTradeConfig(min_confidence=72))
    setup = detector.detect(
        TechnicalFeatures(
            symbol="BAJAJFINSV",
            close=113.0,
            vwap=112.6,
            rsi=68.0,
            macd=2.2,
            macd_signal=1.4,
            atr=1.0,
            relative_volume=8.5,
            opening_range_high=118.0,
            opening_range_low=104.0,
            previous_high=113.0,
            previous_low=106.0,
            trend_bias="neutral",
            latest_open=112.0,
            previous_open=112.5,
            previous_close=111.5,
        )
    )

    assert setup.action == "HOLD"
    assert setup.features["bullish_continuation_confirmed"] is False
    assert setup.features["bullish_vwap_pullback_resumed"] is False


def test_micro_detector_rejects_extreme_continuation_extension():
    detector = MicroSetupDetector(MicroTradeConfig(min_confidence=72))
    setup = detector.detect(
        TechnicalFeatures(
            symbol="BAJAJFINSV",
            close=140.0,
            vwap=110.0,
            rsi=83.0,
            macd=2.2,
            macd_signal=1.4,
            atr=1.0,
            relative_volume=7.5,
            opening_range_high=118.0,
            opening_range_low=104.0,
            previous_high=119.0,
            previous_low=106.0,
            trend_bias="neutral",
        )
    )

    assert setup.action == "HOLD"
    assert "price overextended versus VWAP" in " ".join(setup.reasons)


def test_micro_detector_allows_high_volume_continuation_with_lower_atr():
    detector = MicroSetupDetector(MicroTradeConfig(min_confidence=72))
    setup = detector.detect(
        TechnicalFeatures(
            symbol="ASIANPAINT",
            close=2785.20,
            vwap=2780.80,
            rsi=67.11,
            macd=1.8,
            macd_signal=1.2,
            atr=2.98,
            relative_volume=3.58,
            opening_range_high=2790.0,
            opening_range_low=2760.0,
            previous_high=2784.8,
            previous_low=2755.0,
            trend_bias="bullish",
            latest_open=2783.0,
            previous_open=2780.0,
            previous_close=2784.0,
        )
    )

    assert setup.action == "BUY"
    assert setup.setup == "micro_volume_continuation"
    assert "continuation volatility accepted" in " ".join(setup.reasons)
    assert "volatility too low for micro trade" not in " ".join(setup.reasons)
    assert setup.features["atr_ratio"] < detector.config.min_atr_ratio
    assert setup.features["continuation_volatility_ok"] is True


def test_micro_detector_allows_bullish_vwap_pullback_continuation():
    detector = MicroSetupDetector(MicroTradeConfig(min_confidence=72))
    setup = detector.detect(
        TechnicalFeatures(
            symbol="MARUTI",
            close=101.0,
            vwap=100.0,
            rsi=58.0,
            macd=0.8,
            macd_signal=0.4,
            atr=1.2,
            relative_volume=1.4,
            opening_range_high=104.0,
            opening_range_low=96.0,
            previous_high=103.0,
            previous_low=99.8,
            previous_open=102.2,
            previous_close=100.5,
            latest_open=100.4,
            trend_bias="bullish",
        )
    )

    assert setup.action == "BUY"
    assert setup.setup == "micro_vwap_pullback_continuation"
    assert setup.confidence >= 76
    assert setup.features["bullish_vwap_pullback_resumed"] is True
    assert "cooled back near VWAP and resumed" in " ".join(setup.reasons)


def test_micro_detector_allows_bearish_vwap_pullback_continuation():
    detector = MicroSetupDetector(MicroTradeConfig(min_confidence=72))
    setup = detector.detect(
        TechnicalFeatures(
            symbol="TATASTEEL",
            close=99.0,
            vwap=100.0,
            rsi=42.0,
            macd=-0.8,
            macd_signal=-0.4,
            atr=1.2,
            relative_volume=1.4,
            opening_range_high=104.0,
            opening_range_low=96.0,
            previous_high=100.2,
            previous_low=97.0,
            previous_open=97.8,
            previous_close=99.6,
            latest_open=99.7,
            trend_bias="bearish",
        )
    )

    assert setup.action == "SELL"
    assert setup.setup == "micro_vwap_pullback_continuation"
    assert setup.confidence >= 76
    assert setup.features["bearish_vwap_pullback_resumed"] is True
    assert "cooled back near VWAP and resumed" in " ".join(setup.reasons)


def test_micro_detector_rejects_volatility_below_continuation_floor():
    detector = MicroSetupDetector(
        MicroTradeConfig(
            min_confidence=72,
            min_continuation_atr_ratio=0.0012,
            min_atr_ratio=0.0015,
        )
    )
    setup = detector.detect(
        TechnicalFeatures(
            symbol="MARUTI",
            close=14000.0,
            vwap=13998.0,
            rsi=64.0,
            macd=1.1,
            macd_signal=0.9,
            atr=2.0,
            relative_volume=4.0,
            opening_range_high=14020.0,
            opening_range_low=13950.0,
            previous_high=14025.0,
            previous_low=13960.0,
            trend_bias="bullish",
        )
    )

    assert setup.action == "HOLD"
    assert "volatility_rejected_low" in " ".join(setup.reasons)
    assert setup.features["continuation_volatility_ok"] is False


def test_micro_detector_uses_configured_continuation_volume_threshold():
    detector = MicroSetupDetector(
        MicroTradeConfig(
            min_confidence=72,
            min_relative_volume=1.2,
            min_continuation_relative_volume=1.6,
        )
    )
    setup = detector.detect(
        TechnicalFeatures(
            symbol="MARUTI",
            close=14120.0,
            vwap=14100.0,
            rsi=64.0,
            macd=2.0,
            macd_signal=1.2,
            atr=8.0,
            relative_volume=1.8,
            opening_range_high=14240.0,
            opening_range_low=14060.0,
            previous_high=14118.0,
            previous_low=14080.0,
            trend_bias="bullish",
            latest_open=14110.0,
            previous_open=14090.0,
            previous_close=14116.0,
        )
    )

    assert setup.action == "BUY"
    assert setup.setup == "micro_volume_continuation"


def test_micro_detector_blocks_low_volume_extended_continuation_even_when_threshold_lowered():
    detector = MicroSetupDetector(
        MicroTradeConfig(
            min_confidence=72,
            min_relative_volume=1.2,
            min_continuation_relative_volume=1.6,
        )
    )
    setup = detector.detect(
        TechnicalFeatures(
            symbol="ADANIPORTS",
            close=1703.30,
            vwap=1696.54,
            rsi=67.78,
            macd=2.0,
            macd_signal=1.2,
            atr=1.16,
            relative_volume=1.78,
            opening_range_high=1710.0,
            opening_range_low=1690.0,
            previous_high=1705.0,
            previous_low=1695.0,
            trend_bias="bullish",
        )
    )

    assert setup.action == "HOLD"
    assert "continuation extension too stretched" in " ".join(setup.reasons)


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


def test_micro_detector_uses_shorter_continuation_bracket_and_timeout():
    detector = MicroSetupDetector(MicroTradeConfig(min_confidence=72))
    setup = detector.detect(
        TechnicalFeatures(
            symbol="ASIANPAINT",
            close=2785.20,
            vwap=2780.80,
            rsi=67.11,
            macd=1.8,
            macd_signal=1.2,
            atr=2.98,
            relative_volume=3.58,
            opening_range_high=2790.0,
            opening_range_low=2760.0,
            previous_high=2784.8,
            previous_low=2755.0,
            trend_bias="bullish",
            latest_open=2783.0,
            previous_open=2780.0,
            previous_close=2784.0,
        )
    )
    plan = detector.to_plan(setup, "signal-1")

    assert setup.setup == "micro_volume_continuation"
    assert setup.stop_loss == Decimal("2781.02")
    assert setup.target_price == Decimal("2793.56")
    assert plan.max_hold_minutes == 6


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
        config=MicroTradeConfig(enabled=True, max_candle_age_seconds=999999999),
        detector=Detector(),
    )

    attempts = engine.scan_once(["MARUTI"], risk_state=RiskState(new_trades_allowed=True))

    assert len(attempts) == 1
    assert attempts[0].executed is True
    assert attempts[0].order_status == OrderStatus.FILLED
    assert broker.position_for("MARUTI") > 0


def test_micro_engine_rejects_trade_when_expected_net_cannot_clear_costs():
    class Detector:
        def detect(self, features):
            return MicroTradeSetup(
                symbol="MARUTI",
                action="BUY",
                confidence=82,
                setup="micro_volume_continuation",
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
                {"timestamp": _fresh_timestamp(2), "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000},
                {"timestamp": _fresh_timestamp(1), "open": 100, "high": 111, "low": 100, "close": 110, "volume": 2500},
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
        config=MicroTradeConfig(
            enabled=True,
            max_candle_age_seconds=999999999,
            cost_brokerage_bps=Decimal("3"),
            cost_taxes_bps=Decimal("6"),
            cost_slippage_bps=Decimal("5"),
            min_expected_net_profit=Decimal("100"),
            min_target_to_cost_ratio=Decimal("1.8"),
        ),
        detector=Detector(),
    )

    attempt = engine.scan_once(["MARUTI"], risk_state=RiskState(new_trades_allowed=True))[0]

    assert attempt.executed is False
    assert attempt.skipped_reason.startswith("entry_economics_rejected:")
    assert broker.position_for("MARUTI") == 0


def test_micro_engine_scales_min_expected_net_profit_with_notional():
    class Detector:
        def detect(self, features):
            return MicroTradeSetup(
                symbol="RELIANCE",
                action="BUY",
                confidence=82,
                setup="micro_volume_continuation",
                entry_price=Decimal("1000"),
                stop_loss=Decimal("998"),
                target_price=Decimal("1002"),
                reasons=["large notional test setup"],
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
                {"timestamp": _fresh_timestamp(2), "open": 1000, "high": 1001, "low": 999, "close": 1000, "volume": 1000},
                {"timestamp": _fresh_timestamp(1), "open": 1000, "high": 1004, "low": 1000, "close": 1000, "volume": 3500},
            ],
        }
    )
    broker = PaperBroker()
    risk_manager = RiskManager(
        RiskLimits(
            capital=Decimal("100000000"),
            max_daily_loss_percent=Decimal("4"),
            max_position_size_percent=Decimal("10"),
            min_confidence=70,
            max_quantity_per_order=5000,
        )
    )
    engine = MicroTradingEngine(
        market_data_provider=provider,
        broker=broker,
        risk_manager=risk_manager,
        config=MicroTradeConfig(
            enabled=True,
            max_candle_age_seconds=999999999,
            cost_brokerage_bps=Decimal("1"),
            cost_taxes_bps=Decimal("2"),
            cost_slippage_bps=Decimal("2"),
            min_expected_net_profit=Decimal("1000"),
            min_expected_net_profit_bps=Decimal("12"),
            min_target_to_cost_ratio=Decimal("1.4"),
        ),
        detector=Detector(),
    )

    attempt = engine.scan_once(["RELIANCE"], risk_state=RiskState(new_trades_allowed=True))[0]

    assert attempt.executed is False
    assert "expected_net=4995.00<min=6000.00" in attempt.skipped_reason
    assert "scaled_min=6000.00" in attempt.skipped_reason
    assert broker.position_for("RELIANCE") == 0


def test_micro_engine_skips_duplicate_same_direction_position():
    class Detector:
        def detect(self, features):
            return MicroTradeSetup(
                symbol="ASIANPAINT",
                action="BUY",
                confidence=82,
                setup="micro_volume_continuation",
                entry_price=Decimal("2785.20"),
                stop_loss=Decimal("2779.63"),
                target_price=Decimal("2796.34"),
                reasons=["test continuation"],
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
                {"timestamp": "2026-08-03T05:45:00+00:00", "open": 2770, "high": 2780, "low": 2768, "close": 2775, "volume": 1000},
                {"timestamp": "2026-08-03T05:46:00+00:00", "open": 2775, "high": 2788, "low": 2774, "close": 2785.2, "volume": 4000},
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
        config=MicroTradeConfig(enabled=True, max_candle_age_seconds=999999999),
        detector=Detector(),
    )

    first = engine.scan_once(["ASIANPAINT"], risk_state=RiskState(new_trades_allowed=True))[0]
    second = engine.scan_once(["ASIANPAINT"], risk_state=RiskState(new_trades_allowed=True))[0]

    assert first.executed is True
    assert second.executed is False
    assert second.skipped_reason.startswith("position_already_open:ASIANPAINT:")


def test_micro_engine_applies_reentry_cooldown_after_square_off():
    class Detector:
        def detect(self, features):
            return MicroTradeSetup(
                symbol="ASIANPAINT",
                action="BUY",
                confidence=82,
                setup="micro_volume_continuation",
                entry_price=Decimal("2785.20"),
                stop_loss=Decimal("2779.63"),
                target_price=Decimal("2796.34"),
                reasons=["test continuation"],
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
                {"timestamp": "2026-08-03T05:45:00+00:00", "open": 2770, "high": 2780, "low": 2768, "close": 2775, "volume": 1000},
                {"timestamp": "2026-08-03T05:46:00+00:00", "open": 2775, "high": 2788, "low": 2774, "close": 2785.2, "volume": 4000},
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
        config=MicroTradeConfig(enabled=True, reentry_cooldown_seconds=600, max_candle_age_seconds=999999999),
        detector=Detector(),
    )

    first = engine.scan_once(["ASIANPAINT"], risk_state=RiskState(new_trades_allowed=True))[0]
    broker.square_off("ASIANPAINT", quantity=50)
    second = engine.scan_once(["ASIANPAINT"], risk_state=RiskState(new_trades_allowed=True))[0]

    assert first.executed is True
    assert broker.position_for("ASIANPAINT") == 0
    assert second.executed is False
    assert second.skipped_reason.startswith("reentry_cooldown_active:ASIANPAINT:")


def test_micro_engine_throttles_symbol_after_recent_losses():
    class Detector:
        def detect(self, features):
            return MicroTradeSetup(
                symbol="MARUTI",
                action="BUY",
                confidence=82,
                setup="micro_volume_continuation",
                entry_price=Decimal("14000"),
                stop_loss=Decimal("13979"),
                target_price=Decimal("14042"),
                reasons=["test continuation"],
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
                {"timestamp": _fresh_timestamp(2), "open": 13980, "high": 14000, "low": 13970, "close": 13990, "volume": 1000},
                {"timestamp": _fresh_timestamp(1), "open": 13990, "high": 14020, "low": 13988, "close": 14000, "volume": 4000},
            ],
        }
    )
    engine = MicroTradingEngine(
        market_data_provider=provider,
        broker=PaperBroker(),
        risk_manager=RiskManager(
            RiskLimits(
                capital=Decimal("100000"),
                max_daily_loss_percent=Decimal("4"),
                max_position_size_percent=Decimal("10"),
                min_confidence=70,
            )
        ),
        config=MicroTradeConfig(
            enabled=True,
            loss_throttle_count=2,
            loss_throttle_window_minutes=30,
            max_candle_age_seconds=999999999,
        ),
        detector=Detector(),
    )
    recent_losses = {
        "MARUTI": [
            datetime.now(timezone.utc) - timedelta(minutes=5),
            datetime.now(timezone.utc) - timedelta(minutes=20),
        ]
    }

    attempt = engine.scan_once(
        ["MARUTI"],
        risk_state=RiskState(new_trades_allowed=True),
        recent_losses=recent_losses,
    )[0]

    assert attempt.executed is False
    assert attempt.skipped_reason == "recent_loss_throttle_active:MARUTI:2_losses/30m"


def test_micro_engine_throttles_losing_setup_for_the_day():
    class Detector:
        def detect(self, features):
            return MicroTradeSetup(
                symbol="TITAN",
                action="SELL",
                confidence=82,
                setup="micro_volume_continuation",
                entry_price=Decimal("5053.10"),
                stop_loss=Decimal("5060.68"),
                target_price=Decimal("5037.94"),
                reasons=["test continuation"],
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
                {"timestamp": _fresh_timestamp(2), "open": 5058, "high": 5060, "low": 5050, "close": 5056, "volume": 1000},
                {"timestamp": _fresh_timestamp(1), "open": 5056, "high": 5057, "low": 5050, "close": 5053.1, "volume": 4000},
            ],
        }
    )
    engine = MicroTradingEngine(
        market_data_provider=provider,
        broker=PaperBroker(),
        risk_manager=RiskManager(
            RiskLimits(
                capital=Decimal("100000000"),
                max_daily_loss_percent=Decimal("4"),
                max_position_size_percent=Decimal("10"),
                min_confidence=70,
                max_quantity_per_order=5000,
            )
        ),
        config=MicroTradeConfig(
            enabled=True,
            max_candle_age_seconds=999999999,
            setup_loss_throttle_count=2,
            setup_loss_throttle_min_trades=2,
        ),
        detector=Detector(),
    )

    attempt = engine.scan_once(
        ["TITAN"],
        risk_state=RiskState(new_trades_allowed=True),
        setup_expectancy={
            "micro_volume_continuation": {
                "trades": 2,
                "wins": 0,
                "losses": 2,
                "net_pnl": -33424.47,
            }
        },
    )[0]

    assert attempt.executed is False
    assert attempt.skipped_reason.startswith("setup_loss_throttle_active:micro_volume_continuation:")
    assert "losses=2" in attempt.skipped_reason


def test_micro_engine_exits_existing_position_on_opposite_signal_without_reversing():
    class Detector:
        def detect(self, features):
            return MicroTradeSetup(
                symbol="ASIANPAINT",
                action="SELL",
                confidence=82,
                setup="micro_volume_continuation",
                entry_price=Decimal("2768.00"),
                stop_loss=Decimal("2773.54"),
                target_price=Decimal("2756.93"),
                reasons=["test opposite continuation"],
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
                {"timestamp": "2026-08-03T05:45:00+00:00", "open": 2785, "high": 2788, "low": 2770, "close": 2780, "volume": 1000},
                {"timestamp": "2026-08-03T05:46:00+00:00", "open": 2780, "high": 2781, "low": 2767, "close": 2768, "volume": 4000},
            ],
        }
    )
    broker = PaperBroker()
    broker.positions["ASIANPAINT"] = 12
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
        config=MicroTradeConfig(enabled=True, reentry_cooldown_seconds=600, max_candle_age_seconds=999999999),
        detector=Detector(),
    )

    attempt = engine.scan_once(["ASIANPAINT"], risk_state=RiskState(new_trades_allowed=True))[0]

    assert attempt.executed is True
    assert attempt.order_status == OrderStatus.FILLED
    assert attempt.skipped_reason == "opposite_signal_exit:ASIANPAINT:12"
    assert broker.position_for("ASIANPAINT") == 0


def test_micro_engine_skips_stale_candles():
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
    engine = MicroTradingEngine(
        market_data_provider=provider,
        broker=PaperBroker(),
        risk_manager=RiskManager(
            RiskLimits(
                capital=Decimal("100000"),
                max_daily_loss_percent=Decimal("4"),
                max_position_size_percent=Decimal("10"),
                min_confidence=70,
            )
        ),
        config=MicroTradeConfig(enabled=True, max_candle_age_seconds=180),
    )

    attempt = engine.scan_once(["MARUTI"], risk_state=RiskState(new_trades_allowed=True))[0]

    assert attempt.executed is False
    assert attempt.setup.action == "HOLD"
    assert attempt.setup.setup == "micro_data_unavailable"
    assert attempt.skipped_reason.startswith("stale_candle:")


def test_micro_engine_skips_entry_when_live_quote_has_crossed_stop():
    class Detector:
        def detect(self, features):
            return MicroTradeSetup(
                symbol="JSWSTEEL",
                action="SELL",
                confidence=82,
                setup="micro_volume_continuation",
                entry_price=Decimal("100"),
                stop_loss=Decimal("101"),
                target_price=Decimal("98"),
                reasons=["test short continuation"],
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
                {"timestamp": _fresh_timestamp(2), "open": 102, "high": 103, "low": 100, "close": 102, "volume": 1000},
                {"timestamp": _fresh_timestamp(1), "open": 102, "high": 102, "low": 99, "close": 100, "volume": 3000},
            ],
        },
        get_live_quote=lambda symbol: {"symbol": symbol, "ltp": 101.5},
    )
    engine = MicroTradingEngine(
        market_data_provider=provider,
        broker=PaperBroker(),
        risk_manager=RiskManager(
            RiskLimits(
                capital=Decimal("100000"),
                max_daily_loss_percent=Decimal("4"),
                max_position_size_percent=Decimal("10"),
                min_confidence=70,
            )
        ),
        config=MicroTradeConfig(enabled=True),
        detector=Detector(),
    )

    attempt = engine.scan_once(["JSWSTEEL"], risk_state=RiskState(new_trades_allowed=True))[0]

    assert attempt.executed is False
    assert attempt.signal is not None
    assert attempt.risk_decision is not None
    assert attempt.skipped_reason == "live_price_already_above_stop:101.5"
