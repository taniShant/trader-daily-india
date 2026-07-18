from __future__ import annotations

from decimal import Decimal
from typing import Any


def decimalize(value: Any) -> Any:
    """Convert Python floats into DynamoDB-safe Decimals recursively."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [decimalize(item) for item in value]
    if isinstance(value, dict):
        return {key: decimalize(item) for key, item in value.items()}
    return value


def daily_state_key(date: str, record_type: str) -> dict[str, str]:
    return {"date": date, "timestamp": f"state#{record_type}"}


def get_daily_state(table, date: str, record_type: str) -> dict[str, Any]:
    response = table.get_item(Key=daily_state_key(date, record_type))
    return response.get("Item", {})


def put_daily_state(table, date: str, record_type: str, item: dict[str, Any]) -> None:
    item = {
        **item,
        "date": date,
        "timestamp": f"state#{record_type}",
        "record_type": record_type,
    }
    table.put_item(Item=decimalize(item))
