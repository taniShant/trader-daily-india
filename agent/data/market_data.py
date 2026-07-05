from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from agent.contracts.market import OHLCVBar, Quote


def normalize_quote(
    payload: dict[str, Any],
    *,
    symbol: str,
    source: str,
    exchange: str = "NSE",
    timestamp: datetime | None = None,
) -> Quote:
    """Convert provider-specific quote payloads into the shared Quote contract."""
    return Quote(
        symbol=symbol,
        exchange=exchange,
        ltp=_decimal_from_first(payload, "ltp", "lastPrice", "last_price"),
        open=_optional_decimal_from_first(payload, "open", "Open"),
        high=_optional_decimal_from_first(payload, "high", "dayHigh", "High"),
        low=_optional_decimal_from_first(payload, "low", "dayLow", "Low"),
        previous_close=_optional_decimal_from_first(payload, "previous_close", "previousClose", "close", "Close"),
        volume=_optional_int_from_first(payload, "volume", "Volume"),
        source=source,
        timestamp=_coerce_timestamp(payload.get("timestamp") or timestamp),
    )


def normalize_ohlcv_bars(
    rows: Iterable[dict[str, Any]],
    *,
    symbol: str,
    interval: str,
    source: str,
    exchange: str = "NSE",
) -> list[OHLCVBar]:
    """Convert provider-specific OHLCV rows into shared OHLCVBar contracts."""
    bars: list[OHLCVBar] = []
    for row in rows:
        bars.append(
            OHLCVBar(
                symbol=symbol,
                exchange=exchange,
                timestamp=_coerce_timestamp(_first_present(row, "timestamp", "Datetime", "Date", "index")),
                interval=interval,
                open=_decimal_from_first(row, "open", "Open"),
                high=_decimal_from_first(row, "high", "High"),
                low=_decimal_from_first(row, "low", "Low"),
                close=_decimal_from_first(row, "close", "Close"),
                volume=_int_from_first(row, "volume", "Volume"),
                source=source,
            )
        )
    return bars


def quote_to_tool_payload(quote: Quote) -> dict[str, Any]:
    payload = quote.model_dump(mode="json")
    payload["close"] = payload.pop("previous_close", None)
    return payload


def ohlcv_bars_to_tool_payload(
    *,
    symbol: str,
    days: int,
    interval: str,
    bars: list[OHLCVBar],
) -> dict[str, Any]:
    records = [bar.model_dump(mode="json") for bar in bars]
    latest = bars[-1] if bars else None
    return {
        "symbol": symbol,
        "days": days,
        "interval": interval,
        "data": records,
        "latest_close": float(latest.close) if latest else None,
        "latest_volume": latest.volume if latest else None,
        "high_52w": float(max(bar.high for bar in bars)) if bars else None,
        "low_52w": float(min(bar.low for bar in bars)) if bars else None,
    }


def bars_to_dataframe(payload_or_bars: dict[str, Any] | list[OHLCVBar]):
    import pandas as pd

    if isinstance(payload_or_bars, dict):
        records = payload_or_bars.get("data", [])
    else:
        records = [bar.model_dump(mode="json") for bar in payload_or_bars]

    df = pd.DataFrame(records)
    if df.empty:
        return df

    for column in ["open", "high", "low", "close", "volume"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column])
    return df


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    raise ValueError(f"Missing required field; tried: {', '.join(keys)}")


def _decimal_from_first(payload: dict[str, Any], *keys: str) -> Decimal:
    value = _first_present(payload, *keys)
    return _to_decimal(value)


def _optional_decimal_from_first(payload: dict[str, Any], *keys: str) -> Decimal | None:
    try:
        return _decimal_from_first(payload, *keys)
    except ValueError:
        return None


def _int_from_first(payload: dict[str, Any], *keys: str) -> int:
    value = _first_present(payload, *keys)
    return int(value)


def _optional_int_from_first(payload: dict[str, Any], *keys: str) -> int | None:
    try:
        return _int_from_first(payload, *keys)
    except ValueError:
        return None


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _coerce_timestamp(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if hasattr(value, "to_pydatetime"):
        return _coerce_timestamp(value.to_pydatetime())
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError(f"Unsupported timestamp value: {value!r}")
