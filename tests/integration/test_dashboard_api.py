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
                },
                {
                    "signal_id": "sig-2",
                    "symbol": "TCS",
                    "action": "BUY",
                    "confidence": 58,
                    "created_at": NOW,
                    "reasons": ["setup forming"],
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
    assert body["today_pnl"] == 100.0
    assert body["active_positions"] == 1
    assert body["open_positions"][0]["symbol"] == "RELIANCE"
    assert body["risk_usage"]["trade_count"] == 1


def test_dashboard_signals_include_skipped_trade_reasons():
    client = client_with_store(FakeStore())

    response = client.get("/api/signals")
    skipped = client.get("/api/skipped-trades")

    assert response.status_code == 200
    rows = response.json()["signals"]
    assert {row["trade_status"] for row in rows} == {"APPROVED", "SKIPPED"}
    assert skipped.json()["skipped_trades"][0]["skip_reasons"] == ["confidence below threshold"]


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
