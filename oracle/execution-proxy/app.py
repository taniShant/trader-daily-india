#!/usr/bin/env python3
"""Oracle static-IP execution proxy skeleton.

The proxy still runs in mock execution mode, but protected order submission
requires signed requests before any later Breeze integration is added.
"""

from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from enum import StrEnum

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from auth import DEFAULT_MAX_SKEW_SECONDS, ReplayStore, validate_signed_request
from breeze_client import OrderSide, OrderType, ProxyOrder, create_execution_client
from idempotency import DuplicateOrderError, IdempotencyStore, fingerprint_payload


class ProxyMode(StrEnum):
    MOCK = "mock"
    LIVE = "live"


class MockOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_order_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    exchange: str = Field(default="NSE", min_length=1)
    side: OrderSide
    order_type: OrderType
    quantity: int = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    product_type: str = Field(default="intraday", min_length=1)

    @model_validator(mode="after")
    def validate_price(self) -> "MockOrderRequest":
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("limit orders require price")
        return self


def get_settings() -> dict[str, str]:
    return {
        "mode": os.environ.get("ORACLE_PROXY_MODE", ProxyMode.MOCK.value).lower(),
        "static_ip": os.environ.get("ORACLE_STATIC_IP", "80.225.242.6"),
        "environment": os.environ.get("ENVIRONMENT", "prod"),
        "service_name": os.environ.get("ORACLE_PROXY_SERVICE_NAME", "oracle-execution-proxy"),
        "shared_secret": os.environ.get("ORACLE_PROXY_SHARED_SECRET", ""),
        "max_skew_seconds": os.environ.get("ORACLE_PROXY_MAX_SKEW_SECONDS", str(DEFAULT_MAX_SKEW_SECONDS)),
        "icici_api_key": os.environ.get("ICICI_API_KEY", ""),
        "icici_secret_key": os.environ.get("ICICI_SECRET_KEY", ""),
        "icici_session_token": os.environ.get("ICICI_SESSION_TOKEN", ""),
    }


def create_app() -> FastAPI:
    settings = get_settings()
    if settings["mode"] not in {ProxyMode.MOCK.value, ProxyMode.LIVE.value}:
        raise RuntimeError("ORACLE_PROXY_MODE must be mock or live")

    app = FastAPI(
        title="Oracle Breeze Execution Proxy",
        version="0.1.0",
        description="Static-IP execution proxy skeleton for ICICI Breeze live orders.",
    )
    app.state.replay_store = ReplayStore()
    app.state.idempotency_store = IdempotencyStore()
    app.state.execution_client = create_execution_client(settings)

    async def require_signature(request: Request) -> None:
        await validate_signed_request(
            request,
            secret=settings["shared_secret"],
            replay_store=app.state.replay_store,
            max_skew_seconds=int(settings["max_skew_seconds"]),
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": settings["service_name"],
            "mode": settings["mode"],
            "environment": settings["environment"],
            "static_ip": settings["static_ip"],
            "breeze_enabled": "true" if settings["mode"] == ProxyMode.LIVE.value else "false",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/ready")
    def ready() -> dict[str, str]:
        return {
            "status": "ready",
            "mode": settings["mode"],
            "detail": "execution client is configured",
        }

    @app.post("/mock/orders", status_code=202)
    def place_mock_order(order: MockOrderRequest) -> dict[str, object]:
        if settings["mode"] != ProxyMode.MOCK.value:
            raise HTTPException(status_code=409, detail="mock orders are disabled")

        return place_order_once(app, order)

    @app.post("/orders", status_code=202, dependencies=[Depends(require_signature)])
    def place_signed_order(order: MockOrderRequest) -> dict[str, object]:
        return place_order_once(app, order)

    return app


def place_order_once(app: FastAPI, order: MockOrderRequest) -> dict[str, object]:
    payload = order_payload(order)
    fingerprint = fingerprint_payload(payload)

    try:
        replay = app.state.idempotency_store.get(order.client_order_id, fingerprint)
    except DuplicateOrderError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if replay is not None:
        return replay

    response = app.state.execution_client.place_order(to_proxy_order(order)).to_response()
    return app.state.idempotency_store.save(order.client_order_id, fingerprint, response)


def order_payload(order: MockOrderRequest) -> dict[str, object]:
    return json.loads(order.model_dump_json())


def to_proxy_order(order: MockOrderRequest) -> ProxyOrder:
    return ProxyOrder(
        client_order_id=order.client_order_id,
        symbol=order.symbol,
        exchange="NSE",
        side=order.side,
        order_type=order.order_type,
        quantity=order.quantity,
        price=order.price,
        product_type=order.product_type,
    )


app = create_app()
