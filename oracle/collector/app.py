from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field


class MarketContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    as_of: str
    macro: dict[str, Any] = Field(default_factory=dict)
    news: list[dict[str, Any]] = Field(default_factory=list)
    sentiment_score: float = 0
    key_headlines: list[str] = Field(default_factory=list)


class CollectorSettings(BaseModel):
    mode: str = "mock"
    static_ip: str = "80.225.242.6"
    api_key: str | None = None
    secret_key: str | None = None
    session_token: str | None = None


def load_settings() -> CollectorSettings:
    return CollectorSettings(
        mode=os.environ.get("ORACLE_COLLECTOR_MODE", "mock").lower(),
        static_ip=os.environ.get("ORACLE_STATIC_IP", "80.225.242.6"),
        api_key=os.environ.get("ICICI_API_KEY"),
        secret_key=os.environ.get("ICICI_SECRET_KEY"),
        session_token=os.environ.get("ICICI_SESSION_TOKEN"),
    )


def default_market_context() -> dict[str, Any]:
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "macro": {},
        "news": [],
        "sentiment_score": 0,
        "key_headlines": [],
    }


class BreezeMarketDataClient:
    def __init__(self, settings: CollectorSettings):
        if not all([settings.api_key, settings.secret_key, settings.session_token]):
            raise RuntimeError("ICICI Breeze credentials are required for live collector mode")
        try:
            from breeze_connect import BreezeConnect
        except ImportError as exc:
            raise RuntimeError("breeze-connect is not installed") from exc

        self.client = BreezeConnect(api_key=settings.api_key)
        self.client.generate_session(
            api_secret=settings.secret_key,
            session_token=settings.session_token,
        )

    def quote(self, symbol: str) -> dict[str, Any]:
        response = self.client.get_quotes(stock_code=_breeze_stock_code(symbol), exchange_code="NSE")
        payload = _success_payload(response)
        if isinstance(payload, list):
            if not payload:
                raise RuntimeError("Breeze returned an empty quote list")
            payload = payload[0]
        if not isinstance(payload, dict):
            raise RuntimeError("Breeze returned an invalid quote payload")
        return _normalize_quote_payload(payload, symbol=symbol, source="breeze")

    def ohlcv(self, symbol: str, *, interval: str, days: int) -> dict[str, Any]:
        breeze_interval = _to_breeze_interval(interval)
        from_date, to_date = _breeze_date_range(days=days, interval=interval)
        request = {
            "interval": breeze_interval,
            "from_date": _breeze_datetime(from_date),
            "to_date": _breeze_datetime(to_date),
            "stock_code": _breeze_stock_code(symbol),
            "exchange_code": "NSE",
            "product_type": "cash",
        }
        if hasattr(self.client, "get_historical_data_v2"):
            response = self.client.get_historical_data_v2(**request)
        else:
            response = self.client.get_historical_data(**request)
        rows = _success_payload(response)
        if not isinstance(rows, list):
            raise RuntimeError("Breeze returned an invalid OHLCV payload")
        bars = [_normalize_ohlcv_payload(row, symbol=symbol, interval=interval, source="breeze") for row in rows]
        return _ohlcv_response(symbol=symbol, days=days, interval=interval, bars=bars)


def create_app() -> FastAPI:
    app = FastAPI(title="Oracle Market Context Collector", version="0.1.0")
    settings = load_settings()
    app.state.market_context = default_market_context()
    app.state.settings = settings
    app.state.breeze_client = None

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "oracle-market-context-collector",
            "mode": settings.mode,
            "static_ip": settings.static_ip,
            "market_data": "mock" if settings.mode == "mock" else "breeze",
        }

    @app.get("/market-context/latest")
    def latest_market_context() -> dict[str, Any]:
        return dict(app.state.market_context)

    @app.post("/market-context/latest")
    def update_market_context(context: MarketContext) -> dict[str, Any]:
        app.state.market_context = context.model_dump(mode="json")
        return {
            "status": "stored",
            "as_of": app.state.market_context["as_of"],
        }

    @app.get("/quotes/{symbol}")
    def quote(symbol: str) -> dict[str, Any]:
        canonical = _canonical_symbol(symbol)
        if settings.mode == "mock":
            return _mock_quote(canonical)
        return _call_breeze(lambda client: client.quote(canonical))

    @app.get("/ohlcv/{symbol}")
    def ohlcv(
        symbol: str,
        days: int = Query(default=5, ge=1, le=90),
        interval: str = Query(default="5m"),
    ) -> dict[str, Any]:
        normalized_interval = _normalize_interval(interval)
        canonical = _canonical_symbol(symbol)
        if settings.mode == "mock":
            return _mock_ohlcv(canonical, days=days, interval=normalized_interval)
        return _call_breeze(lambda client: client.ohlcv(canonical, interval=normalized_interval, days=days))

    def _call_breeze(callback):
        try:
            if app.state.breeze_client is None:
                app.state.breeze_client = BreezeMarketDataClient(settings)
            return callback(app.state.breeze_client)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return app


app = create_app()


