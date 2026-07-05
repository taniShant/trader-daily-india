import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "oracle" / "execution-proxy" / "app.py"


def load_proxy_app(monkeypatch):
    monkeypatch.setenv("ORACLE_PROXY_MODE", "mock")
    monkeypatch.setenv("ORACLE_STATIC_IP", "80.225.242.6")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ORACLE_PROXY_SHARED_SECRET", "test-secret")

    module_name = "oracle_execution_proxy_app_test"
    sys.modules.pop(module_name, None)
    monkeypatch.syspath_prepend(str(APP_PATH.parent))
    spec = importlib.util.spec_from_file_location(module_name, APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.app


def test_oracle_proxy_health_reports_mock_mode(monkeypatch):
    client = TestClient(load_proxy_app(monkeypatch))

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "mock"
    assert body["static_ip"] == "80.225.242.6"
    assert body["breeze_enabled"] == "false"


def test_oracle_proxy_accepts_mock_order_without_breeze(monkeypatch):
    client = TestClient(load_proxy_app(monkeypatch))

    response = client.post(
        "/mock/orders",
        json={
            "client_order_id": "test-order-1",
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 1,
            "price": 2500.0,
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["success"] is True
    assert body["mode"] == "mock"
    assert body["status"] == "ACCEPTED"
    assert body["client_order_id"] == "test-order-1"
    assert body["broker_order_id"].startswith("mock-")


def test_oracle_proxy_rejects_invalid_mock_limit_order(monkeypatch):
    client = TestClient(load_proxy_app(monkeypatch))

    response = client.post(
        "/mock/orders",
        json={
            "client_order_id": "test-order-2",
            "symbol": "RELIANCE",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 1,
        },
    )

    assert response.status_code == 422
