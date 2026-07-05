from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from agent.contracts.signals import RiskLevel, SignalAction, TradeSignal


def validate_llm_signal(raw_output: str | dict[str, Any], *, symbol: str) -> TradeSignal:
    try:
        payload = _extract_payload(raw_output)
        action = SignalAction(str(payload.get("action", "HOLD")).upper())
        if action == SignalAction.HOLD:
            return _hold(symbol, "llm returned HOLD", payload)

        entry = _decimal(payload.get("entry_price"))
        stop = _decimal(payload.get("stop_loss"))
        target = _decimal(payload.get("target_price"))
        confidence = int(payload.get("confidence", 0))
        risk_level = RiskLevel(str(payload.get("risk_level", "MEDIUM")).upper())
        return TradeSignal(
            signal_id=f"llm-{symbol}-{datetime.now(timezone.utc).isoformat()}",
            symbol=symbol,
            action=action,
            confidence=confidence,
            generated_at=datetime.now(timezone.utc),
            entry_price=entry,
            stop_loss=stop,
            target_price=target,
            holding_window_minutes=int(payload.get("holding_window_minutes", 30)),
            risk_level=risk_level,
            sentiment_score=float(payload.get("sentiment_score", 0)),
            reasons=[str(payload.get("reasoning") or "llm validated")],
            raw_features={"llm_payload": payload},
        )
    except (ValueError, TypeError, KeyError, ValidationError) as exc:
        return _hold(symbol, f"invalid llm signal: {exc}", raw_output)


def _extract_payload(raw_output: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_output, dict):
        return raw_output
    match = re.search(r"\{.*\}", raw_output, flags=re.DOTALL)
    if not match:
        raise ValueError("no JSON object found")
    payload = json.loads(match.group())
    if not isinstance(payload, dict):
        raise ValueError("JSON payload is not an object")
    return payload


def _decimal(value: Any) -> Decimal:
    if value is None:
        raise ValueError("missing price")
    return Decimal(str(value))


def _hold(symbol: str, reason: str, raw: Any) -> TradeSignal:
    return TradeSignal(
        signal_id=f"hold-{symbol}-{datetime.now(timezone.utc).isoformat()}",
        symbol=symbol,
        action=SignalAction.HOLD,
        confidence=0,
        generated_at=datetime.now(timezone.utc),
        risk_level=RiskLevel.HIGH,
        reasons=[reason],
        raw_features={"raw_llm_output": raw},
    )
