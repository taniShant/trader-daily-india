#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


app = FastAPI(title="Trading Bot Dashboard")

AWS_REGION = os.environ.get("AWS_REGION", "eu-west-2")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "prod")
TRADES_TABLE_NAME = os.environ.get("TRADES_TABLE", "svc-trd-trades-dev")
LEARNING_TABLE_NAME = os.environ.get("LEARNING_TABLE", "svc-trd-learning-dev")
MARKET_STATE_TABLE_NAME = os.environ.get("MARKET_STATE_TABLE", "svc-trd-market-state-dev")
SIGNALS_TABLE_NAME = os.environ.get("SIGNALS_TABLE", "svc-trd-signals-dev")
RISK_EVENTS_TABLE_NAME = os.environ.get("RISK_EVENTS_TABLE", "svc-trd-risk-events-dev")
ORDERS_TABLE_NAME = os.environ.get("ORDERS_TABLE", "svc-trd-orders-dev")
FILLS_TABLE_NAME = os.environ.get("FILLS_TABLE", "svc-trd-fills-dev")
POSITIONS_TABLE_NAME = os.environ.get("POSITIONS_TABLE", "svc-trd-positions-dev")
DASHBOARD_CONTROL_TOKEN = os.environ.get("DASHBOARD_CONTROL_TOKEN")
PAPER_TRADING = os.environ.get("PAPER_TRADING", "true").lower() in {"1", "true", "yes", "on"}

dashboard_root = Path(__file__).parent
static_path = dashboard_root / "static"

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("DASHBOARD_CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


class ControlRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=240)
    symbol: str | None = Field(default=None, min_length=1, max_length=32)


