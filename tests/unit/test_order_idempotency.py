import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from agent.execution.oracle_breeze_client import OracleBreezeClient


ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "oracle" / "execution-proxy" / "app.py"
SECRET = "test-signing-secret"


def load_proxy_app(monkeypatch):
    monkeypatch.setenv("ORACLE_PROXY_MODE", "mock")
    monkeypatch.setenv("ORACLE_STATIC_IP", "80.225.242.6")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ORACLE_PROXY_SHARED_SECRET", SECRET)
    monkeypatch.syspath_prepend(str(APP_PATH.parent))

    for module_name in ["oracle_execution_proxy_app_idempotency_test", "auth", "breeze_client", "idempotency"]:
        sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location("oracle_execution_proxy_app_idempotency_test", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["oracle_execution_proxy_app_idempotency_test"] = module
    spec.loader.exec_module(module)
    return module.app


def signed_request(payload, *, nonce):
    client = OracleBreezeClient(
        base_url="http://oracle-proxy.test",
        client_id="aws-trading-bot",
        shared_secret=SECRET,
    )
    return client.sign_json_request("POST", "/orders", payload, nonce=nonce)


def order_payload(**overrides):
    payload = {
        "client_order_id": "same-client-order",
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 1,
        "price": 2500.0,
    }
    payload.update(overrides)
    return payload


class CountingExecutionClient:
    def __init__(self):
        self.calls = 0

    def place_order(self, order):
        self.calls += 1
        return sys.modules["breeze_client"].ExecutionResult(
            success=True,
            status="ACCEPTED",
            client_order_id=order.client_order_id,
            broker_order_id=f"broker-call-{self.calls}",
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


def test_same_client_order_id_and_same_payload_does_not_place_twice(monkeypatch):
    app = load_proxy_app(monkeypatch)
    execution_client = CountingExecutionClient()
    app.state.execution_client = execution_client
    client = TestClient(app)
    payload = order_payload()

    first_body, first_headers = signed_request(payload, nonce="idempotent-1")
    second_body, second_headers = signed_request(payload, nonce="idempotent-2")

    first_response = client.post("/orders", content=first_body, headers=first_headers)
    second_response = client.post("/orders", content=second_body, headers=second_headers)

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert execution_client.calls == 1
    assert first_response.json()["broker_order_id"] == "broker-call-1"
    assert second_response.json()["broker_order_id"] == "broker-call-1"
    assert first_response.json()["idempotent_replay"] is False
    assert second_response.json()["idempotent_replay"] is True


def test_same_client_order_id_with_different_payload_is_rejected(monkeypatch):
    app = load_proxy_app(monkeypatch)
    execution_client = CountingExecutionClient()
    app.state.execution_client = execution_client
    client = TestClient(app)

    first_body, first_headers = signed_request(order_payload(), nonce="conflict-1")
    conflict_body, conflict_headers = signed_request(order_payload(quantity=2), nonce="conflict-2")

    first_response = client.post("/orders", content=first_body, headers=first_headers)
    conflict_response = client.post("/orders", content=conflict_body, headers=conflict_headers)

    assert first_response.status_code == 202
    assert conflict_response.status_code == 409
    assert conflict_response.json()["detail"] == "client_order_id already used for a different order"
    assert execution_client.calls == 1
