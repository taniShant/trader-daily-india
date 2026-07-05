from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import requests


class OracleCollectorError(RuntimeError):
    """Raised when the Oracle collector cannot provide cached market context."""


@dataclass(frozen=True)
class OracleCollectorClient:
    base_url: str
    timeout_seconds: float = 10.0

    def fetch_market_context(self) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url.rstrip('/')}/market-context/latest",
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 400:
            raise OracleCollectorError(f"Oracle collector returned {response.status_code}: {response.text}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise OracleCollectorError("Oracle collector returned non-object payload")
        return _normalize_context(payload, source="oracle")


def get_market_context_with_fallback(
    client: OracleCollectorClient,
    fallback: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    try:
        return client.fetch_market_context()
    except Exception as exc:
        fallback_payload = fallback()
        fallback_payload = dict(fallback_payload)
        fallback_payload.setdefault("source", "fallback")
        fallback_payload["oracle_error"] = str(exc)
        return fallback_payload


def _normalize_context(payload: dict[str, Any], *, source: str) -> dict[str, Any]:
    return {
        "source": source,
        "as_of": payload.get("as_of") or payload.get("timestamp"),
        "macro": payload.get("macro", {}),
        "news": payload.get("news", []),
        "sentiment_score": payload.get("sentiment_score", 0),
        "key_headlines": payload.get("key_headlines", []),
    }
