from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

logger = logging.getLogger("trading_bot")


def build_log_event(
    event_type: str,
    *,
    symbol: str | None = None,
    signal_id: str | None = None,
    order_id: str | None = None,
    mode: str | None = None,
    reason: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "symbol": symbol,
        "signal_id": signal_id,
        "order_id": order_id,
        "mode": mode,
        "reason": reason,
    }
    event.update(fields)
    return {key: value for key, value in event.items() if value is not None}


def log_event(event_type: str, **fields: Any) -> dict[str, Any]:
    event = build_log_event(event_type, **fields)
    logger.info(json.dumps(event, sort_keys=True, default=_json_default))
    return event


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
