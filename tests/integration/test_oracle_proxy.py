import importlib.util
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from agent.contracts.execution import OrderRequest, OrderSide, OrderStatus, OrderType
from agent.execution.oracle_breeze_client import OracleBreezeClient


ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "oracle" / "execution-proxy" / "app.py"
SECRET = "integration-signing-secret"


def load_proxy_app(monkeypatch):
    monkeypatch.setenv("ORACLE_PROXY_MODE", "mock")
    monkeypatch.setenv("ORACLE_STATIC_IP", "80.225.242.6")
    monkeypatch.setenv("ENVIRONMENT", "integration")
    monkeypatch.setenv("ORACLE_PROXY_SHARED_SECRET", SECRET)
    monkeypatch.syspath_prepend(str(APP_PATH.parent))

    for module_name in ["oracle_execution_proxy_app_integration_test", "auth", "breeze_client", "idempotency"]:
        sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location("oracle_execution_proxy_app_integration_test", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["oracle_execution_proxy_app_integration_test"] = module
    spec.loader.exec_module(module)
    return module.app


class RequestsResponse:
    def __init__(self, response):
        self._response = response
        self.status_code = response.status_code
        self.text = response.text

    def json(self):
        return self._response.json()


def test_aws_oracle_client_places_signed_mock_order_through_proxy(monkeypatch):
    app = load_proxy_app(monkeypatch)
    proxy_client = TestClient(app)

    def fake_post(url, data, headers, timeout):
        assert url == "http://oracle-proxy.test/orders"
        assert timeout == 10.0
        return RequestsResponse(proxy_client.post("/orders", content=data, headers=headers))

    monkeypatch.setattr("agent.execution.oracle_breeze_client.requests.post", fake_post)

    aws_client = OracleBreezeClient(
        base_url="http://oracle-proxy.test",
        client_id="aws-trading-bot",
        shared_secret=SECRET,
    )
    order = OrderRequest(
        client_order_id="integration-order-1",
        signal_id="signal-1",
        risk_decision_id="risk-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=1,
        price=Decimal("2500.00"),
        requested_at=datetime.now(timezone.utc),
    )

    status = aws_client.place_order(order)

    assert status == OrderStatus.ACCEPTED
