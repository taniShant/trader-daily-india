"""AWS-side client for the Oracle static-IP execution proxy."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import requests

from agent.contracts.execution import OrderRequest, OrderStatus
from agent.data.symbols import breeze_stock_code


class OracleProxyError(RuntimeError):
    """Raised when the Oracle execution proxy rejects or fails a request."""


@dataclass(frozen=True)
class OracleBreezeClient:
    base_url: str
    client_id: str
    shared_secret: str
    timeout_seconds: float = 10.0

    def _headers(self, method: str, path: str, body: bytes, *, timestamp: int | None = None, nonce: str | None = None) -> dict[str, str]:
        ts = str(timestamp or int(time.time()))
        request_nonce = nonce or uuid4().hex
        body_digest = hashlib.sha256(body).hexdigest()
        canonical = "\n".join([method.upper(), path, ts, request_nonce, body_digest])
        signature = hmac.new(
            self.shared_secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-Oracle-Client-Id": self.client_id,
            "X-Oracle-Timestamp": ts,
            "X-Oracle-Nonce": request_nonce,
            "X-Oracle-Signature": signature,
        }

    def sign_json_request(
        self,
        method: str,
        path: str,
        payload: dict[str, object],
        *,
        timestamp: int | None = None,
        nonce: str | None = None,
    ) -> tuple[bytes, dict[str, str]]:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=_json_default).encode("utf-8")
        return body, self._headers(method, path, body, timestamp=timestamp, nonce=nonce)

    def place_order(self, order: OrderRequest) -> OrderStatus:
        path = "/orders"
        payload = _order_to_proxy_payload(order)
        body, headers = self.sign_json_request("POST", path, payload)
        response = requests.post(
            f"{self.base_url.rstrip('/')}{path}",
            data=body,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 400:
            raise OracleProxyError(f"Oracle proxy rejected order: {response.status_code} {response.text}")

        status = response.json().get("status")
        return OrderStatus(status)


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _order_to_proxy_payload(order: OrderRequest) -> dict[str, object]:
    payload: dict[str, object] = {
        "client_order_id": order.client_order_id,
        "symbol": breeze_stock_code(order.symbol),
        "exchange": order.exchange,
        "side": order.side.value,
        "order_type": order.order_type.value,
        "quantity": order.quantity,
        "product_type": order.product_type,
    }
    if order.price is not None:
        payload["price"] = order.price
    return payload