def _canonical_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    for suffix in (".NS", ".BO", ".N"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    return _ALIASES.get(cleaned, cleaned)


def _breeze_stock_code(symbol: str) -> str:
    return _BREEZE_STOCK_CODES.get(_canonical_symbol(symbol), _canonical_symbol(symbol))


def _normalize_interval(interval: str) -> str:
    mapping = {
        "1minute": "1m",
        "3minute": "3m",
        "5minute": "5m",
        "15minute": "15m",
        "30minute": "30m",
        "1day": "1d",
        "day": "1d",
    }
    normalized = mapping.get(interval.lower(), interval.lower())
    if normalized not in {"1m", "3m", "5m", "15m", "30m", "1d"}:
        raise HTTPException(status_code=400, detail=f"Unsupported interval: {interval}")
    return normalized


def _to_breeze_interval(interval: str) -> str:
    return {
        "1m": "1minute",
        "3m": "3minute",
        "5m": "5minute",
        "15m": "15minute",
        "30m": "30minute",
        "1d": "1day",
    }[interval]


def _breeze_date_range(*, days: int, interval: str) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if interval == "1d":
        return now - timedelta(days=days), now

    end_date = now.date()
    start_date = (now - timedelta(days=days)).date()
    return (
        datetime(start_date.year, start_date.month, start_date.day, 3, 45, tzinfo=timezone.utc),
        datetime(end_date.year, end_date.month, end_date.day, 10, 0, tzinfo=timezone.utc),
    )


def _breeze_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _success_payload(response: Any) -> Any:
    if not isinstance(response, dict):
        raise RuntimeError("Breeze returned a non-object response")
    if response.get("Error"):
        raise RuntimeError(str(response["Error"]))
    if "Success" not in response:
        raise RuntimeError("Breeze response is missing Success")
    return response["Success"]


def _normalize_quote_payload(payload: dict[str, Any], *, symbol: str, source: str) -> dict[str, Any]:
    return {
        "symbol": _canonical_symbol(symbol),
        "exchange": payload.get("exchange_code") or payload.get("exchange") or "NSE",
        "ltp": _first(payload, "ltp", "last_price", "lastPrice", "best_offer_price"),
        "open": _optional(payload, "open", "open_price"),
        "high": _optional(payload, "high", "high_price"),
        "low": _optional(payload, "low", "low_price"),
        "close": _optional(payload, "close", "previous_close", "previousClose"),
        "volume": _optional(payload, "volume", "total_quantity_traded"),
        "source": source,
        "timestamp": _timestamp(payload),
    }


def _normalize_ohlcv_payload(payload: dict[str, Any], *, symbol: str, interval: str, source: str) -> dict[str, Any]:
    return {
        "symbol": _canonical_symbol(symbol),
        "exchange": payload.get("exchange_code") or payload.get("exchange") or "NSE",
        "timestamp": _timestamp(payload),
        "interval": interval,
        "open": _first(payload, "open", "Open"),
        "high": _first(payload, "high", "High"),
        "low": _first(payload, "low", "Low"),
        "close": _first(payload, "close", "Close"),
        "volume": _first(payload, "volume", "Volume"),
        "source": source,
    }


def _ohlcv_response(*, symbol: str, days: int, interval: str, bars: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "symbol": _canonical_symbol(symbol),
        "days": days,
        "interval": interval,
        "data": bars,
        "latest_close": float(bars[-1]["close"]) if bars else None,
        "latest_volume": int(bars[-1]["volume"]) if bars else None,
        "high_52w": float(max(float(bar["high"]) for bar in bars)) if bars else None,
        "low_52w": float(min(float(bar["low"]) for bar in bars)) if bars else None,
    }


def _mock_quote(symbol: str) -> dict[str, Any]:
    return {
        "symbol": _canonical_symbol(symbol),
        "exchange": "NSE",
        "ltp": "100.50",
        "open": "99.80",
        "high": "101.20",
        "low": "99.10",
        "close": "99.00",
        "volume": 250000,
        "source": "oracle-mock",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _mock_ohlcv(symbol: str, *, days: int, interval: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    count = max(8, min(days * 75, 120))
    bars: list[dict[str, Any]] = []
    base = 100.0
    for index in range(count):
        close = base + (index * 0.08)
        high = close + 0.6
        low = close - 0.5
        bars.append(
            {
                "symbol": _canonical_symbol(symbol),
                "exchange": "NSE",
                "timestamp": (now - timedelta(minutes=(count - index) * 5)).isoformat(),
                "interval": interval,
                "open": f"{close - 0.2:.2f}",
                "high": f"{high:.2f}",
                "low": f"{low:.2f}",
                "close": f"{close:.2f}",
                "volume": 100000 + (index * 1000),
                "source": "oracle-mock",
            }
        )
    return _ohlcv_response(symbol=symbol, days=days, interval=interval, bars=bars)


def _first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    raise RuntimeError(f"Missing required field; tried: {', '.join(keys)}")


def _optional(payload: dict[str, Any], *keys: str) -> Any:
    try:
        return _first(payload, *keys)
    except RuntimeError:
        return None


def _timestamp(payload: dict[str, Any]) -> str:
    value = _optional(payload, "timestamp", "datetime", "date", "Date", "Datetime")
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.replace(tzinfo=timezone.utc).isoformat()
    return str(value).replace(" ", "T")


_ALIASES = {
    "NESTLE": "NESTLEIND",
    "TATAMOTORS": "TMCV",
}


_BREEZE_STOCK_CODES = {
    "ADANIPORTS": "ADAPOR",
    "RELIANCE": "RELIND",
    "INFY": "INFTEC",
    "ICICIBANK": "ICICIBANK",
    "BHARTIARTL": "BHAAIR",
    "HEROMOTOCO": "HERHON",
    "TECHM": "TECMAH",
    "ASIANPAINT": "ASIPAI",
    "HCLTECH": "HCLTEC",
    "DIVISLAB": "DIVLAB",
    "BAJFINANCE": "BAJFI",
    "BAJAJFINSV": "BAFINS",
    "EICHERMOT": "EICMOT",
    "SUNPHARMA": "SUNPHA",
    "JSWSTEEL": "JSWSTE",
}