class DashboardStore:
    def scan(self, table_name: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    def put(self, table_name: str, item: dict[str, Any]) -> None:
        raise NotImplementedError


class DynamoDashboardStore(DashboardStore):
    def __init__(self):
        self._dynamodb = None

    @property
    def dynamodb(self):
        if self._dynamodb is None:
            import boto3

            self._dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
        return self._dynamodb

    def scan(self, table_name: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        kwargs = {"Limit": limit} if limit else {}
        response = self.dynamodb.Table(table_name).scan(**kwargs)
        return response.get("Items", [])

    def put(self, table_name: str, item: dict[str, Any]) -> None:
        self.dynamodb.Table(table_name).put_item(Item=item)


class MockDashboardStore(DashboardStore):
    def __init__(self):
        now = _now()
        self.tables = {
            TRADES_TABLE_NAME: [
                {
                    "tradeId": "mock-trade-1",
                    "date": now.date().isoformat(),
                    "timestamp": now.isoformat(),
                    "stock_symbol": "RELIANCE",
                    "action": "BUY",
                    "price": Decimal("2800"),
                    "quantity": 5,
                    "pnl": Decimal("450.50"),
                }
            ],
            MARKET_STATE_TABLE_NAME: [
                {
                    "date": "heartbeat#trading-bot",
                    "timestamp": now.isoformat(),
                    "record_type": "bot_heartbeat",
                    "status": "market_cycle_complete",
                    "mode": "paper",
                    "environment": ENVIRONMENT,
                    "cycle": 3,
                    "market_open": True,
                    "active_positions": 1,
                    "daily_pnl": Decimal("450.50"),
                },
                {
                    "date": now.date().isoformat(),
                    "timestamp": "state#news",
                    "record_type": "news",
                    "latest_sentiment": Decimal("0.2"),
                    "realtime_updated_at": now.isoformat(),
                    "realtime_news_updates": [
                        {
                            "timestamp": now.isoformat(),
                            "new_news_count": 2,
                            "sentiment_update": Decimal("0.2"),
                            "has_breaking": True,
                            "headlines": ["RBI keeps liquidity steady", "NIFTY advances on global cues"],
                        }
                    ],
                },
                {
                    "date": now.date().isoformat(),
                    "timestamp": "state#global_macro",
                    "record_type": "global_macro",
                    "updated_at": now.isoformat(),
                    "global_sentiment": "positive",
                    "data": {"us_markets": {"S&P 500": {"change_percent": Decimal("0.5")}}},
                }
            ],
            POSITIONS_TABLE_NAME: [
                {
                    "symbol": "RELIANCE",
                    "session_id": "mock-session",
                    "quantity": 5,
                    "average_price": Decimal("2800"),
                    "last_price": Decimal("2890"),
                    "unrealized_pnl": Decimal("450"),
                    "status": "OPEN",
                    "updated_at": now.isoformat(),
                }
            ],
            SIGNALS_TABLE_NAME: [
                {
                    "signal_id": "sig-1",
                    "symbol": "RELIANCE",
                    "action": "BUY",
                    "confidence": 82,
                    "created_at": now.isoformat(),
                    "reasons": ["technical momentum", "positive sentiment"],
                    "raw_features": {
                        "source_quality": {
                            "score": Decimal("0.92"),
                            "reasons": [],
                            "live_trade_blocked": False,
                        }
                    },
                },
                {
                    "signal_id": "sig-2",
                    "symbol": "TCS",
                    "action": "BUY",
                    "confidence": 61,
                    "created_at": now.isoformat(),
                    "reasons": ["weak confidence"],
                    "raw_features": {
                        "source_quality": {
                            "score": Decimal("0.4"),
                            "reasons": ["global_news unavailable"],
                            "live_trade_blocked": True,
                        }
                    },
                },
            ],
            RISK_EVENTS_TABLE_NAME: [
                {
                    "risk_decision_id": "risk-1",
                    "signal_id": "sig-1",
                    "status": "APPROVED",
                    "created_at": now.isoformat(),
                    "reasons": [],
                },
                {
                    "risk_decision_id": "risk-2",
                    "signal_id": "sig-2",
                    "status": "REJECTED",
                    "created_at": now.isoformat(),
                    "reasons": ["confidence below threshold"],
                },
            ],
            LEARNING_TABLE_NAME: [],
            ORDERS_TABLE_NAME: [],
            FILLS_TABLE_NAME: [],
        }

    def scan(self, table_name: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        items = list(self.tables.get(table_name, []))
        return items[:limit] if limit else items

    def put(self, table_name: str, item: dict[str, Any]) -> None:
        self.tables.setdefault(table_name, []).append(item)


_store: DashboardStore | None = None


def get_store() -> DashboardStore:
    global _store
    if _store is None:
        if os.environ.get("DASHBOARD_MOCK_MODE", "").lower() in {"1", "true", "yes", "on"}:
            _store = MockDashboardStore()
        else:
            _store = DynamoDashboardStore()
    return _store


@app.get("/")
async def serve_index():
    for index_path in (static_path / "index.html", dashboard_root / "index.html"):
        if index_path.exists():
            return FileResponse(index_path)
    return HTMLResponse("<h1>Trading Dashboard</h1><p>Dashboard static files are missing.</p>", status_code=200)


@app.get("/api/health")
async def health_check():
    return _json_safe(
        {
            "status": "healthy",
            "timestamp": _now().isoformat(),
            "environment": ENVIRONMENT,
            "mode": "paper" if PAPER_TRADING else "live",
            "tables": _table_names(),
            "control_auth_configured": bool(DASHBOARD_CONTROL_TOKEN),
        }
    )


@app.get("/api/status")
async def get_status(store: DashboardStore = Depends(get_store)):
    heartbeat = _latest_heartbeat(store.scan(MARKET_STATE_TABLE_NAME))
    reference_time = _parse_time(heartbeat.get("timestamp")) if heartbeat else _now()
    trades = _recent_items(store.scan(TRADES_TABLE_NAME), "timestamp", days=1, reference_time=reference_time)
    positions = [item for item in store.scan(POSITIONS_TABLE_NAME) if str(item.get("status", "OPEN")).upper() == "OPEN"]
    today_pnl = sum(_decimal(item.get("pnl", item.get("realized_pnl", 0))) for item in trades)
    risk_usage = _risk_usage(trades, today_pnl)

    return _json_safe(
        {
            "status": heartbeat.get("status", "waiting") if heartbeat else "waiting",
            "mode": heartbeat.get("mode", "paper" if PAPER_TRADING else "live") if heartbeat else "paper",
            "market_hours": "open" if _is_market_hours() else "closed",
            "heartbeat": heartbeat,
            "active_positions": len(positions),
            "open_positions": positions,
            "today_pnl": today_pnl,
            "win_rate": _win_rate(trades),
            "risk_usage": risk_usage,
            "last_analysis": heartbeat.get("timestamp") if heartbeat else None,
        }
    )


@app.get("/api/trades")
async def get_trades(
    limit: int = Query(default=50, ge=1, le=200),
    stock: str | None = None,
    days: int = Query(default=30, ge=1, le=365),
    store: DashboardStore = Depends(get_store),
):
    trades = _recent_items(store.scan(TRADES_TABLE_NAME), "timestamp", days=days)
    trades = [trade for trade in trades if trade.get("tradeId") != "bot_state"]
    if stock:
        trades = [trade for trade in trades if stock.upper() in str(trade.get("stock_symbol", "")).upper()]
    trades.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return _json_safe({"trades": trades[:limit], "total": len(trades)})


@app.get("/api/pnl")
async def get_pnl(days: int = Query(default=30, ge=1, le=365), store: DashboardStore = Depends(get_store)):
    trades = _recent_items(store.scan(TRADES_TABLE_NAME), "timestamp", days=days)
    daily: dict[str, Decimal] = {}
    for trade in trades:
        if "pnl" not in trade:
            continue
        date = str(trade.get("date") or str(trade.get("timestamp", ""))[:10])
        daily[date] = daily.get(date, Decimal("0")) + _decimal(trade.get("pnl"))

    cumulative = Decimal("0")
    dates: list[str] = []
    daily_pnl: list[Decimal] = []
    cumulative_pnl: list[Decimal] = []
    for date in sorted(daily):
        cumulative += daily[date]
        dates.append(date)
        daily_pnl.append(daily[date])
        cumulative_pnl.append(cumulative)
    return _json_safe({"dates": dates, "daily_pnl": daily_pnl, "cumulative_pnl": cumulative_pnl})


@app.get("/api/signals")
async def get_signals(
    limit: int = Query(default=100, ge=1, le=300),
    store: DashboardStore = Depends(get_store),
):
    risk_by_signal = _latest_risk_by_signal(store.scan(RISK_EVENTS_TABLE_NAME))
    signals = store.scan(SIGNALS_TABLE_NAME, limit=limit)
    rows = [_signal_row(signal, risk_by_signal.get(signal.get("signal_id"))) for signal in signals]
    rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return _json_safe({"signals": rows[:limit], "total": len(rows)})


@app.get("/api/skipped-trades")
async def get_skipped_trades(store: DashboardStore = Depends(get_store)):
    risk_by_signal = _latest_risk_by_signal(store.scan(RISK_EVENTS_TABLE_NAME))
    rows = [
        _signal_row(signal, risk_by_signal.get(signal.get("signal_id")))
        for signal in store.scan(SIGNALS_TABLE_NAME)
    ]
    skipped = [row for row in rows if row["trade_status"] == "SKIPPED"]
    skipped.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return _json_safe({"skipped_trades": skipped, "total": len(skipped)})


@app.get("/api/learning")
async def get_learning_patterns(limit: int = Query(default=20, ge=1, le=100), store: DashboardStore = Depends(get_store)):
    patterns = store.scan(LEARNING_TABLE_NAME, limit=limit)
    patterns.sort(key=lambda item: item.get("date", ""), reverse=True)
    return _json_safe({"patterns": patterns, "total": len(patterns)})


@app.get("/api/market-state")
async def get_market_state(days: int = Query(default=7, ge=1, le=60), store: DashboardStore = Depends(get_store)):
    states = _recent_items(store.scan(MARKET_STATE_TABLE_NAME), "timestamp", days=days)
    states.sort(key=lambda item: item.get("timestamp", item.get("date", "")), reverse=True)
    return _json_safe({"market_states": states, "total": len(states)})


@app.get("/api/intelligence")
async def get_intelligence(store: DashboardStore = Depends(get_store)):
    market_state = store.scan(MARKET_STATE_TABLE_NAME)
    signals = store.scan(SIGNALS_TABLE_NAME, limit=100)
    return _json_safe(_intelligence_summary(market_state, signals))


@app.post("/api/controls/kill-switch")
async def request_kill_switch(
    request: ControlRequest,
    store: DashboardStore = Depends(get_store),
    x_dashboard_token: str | None = Header(default=None),
):
    _require_control_token(x_dashboard_token)
    command = _control_command("kill_switch", request.reason, request.symbol)
    store.put(MARKET_STATE_TABLE_NAME, command)
    return _json_safe({"accepted": True, "command": command})


@app.post("/api/controls/square-off")
async def request_square_off(
    request: ControlRequest,
    store: DashboardStore = Depends(get_store),
    x_dashboard_token: str | None = Header(default=None),
):
    _require_control_token(x_dashboard_token)
    command = _control_command("square_off", request.reason, request.symbol)
    store.put(MARKET_STATE_TABLE_NAME, command)
    return _json_safe({"accepted": True, "command": command})


def _require_control_token(token: str | None) -> None:
    if not DASHBOARD_CONTROL_TOKEN:
        raise HTTPException(status_code=503, detail="Dashboard control token is not configured")
    if token != DASHBOARD_CONTROL_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid dashboard control token")


def _control_command(action: str, reason: str, symbol: str | None) -> dict[str, Any]:
    now = _now()
    return {
        "date": f"control#{action}",
        "timestamp": now.isoformat(),
        "record_type": "dashboard_control_command",
        "command_id": f"{action}-{uuid4().hex}",
        "action": action,
        "symbol": symbol,
        "reason": reason,
        "status": "REQUESTED",
        "source": "dashboard",
    }


def _latest_heartbeat(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    heartbeats = [item for item in items if item.get("record_type") == "bot_heartbeat"]
    if not heartbeats:
        return None
    return max(heartbeats, key=lambda item: item.get("timestamp", ""))


def _latest_risk_by_signal(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for item in items:
        signal_id = item.get("signal_id")
        if not signal_id:
            continue
        if signal_id not in latest or item.get("created_at", "") > latest[signal_id].get("created_at", ""):
            latest[signal_id] = item
    return latest


def _signal_row(signal: dict[str, Any], risk: dict[str, Any] | None) -> dict[str, Any]:
    status = str((risk or {}).get("status", "PENDING")).upper()
    trade_status = "APPROVED" if status == "APPROVED" else "SKIPPED" if status == "REJECTED" else "PENDING"
    return {
        **signal,
        "risk_status": status,
        "trade_status": trade_status,
        "skip_reasons": (risk or {}).get("reasons", []) if trade_status == "SKIPPED" else [],
    }


def _intelligence_summary(market_state: list[dict[str, Any]], signals: list[dict[str, Any]]) -> dict[str, Any]:
    news_state = _latest_state_record(market_state, "news")
    macro_state = _latest_state_record(market_state, "global_macro")
    source_quality = _latest_source_quality(signals)
    events = _intelligence_events(news_state, macro_state)

    source_health = {
        "status": "blocked" if source_quality.get("live_trade_blocked") else "degraded" if source_quality.get("score", 1) < 0.8 else "ok",
        "score": source_quality.get("score", 1),
        "reasons": source_quality.get("reasons", []),
        "live_trade_blocked": source_quality.get("live_trade_blocked", False),
        "latest_signal_id": source_quality.get("signal_id"),
    }

    return {
        "source_health": source_health,
        "latest_news": {
            "latest_sentiment": news_state.get("latest_sentiment", news_state.get("overnight_sentiment")),
            "updated_at": news_state.get("realtime_updated_at") or news_state.get("overnight_updated_at"),
            "headlines": _latest_headlines(news_state),
        },
        "global_macro": {
            "global_sentiment": macro_state.get("global_sentiment", "neutral"),
            "updated_at": macro_state.get("updated_at"),
            "data": macro_state.get("data", {}),
        },
        "events": events,
    }


def _latest_state_record(items: list[dict[str, Any]], record_type: str) -> dict[str, Any]:
    matching = [
        item
        for item in items
        if item.get("record_type") == record_type or item.get("timestamp") == f"state#{record_type}"
    ]
    if not matching:
        return {}
    return max(matching, key=lambda item: item.get("updated_at") or item.get("realtime_updated_at") or item.get("timestamp", ""))


def _latest_source_quality(signals: list[dict[str, Any]]) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    latest_time = ""
    for signal in signals:
        raw = signal.get("raw_features") or {}
        source_quality = raw.get("source_quality") or {}
        if not source_quality:
            continue
        created_at = str(signal.get("created_at") or signal.get("generated_at") or "")
        if not latest or created_at >= latest_time:
            latest = dict(source_quality)
            latest["signal_id"] = signal.get("signal_id")
            latest_time = created_at
    return latest


def _latest_headlines(news_state: dict[str, Any]) -> list[str]:
    updates = news_state.get("realtime_news_updates") or []
    if updates:
        latest = max(updates, key=lambda item: item.get("timestamp", ""))
        return list(latest.get("headlines") or [])

    overnight = news_state.get("overnight_news") or {}
    headlines = overnight.get("key_headlines") or []
    if headlines:
        return list(headlines)

    return [
        str(item.get("title"))
        for item in (overnight.get("global_news") or []) + (overnight.get("india_overnight_news") or [])
        if item.get("title")
    ][:5]


def _intelligence_events(news_state: dict[str, Any], macro_state: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for headline in _latest_headlines(news_state):
        events.append({"type": "news", "title": headline, "source": "market_state"})
    if macro_state:
        events.append(
            {
                "type": "macro",
                "title": f"Global sentiment: {macro_state.get('global_sentiment', 'neutral')}",
                "source": "global_macro",
            }
        )
    return events[:10]


def _recent_items(
    items: list[dict[str, Any]],
    timestamp_key: str,
    *,
    days: int,
    reference_time: datetime | None = None,
) -> list[dict[str, Any]]:
    anchor = reference_time or _now()
    cutoff = anchor - timedelta(days=days)
    return [item for item in items if cutoff <= _parse_time(item.get(timestamp_key)) <= anchor]


def _risk_usage(trades: list[dict[str, Any]], today_pnl: Decimal) -> dict[str, Any]:
    winning_pnl = sum((_decimal(item.get("pnl")) for item in trades if _decimal(item.get("pnl")) > 0), Decimal("0"))
    losing_pnl = abs(sum((_decimal(item.get("pnl")) for item in trades if _decimal(item.get("pnl")) < 0), Decimal("0")))
    return {
        "today_profit": winning_pnl,
        "today_loss": losing_pnl,
        "today_pnl": today_pnl,
        "daily_loss_limit": os.environ.get("MAX_DAILY_LOSS_PERCENT", "4"),
        "trade_count": len(trades),
    }


def _win_rate(trades: list[dict[str, Any]]) -> Decimal:
    if not trades:
        return Decimal("0")
    wins = [trade for trade in trades if _decimal(trade.get("pnl")) > 0]
    return Decimal(len(wins)) / Decimal(len(trades)) * Decimal("100")


def _is_market_hours() -> bool:
    now = datetime.now(timezone.utc)
    market_open = now.replace(hour=3, minute=45, second=0, microsecond=0)
    market_close = now.replace(hour=10, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


def _table_names() -> dict[str, str]:
    return {
        "trades": TRADES_TABLE_NAME,
        "learning": LEARNING_TABLE_NAME,
        "market_state": MARKET_STATE_TABLE_NAME,
        "signals": SIGNALS_TABLE_NAME,
        "risk_events": RISK_EVENTS_TABLE_NAME,
        "orders": ORDERS_TABLE_NAME,
        "fills": FILLS_TABLE_NAME,
        "positions": POSITIONS_TABLE_NAME,
    }


def _parse_time(value: Any) -> datetime:
    if not value:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def main():
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
