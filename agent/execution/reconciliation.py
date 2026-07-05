from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReconciliationIssue:
    symbol: str
    ledger_quantity: int
    broker_quantity: int
    issue_type: str


def reconcile_positions(
    ledger_positions: dict[str, dict[str, Any]],
    broker_positions: list[dict[str, Any]],
) -> list[ReconciliationIssue]:
    broker_by_symbol = {
        str(item.get("symbol") or item.get("stock_code")).upper(): int(item.get("quantity", 0))
        for item in broker_positions
    }
    all_symbols = set(ledger_positions) | set(broker_by_symbol)
    issues: list[ReconciliationIssue] = []
    for symbol in sorted(all_symbols):
        ledger_quantity = int(ledger_positions.get(symbol, {}).get("quantity", 0))
        broker_quantity = broker_by_symbol.get(symbol, 0)
        if ledger_quantity == broker_quantity:
            continue
        if ledger_quantity == 0:
            issue_type = "missing_in_ledger"
        elif broker_quantity == 0:
            issue_type = "missing_at_broker"
        else:
            issue_type = "quantity_mismatch"
        issues.append(ReconciliationIssue(symbol, ledger_quantity, broker_quantity, issue_type))
    return issues
