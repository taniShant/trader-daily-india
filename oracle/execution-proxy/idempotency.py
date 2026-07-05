"""In-memory idempotency guard for Oracle proxy order submission."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256


class DuplicateOrderError(RuntimeError):
    """Raised when a client order ID is reused for a different order payload."""


@dataclass(frozen=True)
class IdempotencyRecord:
    fingerprint: str
    response: dict[str, object]


@dataclass
class IdempotencyStore:
    records: dict[str, IdempotencyRecord] = field(default_factory=dict)

    def get(self, client_order_id: str, fingerprint: str) -> dict[str, object] | None:
        record = self.records.get(client_order_id)
        if record is None:
            return None
        if record.fingerprint != fingerprint:
            raise DuplicateOrderError("client_order_id already used for a different order")

        replay = dict(record.response)
        replay["idempotent_replay"] = True
        return replay

    def save(self, client_order_id: str, fingerprint: str, response: dict[str, object]) -> dict[str, object]:
        stored_response = dict(response)
        stored_response["idempotent_replay"] = False
        self.records[client_order_id] = IdempotencyRecord(
            fingerprint=fingerprint,
            response=stored_response,
        )
        return dict(stored_response)


def fingerprint_payload(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return sha256(encoded).hexdigest()
