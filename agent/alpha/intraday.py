from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from agent.data.symbols import canonical_symbol
from agent.signals.technical import TechnicalFeatures, compute_technical_features


@dataclass(frozen=True)
class AlphaSetup:
    symbol: str
    action: str
    conviction: int
    setup: str
    entry_price: float | None
    stop_loss: float | None
    target_price: float | None
    reasons: list[str]
    data_quality: str
    features: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "conviction": self.conviction,
            "setup": self.setup,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "target_price": self.target_price,
            "reasons": list(self.reasons),
            "data_quality": self.data_quality,
            "features": dict(self.features),
        }


class IntradayAlphaScanner:
    """Deterministic scanner for price/volume intraday setups.

    This module looks for tradable structure first and leaves narrative/news
    validation to the LLM. It never fabricates prices when OHLCV is missing.
    """

    def __init__(
        self,
        historical_fetcher: Callable[..., dict[str, Any]] | None = None,
        *,
        interval: str = "5m",
        lookback_days: int = 5,
    ):
        self.historical_fetcher = historical_fetcher
        self.interval = interval
        self.lookback_days = lookback_days

    def analyze_symbol(self, symbol: str) -> AlphaSetup:
        canonical = canonical_symbol(symbol)
        payload = self._fetch_history(canonical)
        if payload.get("error"):
            return _hold(canonical, f"market_data_unavailable:{payload['error']}")

        try:
            features = compute_technical_features(payload)
        except Exception as exc:
            return _hold(canonical, f"technical_features_unavailable:{exc}")

        return self.score_features(features)

    def score_features(self, features: TechnicalFeatures) -> AlphaSetup:
        reasons: list[str] = []
        score = 0
        action = "HOLD"
        setup = "monitor"

        close = features.close
        atr = max(features.atr, close * 0.005)
        atr_ratio = atr / close if close > 0 else 1
        extension = abs(close - features.vwap) / atr if atr > 0 else 99

        if 0.002 <= atr_ratio <= 0.035:
            score += 10
            reasons.append("tradable intraday volatility")
        elif atr_ratio > 0.035:
            reasons.append("volatility too high for conservative intraday entry")
        else:
            reasons.append("volatility too low for meaningful intraday edge")

        if features.relative_volume >= 1.8:
            score += 25
            reasons.append(f"relative volume spike {features.relative_volume:.2f}x")
        elif features.relative_volume >= 1.25:
            score += 15
            reasons.append(f"above-average volume {features.relative_volume:.2f}x")
        else:
            reasons.append(f"weak relative volume {features.relative_volume:.2f}x")

        bullish_breakout = (
            close > features.opening_range_high
            and close > features.previous_high
            and close > features.vwap
            and features.macd > features.macd_signal
            and 50 <= features.rsi <= 72
        )
        bearish_breakdown = (
            close < features.opening_range_low
            and close < features.previous_low
            and close < features.vwap
            and features.macd < features.macd_signal
            and 28 <= features.rsi <= 50
        )

        if bullish_breakout:
            action = "BUY"
            setup = "opening_range_breakout"
            score += 45
            reasons.append("price broke opening range and previous high above VWAP")
        elif bearish_breakdown:
            action = "SELL"
            setup = "opening_range_breakdown"
            score += 45
            reasons.append("price broke opening range and previous low below VWAP")
        else:
            reasons.append(f"no confirmed breakout; trend bias is {features.trend_bias}")

        if extension <= 2.5:
            score += 10
            reasons.append("not overextended versus VWAP")
        else:
            score -= 20
            reasons.append("price overextended versus VWAP")

        if action == "BUY" and features.rsi > 72:
            action = "HOLD"
            reasons.append("RSI too stretched for new long")
        if action == "SELL" and features.rsi < 28:
            action = "HOLD"
            reasons.append("RSI too stretched for new short")

        conviction = max(0, min(95, score))
        if conviction < 70:
            action = "HOLD"

        entry = close if action in {"BUY", "SELL"} else None
        if action == "BUY":
            stop = close - atr
            target = close + (atr * 1.8)
        elif action == "SELL":
            stop = close + atr
            target = close - (atr * 1.8)
        else:
            stop = None
            target = None

        return AlphaSetup(
            symbol=features.symbol,
            action=action,
            conviction=conviction,
            setup=setup,
            entry_price=_round(entry),
            stop_loss=_round(stop),
            target_price=_round(target),
            reasons=reasons[:6],
            data_quality="ok",
            features=features.to_dict(),
        )

    def _fetch_history(self, symbol: str) -> dict[str, Any]:
        if self.historical_fetcher is None:
            from agent.tools.market_data import get_market_data

            return get_market_data().get_historical_data(
                symbol,
                days=self.lookback_days,
                interval=self.interval,
            )
        return self.historical_fetcher(symbol, days=self.lookback_days, interval=self.interval)


def _hold(symbol: str, reason: str) -> AlphaSetup:
    return AlphaSetup(
        symbol=symbol,
        action="HOLD",
        conviction=0,
        setup="data_unavailable",
        entry_price=None,
        stop_loss=None,
        target_price=None,
        reasons=[reason],
        data_quality="unavailable",
        features={},
    )


def _round(value: float | None) -> float | None:
    return round(float(value), 2) if value is not None else None
