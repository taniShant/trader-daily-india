from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field


class MarketContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    as_of: str
    macro: dict[str, Any] = Field(default_factory=dict)
    news: list[dict[str, Any]] = Field(default_factory=list)
    sentiment_score: float = 0
    key_headlines: list[str] = Field(default_factory=list)


def default_market_context() -> dict[str, Any]:
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "macro": {},
        "news": [],
        "sentiment_score": 0,
        "key_headlines": [],
    }


def create_app() -> FastAPI:
    app = FastAPI(title="Oracle Market Context Collector", version="0.1.0")
    app.state.market_context = default_market_context()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "oracle-market-context-collector",
            "mode": os.environ.get("ORACLE_COLLECTOR_MODE", "mock"),
            "static_ip": os.environ.get("ORACLE_STATIC_IP", "80.225.242.6"),
        }

    @app.get("/market-context/latest")
    def latest_market_context() -> dict[str, Any]:
        return dict(app.state.market_context)

    @app.post("/market-context/latest")
    def update_market_context(context: MarketContext) -> dict[str, Any]:
        app.state.market_context = context.model_dump(mode="json")
        return {
            "status": "stored",
            "as_of": app.state.market_context["as_of"],
        }

    return app


app = create_app()
