from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from agent.contracts.execution import OrderSide
from agent.signals.technical import TechnicalFeatures

from .models import MicroTradeConfig, MicroTradePlan, MicroTradeSetup


class MicroSetupDetector:
    """Classifies 5-10 minute scalping setups without LLM calls."""

    def __init__(self, config: MicroTradeConfig | None = None):
        self.config = config or MicroTradeConfig()

    def detect(self, features: TechnicalFeatures) -> MicroTradeSetup:
        reasons: list[str] = []
        close = Decimal(str(features.close))
        atr = Decimal(str(max(features.atr, features.close * 0.001)))
        atr_ratio = float(atr / close) if close > 0 else 1.0
        extension = abs(features.close - features.vwap) / float(atr) if atr > 0 else 99.0
        extension_ok = extension <= self.config.max_vwap_extension_atr
        continuation_extension_ok = extension <= self.config.max_continuation_vwap_extension_atr
        normal_volatility_ok = self.config.min_atr_ratio <= atr_ratio <= self.config.max_atr_ratio
        continuation_volatility_ok = (
            self.config.min_continuation_atr_ratio <= atr_ratio <= self.config.max_atr_ratio
        )
        extended_continuation_volume_ok = (
            extension <= self.config.max_vwap_extension_atr
            or features.relative_volume >= self.config.extended_continuation_min_relative_volume
        )

        if atr_ratio < self.config.min_continuation_atr_ratio:
            reasons.append(
                f"volatility_rejected_low atr_ratio={atr_ratio:.5f} "
                f"min_continuation={self.config.min_continuation_atr_ratio:.5f}"
            )
        elif atr_ratio < self.config.min_atr_ratio:
            reasons.append(
                f"continuation_volatility_candidate atr_ratio={atr_ratio:.5f} "
                f"normal_min={self.config.min_atr_ratio:.5f}"
            )
        elif atr_ratio > self.config.max_atr_ratio:
            reasons.append(
                f"volatility_rejected_high atr_ratio={atr_ratio:.5f} "
                f"max={self.config.max_atr_ratio:.5f}"
            )
        else:
            reasons.append(f"tradable micro volatility atr_ratio={atr_ratio:.5f}")

        if features.relative_volume >= self.config.min_relative_volume:
            reasons.append(f"relative volume confirmed {features.relative_volume:.2f}x")
        else:
            reasons.append(f"relative volume too weak {features.relative_volume:.2f}x")

        if extension_ok:
            reasons.append("price not overextended versus VWAP")
        else:
            reasons.append("price overextended versus VWAP")
        if not continuation_extension_ok:
            reasons.append(
                f"continuation extension too stretched {extension:.2f} ATR"
            )
        elif not extended_continuation_volume_ok:
            reasons.append(
                "extended continuation needs stronger relative volume "
                f"{features.relative_volume:.2f}x"
            )

        action = "HOLD"
        setup = "micro_monitor"
        confidence = 50

        bullish_orb = (
            features.close > features.opening_range_high
            and features.close > features.previous_high
            and features.close > features.vwap
            and features.macd >= features.macd_signal
            and 50 <= features.rsi <= 72
        )
        bearish_orb = (
            features.close < features.opening_range_low
            and features.close < features.previous_low
            and features.close < features.vwap
            and features.macd <= features.macd_signal
            and 28 <= features.rsi <= 50
        )
        bullish_vwap = (
            features.close > features.vwap
            and features.trend_bias == "bullish"
            and features.relative_volume >= self.config.min_relative_volume
            and 50 <= features.rsi <= 70
        )
        bearish_vwap = (
            features.close < features.vwap
            and features.trend_bias == "bearish"
            and features.relative_volume >= self.config.min_relative_volume
            and 30 <= features.rsi <= 50
        )
        bullish_continuation = (
            features.close > features.vwap
            and features.macd >= features.macd_signal
            and features.trend_bias in {"bullish", "neutral"}
            and features.relative_volume >= self.config.min_continuation_relative_volume
            and 55 <= features.rsi <= 78
        )
        bearish_continuation = (
            features.close < features.vwap
            and features.macd <= features.macd_signal
            and features.trend_bias in {"bearish", "neutral"}
            and features.relative_volume >= self.config.min_continuation_relative_volume
            and 22 <= features.rsi <= 45
        )

        tradable = (
            normal_volatility_ok
            and features.relative_volume >= self.config.min_relative_volume
            and extension <= self.config.max_vwap_extension_atr
        )
        continuation_tradable = (
            continuation_volatility_ok
            and continuation_extension_ok
            and extended_continuation_volume_ok
        )

        if tradable and bullish_orb:
            action = "BUY"
            setup = "micro_opening_range_breakout"
            confidence = 80
            reasons.append("price broke opening range and previous high above VWAP")
        elif tradable and bearish_orb:
            action = "SELL"
            setup = "micro_opening_range_breakdown"
            confidence = 80
            reasons.append("price broke opening range and previous low below VWAP")
        elif continuation_tradable and bullish_continuation:
            action = "BUY"
            setup = "micro_volume_continuation"
            confidence = 72
            reasons.append("continuation volatility accepted for high relative volume")
            reasons.append("high-volume bullish continuation with controlled VWAP extension")
        elif continuation_tradable and bearish_continuation:
            action = "SELL"
            setup = "micro_volume_continuation"
            confidence = 72
            reasons.append("continuation volatility accepted for high relative volume")
            reasons.append("high-volume bearish continuation with controlled VWAP extension")
        elif tradable and bullish_vwap:
            action = "BUY"
            setup = "micro_vwap_momentum"
            confidence = 74
            reasons.append("bullish VWAP momentum with volume")
        elif tradable and bearish_vwap:
            action = "SELL"
            setup = "micro_vwap_rejection"
            confidence = 74
            reasons.append("bearish VWAP rejection with volume")
        else:
            reasons.append("no confirmed micro setup")

        if action in {"BUY", "SELL"}:
            confidence = min(95, confidence + self._volume_bonus(features.relative_volume))

        entry = close if action in {"BUY", "SELL"} else None
        stop, target = self._prices(action, close) if entry is not None else (None, None)
        feature_payload = {
            **features.to_dict(),
            "atr_ratio": round(atr_ratio, 6),
            "vwap_extension_atr": round(extension, 4),
            "normal_volatility_ok": normal_volatility_ok,
            "continuation_volatility_ok": continuation_volatility_ok,
            "vwap_extension_ok": extension_ok,
            "continuation_extension_ok": continuation_extension_ok,
        }

        return MicroTradeSetup(
            symbol=features.symbol,
            action=action if confidence >= self.config.min_confidence else "HOLD",
            confidence=confidence,
            setup=setup,
            entry_price=entry,
            stop_loss=stop,
            target_price=target,
            reasons=reasons[:8],
            features=feature_payload,
        )

    def to_plan(self, setup: MicroTradeSetup, signal_id: str) -> MicroTradePlan:
        if not setup.is_actionable:
            raise ValueError("micro setup is not actionable")

        return MicroTradePlan(
            signal_id=signal_id,
            symbol=setup.symbol,
            side=OrderSide.BUY if setup.action == "BUY" else OrderSide.SELL,
            entry_price=setup.entry_price,
            stop_loss=setup.stop_loss,
            target_price=setup.target_price,
            confidence=setup.confidence,
            max_hold_minutes=self.config.max_hold_minutes,
            reasons=setup.reasons,
            features=setup.features,
        )

    def _prices(self, action: str, entry: Decimal) -> tuple[Decimal, Decimal]:
        if action == "BUY":
            stop = entry * (Decimal("1") - self.config.stop_pct)
            target = entry * (Decimal("1") + self.config.target_pct)
        else:
            stop = entry * (Decimal("1") + self.config.stop_pct)
            target = entry * (Decimal("1") - self.config.target_pct)
        return _money(stop), _money(target)

    @staticmethod
    def _volume_bonus(relative_volume: float) -> int:
        if relative_volume >= 3.0:
            return 10
        if relative_volume >= 2.2:
            return 6
        return 0


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
