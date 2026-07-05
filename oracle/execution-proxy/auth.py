"""Signed request authentication for the Oracle execution proxy."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field

from fastapi import HTTPException, Request


CLIENT_ID_HEADER = "x-oracle-client-id"
TIMESTAMP_HEADER = "x-oracle-timestamp"
NONCE_HEADER = "x-oracle-nonce"
SIGNATURE_HEADER = "x-oracle-signature"
DEFAULT_MAX_SKEW_SECONDS = 300


def body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def canonical_payload(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    return "\n".join(
        [
            method.upper(),
            path,
            timestamp,
            nonce,
            body_hash(body),
        ]
    )


def sign_payload(secret: str, payload: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def expected_signature(secret: str, method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    return sign_payload(secret, canonical_payload(method, path, timestamp, nonce, body))


@dataclass
class ReplayStore:
    seen_nonces: dict[str, float] = field(default_factory=dict)

    def purge(self, now: float, max_age_seconds: int) -> None:
        expired = [nonce for nonce, seen_at in self.seen_nonces.items() if now - seen_at > max_age_seconds]
        for nonce in expired:
            self.seen_nonces.pop(nonce, None)

    def mark_once(self, client_id: str, nonce: str, now: float, max_age_seconds: int) -> bool:
        self.purge(now, max_age_seconds)
        replay_key = f"{client_id}:{nonce}"
        if replay_key in self.seen_nonces:
            return False
        self.seen_nonces[replay_key] = now
        return True


async def validate_signed_request(
    request: Request,
    *,
    secret: str,
    replay_store: ReplayStore,
    max_skew_seconds: int = DEFAULT_MAX_SKEW_SECONDS,
) -> None:
    if not secret:
        raise HTTPException(status_code=500, detail="Oracle proxy signing secret is not configured")

    client_id = request.headers.get(CLIENT_ID_HEADER)
    timestamp = request.headers.get(TIMESTAMP_HEADER)
    nonce = request.headers.get(NONCE_HEADER)
    signature = request.headers.get(SIGNATURE_HEADER)

    if not all([client_id, timestamp, nonce, signature]):
        raise HTTPException(status_code=401, detail="missing required signature headers")

    try:
        request_time = int(timestamp)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="invalid signature timestamp") from None

    now = int(time.time())
    if abs(now - request_time) > max_skew_seconds:
        raise HTTPException(status_code=401, detail="expired signature timestamp")

    body = await request.body()
    expected = expected_signature(secret, request.method, request.url.path, timestamp, nonce, body)
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="invalid signature")

    if not replay_store.mark_once(client_id, nonce, float(now), max_skew_seconds):
        raise HTTPException(status_code=409, detail="replayed signature nonce")
