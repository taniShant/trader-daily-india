import importlib.util
import sys
import time
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
    monkeypatch.setenv("ORACLE_PROXY_MAX_SKEW_SECONDS", "300")
    monkeypatch.syspath_prepend(str(APP_PATH.parent))

    for module_name in ["oracle_execution_proxy_app_auth_test", "auth"]:
        sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location("oracle_execution_proxy_app_auth_test", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["oracle_execution_proxy_app_auth_test"] = module
    spec.loader.exec_module(module)
    return module.app


def signed_request(payload, *, timestamp=None, nonce="nonce-1", secret=SECRET):
    client = OracleBreezeClient(
        base_url="http://oracle-proxy.test",
        client_id="aws-trading-bot",
        shared_secret=secret,
    )
    return client.sign_json_request("POST", "/orders", payload, timestamp=timestamp, nonce=nonce)


def valid_payload():
    return {
        "client_order_id": "order-1",
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 1,
        "price": 2500.0,
    }


def test_signed_order_is_accepted_in_mock_mode(monkeypatch):
    client = TestClient(load_proxy_app(monkeypatch))
    body, headers = signed_request(valid_payload(), nonce="valid-1")

    response = client.post("/orders", content=body, headers=headers)

    assert response.status_code == 202
    assert response.json()["status"] == "ACCEPTED"
    assert response.json()["broker_order_id"].startswith("mock-")


def test_unsigned_order_is_rejected(monkeypatch):
    client = TestClient(load_proxy_app(monkeypatch))

    response = client.post("/orders", json=valid_payload())

    assert response.status_code == 401
    assert "signature" in response.json()["detail"]


def test_expired_signed_order_is_rejected(monkeypatch):
    client = TestClient(load_proxy_app(monkeypatch))
    old_timestamp = int(time.time()) - 1000
    body, headers = signed_request(valid_payload(), timestamp=old_timestamp, nonce="expired-1")

    response = client.post("/orders", content=body, headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "expired signature timestamp"


def test_bad_signature_is_rejected(monkeypatch):
    client = TestClient(load_proxy_app(monkeypatch))
    body, headers = signed_request(valid_payload(), nonce="bad-signature-1")
    headers["X-Oracle-Signature"] = "bad"

    response = client.post("/orders", content=body, headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid signature"


def test_replayed_nonce_is_rejected(monkeypatch):
    client = TestClient(load_proxy_app(monkeypatch))
    body, headers = signed_request(valid_payload(), nonce="replay-1")

    first_response = client.post("/orders", content=body, headers=headers)
    second_response = client.post("/orders", content=body, headers=headers)

    assert first_response.status_code == 202
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "replayed signature nonce"
