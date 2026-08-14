from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

import containers.dashboard.api_server as dashboard


NOW = datetime(2026, 7, 6, 9, 30, tzinfo=timezone.utc).isoformat()


class FakeStore(dashboard.DashboardStore):
    def __init__(self):
        self.tables = {
            dashboard.TRADES_TABLE_NAME: [
                {
                    "tradeId": "trade-1",
                    "timestamp": NOW,
                    "date": "2026-07-06",
                    "stock_symbol": "RELIANCE",
                    "action": "BUY",
                    "price": Decimal("2800"),
                    "quantity": 2,
                    "pnl": Decimal("100"),
                },
                {
                    "tradeId": "trade-2",
                    "timestamp": NOW,
                    "date": "2026-07-06",
                    "stock_symbol": "INFY",
                    "action": "SELL",
                    "price": Decimal("1500"),
                    "quantity": 1,
                    "pnl": Decimal("-25"),
                }
            ],
            dashboard.MARKET_STATE_TABLE_NAME: [
                {
                    "date": "heartbeat#trading-bot",
                    "timestamp": NOW,
                    "record_type": "bot_heartbeat",
                    "status": "market_cycle_complete",
                    "mode": "paper",
                    "cycle": 4,
                    "market_open": True,
                    "active_positions": 1,
                    "daily_pnl": Decimal("100"),
                },
                {
                    "date": "2026-07-06",
                    "timestamp": "state#news",
                    "record_type": "news",
                    "latest_sentiment": Decimal("0.25"),
                    "realtime_updated_at": NOW,
                    "realtime_news_updates": [
                        {
                            "timestamp": NOW,
                            "new_news_count": 1,
                            "sentiment_update": Decimal("0.25"),
                            "has_breaking": True,
                            "headlines": ["SEBI circular on settlement margins"],
                        }
                    ],
                },
                {
                    "date": "2026-07-06",
                    "timestamp": "state#global_macro",
                    "record_type": "global_macro",
                    "updated_at": NOW,
                    "global_sentiment": "negative",
                }
            ],
            dashboard.POSITIONS_TABLE_NAME: [
                {
                    "symbol": "RELIANCE",
                    "session_id": "session-1",
                    "quantity": 2,
                    "average_price": Decimal("2800"),
                    "last_price": Decimal("2850"),
                    "unrealized_pnl": Decimal("100"),
                    "status": "OPEN",
                    "updated_at": NOW,
                }
            ],
            dashboard.SIGNALS_TABLE_NAME: [
                {
                    "signal_id": "sig-1",
                    "symbol": "RELIANCE",
                    "action": "BUY",
                    "confidence": 82,
                    "created_at": NOW,
                    "reasons": ["momentum"],
                    "raw_features": {
                        "source_quality": {
                            "score": Decimal("0.95"),
                            "reasons": [],
                            "live_trade_blocked": False,
                        }
                    },
                },
                {
                    "signal_id": "sig-2",
                    "symbol": "TCS",
                    "action": "BUY",
                    "confidence": 58,
                    "created_at": NOW,
                    "reasons": ["setup forming"],
                    "raw_features": {
                        "source_quality": {
                            "score": Decimal("0.45"),
                            "reasons": ["global_news unavailable"],
                            "live_trade_blocked": True,
                        }
                    },
                },
            ],
            dashboard.RISK_EVENTS_TABLE_NAME: [
                {
                    "risk_decision_id": "risk-1",
                    "signal_id": "sig-1",
                    "status": "APPROVED",
                    "created_at": NOW,
                    "reasons": [],
                },
                {
                    "risk_decision_id": "risk-2",
                    "signal_id": "sig-2",
                    "status": "REJECTED",
                    "created_at": NOW,
                    "reasons": ["confidence below threshold"],
                },
            ],
            dashboard.LEARNING_TABLE_NAME: [],
        }

    def scan(self, table_name: str, *, limit: int | None = None):
        items = list(self.tables.get(table_name, []))
        return items[:limit] if limit else items

    def put(self, table_name: str, item):
        self.tables.setdefault(table_name, []).append(item)


def client_with_store(store):
    dashboard.app.dependency_overrides[dashboard.get_store] = lambda: store
    return TestClient(dashboard.app)


def teardown_function():
    dashboard.app.dependency_overrides.clear()
    dashboard.DASHBOARD_CONTROL_TOKEN = None


def test_dashboard_root_and_health_work_without_dynamodb_client():
    client = client_with_store(FakeStore())

    root = client.get("/")
    health = client.get("/api/health")

    assert root.status_code == 200
    assert "intelligenceCard" in root.text
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    assert "signals" in health.json()["tables"]


def test_dashboard_status_shows_heartbeat_risk_pnl_and_open_positions():
    client = client_with_store(FakeStore())

    response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "market_cycle_complete"
    assert body["mode"] == "paper"
    assert body["today_pnl"] == 75.0
    assert body["active_positions"] == 1
    assert body["open_positions"][0]["symbol"] == "RELIANCE"
    assert body["risk_usage"]["today_profit"] == 100.0
    assert body["risk_usage"]["today_loss"] == 25.0
    assert body["risk_usage"]["trade_count"] == 2


def test_dashboard_signals_include_skipped_trade_reasons():
    client = client_with_store(FakeStore())

    response = client.get("/api/signals")
    skipped = client.get("/api/skipped-trades")

    assert response.status_code == 200
    rows = response.json()["signals"]
    assert {row["trade_status"] for row in rows} == {"APPROVED", "SKIPPED"}
    assert skipped.json()["skipped_trades"][0]["skip_reasons"] == ["confidence below threshold"]


def test_dashboard_intelligence_shows_source_health_and_latest_events():
    client = client_with_store(FakeStore())

    response = client.get("/api/intelligence")

    assert response.status_code == 200
    body = response.json()
    assert body["source_health"]["status"] == "blocked"
    assert body["source_health"]["live_trade_blocked"] is True
    assert body["source_health"]["reasons"] == ["global_news unavailable"]
    assert body["latest_news"]["headlines"] == ["SEBI circular on settlement margins"]
    assert body["global_macro"]["global_sentiment"] == "negative"
    assert body["events"][0]["type"] == "news"


def test_dashboard_controls_require_token_and_write_safe_command():
    store = FakeStore()
    client = client_with_store(store)
    dashboard.DASHBOARD_CONTROL_TOKEN = "secret-token"

    rejected = client.post("/api/controls/kill-switch", json={"reason": "manual safety stop"})
    accepted = client.post(
        "/api/controls/square-off",
        headers={"x-dashboard-token": "secret-token"},
        json={"reason": "end of day cleanup", "symbol": "RELIANCE"},
    )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json()["accepted"] is True
    assert store.tables[dashboard.MARKET_STATE_TABLE_NAME][-1]["record_type"] == "dashboard_control_command"
    assert store.tables[dashboard.MARKET_STATE_TABLE_NAME][-1]["action"] == "square_off"
