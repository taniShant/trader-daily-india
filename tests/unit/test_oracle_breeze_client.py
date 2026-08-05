import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.execution.oracle_breeze_client import OracleBreezeClient


ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "oracle" / "execution-proxy" / "app.py"
BREEZE_CLIENT_PATH = ROOT / "oracle" / "execution-proxy" / "breeze_client.py"
SECRET = "test-signing-secret"


def load_breeze_module(monkeypatch):
    monkeypatch.syspath_prepend(str(BREEZE_CLIENT_PATH.parent))
    sys.modules.pop("breeze_client_test", None)
    spec = importlib.util.spec_from_file_location("breeze_client_test", BREEZE_CLIENT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["breeze_client_test"] = module
    spec.loader.exec_module(module)
    return module


def load_proxy_app(monkeypatch):
    monkeypatch.setenv("ORACLE_PROXY_MODE", "mock")
    monkeypatch.setenv("ORACLE_STATIC_IP", "80.225.242.6")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ORACLE_PROXY_SHARED_SECRET", SECRET)
    monkeypatch.syspath_prepend(str(APP_PATH.parent))

    for module_name in ["oracle_execution_proxy_app_breeze_test", "auth", "breeze_client"]:
        sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location("oracle_execution_proxy_app_breeze_test", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["oracle_execution_proxy_app_breeze_test"] = module
    spec.loader.exec_module(module)
    return module.app


def signed_request(payload, *, nonce="breeze-boundary-1"):
    client = OracleBreezeClient(
        base_url="http://oracle-proxy.test",
        client_id="aws-trading-bot",
        shared_secret=SECRET,
    )
    return client.sign_json_request("POST", "/orders", payload, nonce=nonce)


def test_mock_breeze_client_returns_accepted_without_live_call(monkeypatch):
    breeze_module = load_breeze_module(monkeypatch)
    order = breeze_module.ProxyOrder(
        client_order_id="mock-order-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=breeze_module.OrderSide.BUY,
        order_type=breeze_module.OrderType.LIMIT,
        quantity=1,
        price=2500.0,
    )

    result = breeze_module.MockBreezeClient().place_order(order)

    assert result.success is True
    assert result.mode == "mock"
    assert result.status == "ACCEPTED"
    assert result.broker_order_id.startswith("mock-")


def test_icici_breeze_client_maps_proxy_order_to_breeze_place_order(monkeypatch):
    breeze_module = load_breeze_module(monkeypatch)
    calls = {}

    class FakeBreeze:
        def __init__(self, **kwargs):
            calls["init"] = kwargs

        def generate_session(self, **kwargs):
            calls["session"] = kwargs

        def place_order(self, **kwargs):
            calls["place_order"] = kwargs
            return {"Success": {"order_id": "breeze-123"}}

    client = breeze_module.IciciBreezeClient(
        api_key="api-key",
        api_secret="api-secret",
        session_token="session-token",
        breeze_factory=FakeBreeze,
    )
    order = breeze_module.ProxyOrder(
        client_order_id="live-order-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=breeze_module.OrderSide.SELL,
        order_type=breeze_module.OrderType.LIMIT,
        quantity=2,
        price=2501.5,
    )

    result = client.place_order(order)

    assert calls["init"] == {"api_key": "api-key"}
    assert calls["session"] == {"api_secret": "api-secret", "session_token": "session-token"}
    assert calls["place_order"] == {
        "stock_code": "RELIANCE",
        "exchange_code": "NSE",
        "action": "sell",
        "order_type": "limit",
        "quantity": 2,
        "validity": "day",
        "product_type": "intraday",
        "price": 2501.5,
    }
    assert result.mode == "live"
    assert result.broker_order_id == "breeze-123"


def test_live_breeze_client_requires_credentials(monkeypatch):
    breeze_module = load_breeze_module(monkeypatch)

    with pytest.raises(breeze_module.BreezeClientError, match="credentials"):
        breeze_module.IciciBreezeClient(api_key="", api_secret="", session_token="", breeze_factory=lambda **_: object())


def test_signed_proxy_order_delegates_to_execution_client(monkeypatch):
    app = load_proxy_app(monkeypatch)

    class RecordingClient:
        def __init__(self):
            self.orders = []

        def place_order(self, order):
            self.orders.append(order)
            return sys.modules["breeze_client"].ExecutionResult(
                success=True,
                status="ACCEPTED",
                client_order_id=order.client_order_id,
                broker_order_id="fake-broker-1",
                symbol=order.symbol,
                exchange=order.exchange,
                side=order.side.value,
                order_type=order.order_type.value,
                quantity=order.quantity,
                price=order.price,
                mode="mock",
                message="recorded",
                accepted_at="2026-07-02T00:00:00+00:00",
            )

    recorder = RecordingClient()
    app.state.execution_client = recorder
    client = TestClient(app)
    body, headers = signed_request(
        {
            "client_order_id": "signed-order-1",
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 3,
            "price": 2500.0,
        }
    )

    response = client.post("/orders", content=body, headers=headers)

    assert response.status_code == 202
    assert response.json()["broker_order_id"] == "fake-broker-1"
    assert len(recorder.orders) == 1
    assert recorder.orders[0].symbol == "RELIANCE"
    assert recorder.orders[0].exchange == "NSE"


def test_signed_proxy_order_always_executes_on_nse(monkeypatch):
    app = load_proxy_app(monkeypatch)

    class RecordingClient:
        def __init__(self):
            self.orders = []

        def place_order(self, order):
            self.orders.append(order)
            return sys.modules["breeze_client"].ExecutionResult(
                success=True,
                status="ACCEPTED",
                client_order_id=order.client_order_id,
                broker_order_id="fake-broker-2",
                symbol=order.symbol,
                exchange=order.exchange,
                side=order.side.value,
                order_type=order.order_type.value,
                quantity=order.quantity,
                price=order.price,
                mode="mock",
                message="recorded",
                accepted_at="2026-07-02T00:00:00+00:00",
            )

    recorder = RecordingClient()
    app.state.execution_client = recorder
    client = TestClient(app)
    body, headers = signed_request(
        {
            "client_order_id": "signed-order-nse-only",
            "symbol": "ADANIPORTS",
            "exchange": "BSE",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 3,
            "price": 1690.0,
        },
        nonce="breeze-boundary-2",
    )

    response = client.post("/orders", content=body, headers=headers)

    assert response.status_code == 202
    assert response.json()["exchange"] == "NSE"
    assert len(recorder.orders) == 1
    assert recorder.orders[0].exchange == "NSE"
