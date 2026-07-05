from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from agent.contracts.market import OHLCVBar
from agent.data.market_data import bars_to_dataframe


@dataclass(frozen=True)
class TechnicalFeatures:
    symbol: str
    close: float
    vwap: float
    rsi: float
    macd: float
    macd_signal: float
    atr: float
    relative_volume: float
    opening_range_high: float
    opening_range_low: float
    previous_high: float
    previous_low: float
    trend_bias: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def compute_technical_features(payload_or_bars: dict[str, Any] | list[OHLCVBar]) -> TechnicalFeatures:
    df = bars_to_dataframe(payload_or_bars).copy()
    if df.empty or len(df) < 2:
        raise ValueError("at least two OHLCV bars are required")

    symbol = _symbol_from_payload(payload_or_bars, df)
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column])

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    typical_price = (high + low + close) / 3
    vwap = (typical_price * volume).sum() / volume.sum() if volume.sum() > 0 else close.iloc[-1]
    rsi = _rsi(close)
    macd_line, macd_signal = _macd(close)
    atr = _atr(high, low, close)
    avg_volume = volume.iloc[:-1].mean() if len(volume) > 1 else volume.mean()
    relative_volume = volume.iloc[-1] / avg_volume if avg_volume > 0 else 0
    opening_slice = df.head(min(3, len(df)))
    previous = df.iloc[-2]
    latest_close = float(close.iloc[-1])

    return TechnicalFeatures(
        symbol=symbol,
        close=round(latest_close, 4),
        vwap=round(float(vwap), 4),
        rsi=round(float(rsi), 4),
        macd=round(float(macd_line), 4),
        macd_signal=round(float(macd_signal), 4),
        atr=round(float(atr), 4),
        relative_volume=round(float(relative_volume), 4),
        opening_range_high=round(float(opening_slice["high"].max()), 4),
        opening_range_low=round(float(opening_slice["low"].min()), 4),
        previous_high=round(float(previous["high"]), 4),
        previous_low=round(float(previous["low"]), 4),
        trend_bias=_trend_bias(latest_close, float(vwap), float(rsi), float(macd_line), float(macd_signal)),
    )


def _symbol_from_payload(payload_or_bars: dict[str, Any] | list[OHLCVBar], df) -> str:
    if isinstance(payload_or_bars, dict):
        return str(payload_or_bars.get("symbol") or df.iloc[-1].get("symbol"))
    return payload_or_bars[-1].symbol


def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period, min_periods=1).mean()
    avg_loss = loss.rolling(period, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    value = rsi.iloc[-1]
    if pd.isna(value):
        return 100.0 if avg_gain.iloc[-1] > 0 else 50.0
    return float(value)


def _macd(close: pd.Series) -> tuple[float, float]:
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal = macd_line.ewm(span=9, adjust=False).mean()
    return float(macd_line.iloc[-1]), float(signal.iloc[-1])


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return float(true_range.rolling(period, min_periods=1).mean().iloc[-1])


def _trend_bias(close: float, vwap: float, rsi: float, macd: float, macd_signal: float) -> str:
    bullish = close >= vwap and macd >= macd_signal and rsi >= 50
    bearish = close < vwap and macd < macd_signal and rsi < 50
    if bullish:
        return "bullish"
    if bearish:
        return "bearish"
    return "neutral"
