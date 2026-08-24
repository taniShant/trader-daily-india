from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from agent.contracts.market import OHLCVBar
from agent.data.market_data import bars_to_dataframe


INDIA_TZ = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


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
    latest_open: float | None = None
    previous_open: float | None = None
    previous_close: float | None = None
    latest_timestamp: datetime | None = None
    latest_source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = self.__dict__.copy()
        if self.latest_timestamp is not None:
            payload["latest_timestamp"] = self.latest_timestamp.isoformat()
        return payload


def compute_technical_features(payload_or_bars: dict[str, Any] | list[OHLCVBar]) -> TechnicalFeatures:
    df = bars_to_dataframe(payload_or_bars).copy()
    df = _latest_ist_market_session(df)
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
    latest = df.iloc[-1]
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
        latest_open=round(float(latest["open"]), 4),
        previous_open=round(float(previous["open"]), 4),
        previous_close=round(float(previous["close"]), 4),
        latest_timestamp=_latest_timestamp(latest),
        latest_source=str(latest.get("source")) if latest.get("source") is not None else None,
    )


def _latest_ist_market_session(df):
    """Keep only the latest bar date's regular NSE session in IST.

    Breeze's ``days=1`` range can include the preceding trading session. Using
    the whole response would contaminate intraday VWAP, relative volume and the
    opening range with yesterday's bars. Selecting by the latest bar date also
    keeps historical replay deterministic instead of depending on wall-clock
    time.
    """
    import pandas as pd

    if df.empty:
        return df
    if "timestamp" not in df.columns:
        raise ValueError("OHLCV bars require timestamps for IST session filtering")

    timestamps = df["timestamp"].map(_timestamp_in_ist)
    valid = timestamps.notna()
    if not valid.any():
        raise ValueError("OHLCV bars contain no valid timestamps")

    local_times = timestamps.map(lambda value: None if pd.isna(value) else value.time())
    regular_hours = valid & local_times.map(
        lambda value: value is not None and MARKET_OPEN <= value <= MARKET_CLOSE
    )
    if not regular_hours.any():
        raise ValueError("OHLCV bars contain no regular-session IST candles")

    latest_session_date = max(value.date() for value in timestamps[regular_hours])
    same_session = regular_hours & timestamps.map(
        lambda value: not pd.isna(value) and value.date() == latest_session_date
    )
    session = df.loc[same_session].copy()
    session["timestamp"] = timestamps.loc[same_session].map(
        lambda value: value.astimezone(timezone.utc)
    )
    return session.sort_values("timestamp").reset_index(drop=True)


def _timestamp_in_ist(value):
    import pandas as pd

    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError):
        return pd.NaT
    if pd.isna(parsed):
        return pd.NaT
    if parsed.tzinfo is None:
        return parsed.tz_localize(INDIA_TZ).to_pydatetime()
    return parsed.tz_convert(INDIA_TZ).to_pydatetime()


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


def _latest_timestamp(row) -> datetime | None:
    value = row.get("timestamp")
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = pd.to_datetime(value)
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    if parsed.tzinfo is None:
        return parsed.to_pydatetime().replace(tzinfo=timezone.utc)
    return parsed.to_pydatetime().astimezone(timezone.utc)
