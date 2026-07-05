from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DerivativesFeatures:
    available: bool
    put_call_ratio: float | None
    open_interest_bias: str
    implied_volatility: float | None
    volatility_bias: str
    max_pain: float | None
    bias: str
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def compute_derivatives_features(
    *,
    put_call_ratio: float | None = None,
    put_call_open_interest_ratio: float | None = None,
    implied_volatility: float | None = None,
    max_pain: float | None = None,
    spot_price: float | None = None,
) -> DerivativesFeatures:
    if put_call_ratio is None and put_call_open_interest_ratio is None and implied_volatility is None:
        return DerivativesFeatures(
            available=False,
            put_call_ratio=None,
            open_interest_bias="neutral",
            implied_volatility=None,
            volatility_bias="unknown",
            max_pain=max_pain,
            bias="neutral",
            reasons=["derivatives data unavailable"],
        )

    pcr = put_call_ratio if put_call_ratio is not None else put_call_open_interest_ratio
    oi_bias = _pcr_bias(pcr)
    vol_bias = _volatility_bias(implied_volatility)
    pain_bias = _max_pain_bias(max_pain, spot_price)
    bias = _combine_bias([oi_bias, pain_bias])
    reasons = [f"pcr:{pcr:.2f}"] if pcr is not None else []
    if implied_volatility is not None:
        reasons.append(f"iv:{implied_volatility:.2f}")
    if max_pain is not None and spot_price is not None:
        reasons.append(f"max_pain_distance:{max_pain - spot_price:.2f}")

    return DerivativesFeatures(
        available=True,
        put_call_ratio=pcr,
        open_interest_bias=oi_bias,
        implied_volatility=implied_volatility,
        volatility_bias=vol_bias,
        max_pain=max_pain,
        bias=bias,
        reasons=reasons,
    )


def _pcr_bias(value: float | None) -> str:
    if value is None:
        return "neutral"
    if value < 0.7:
        return "bullish"
    if value > 1.3:
        return "bearish"
    return "neutral"


def _volatility_bias(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value > 35:
        return "high"
    if value < 12:
        return "low"
    return "normal"


def _max_pain_bias(max_pain: float | None, spot_price: float | None) -> str:
    if max_pain is None or spot_price is None or spot_price <= 0:
        return "neutral"
    distance = (max_pain - spot_price) / spot_price
    if distance > 0.02:
        return "bullish"
    if distance < -0.02:
        return "bearish"
    return "neutral"


def _combine_bias(values: list[str]) -> str:
    bullish = values.count("bullish")
    bearish = values.count("bearish")
    if bullish > bearish:
        return "bullish"
    if bearish > bullish:
        return "bearish"
    return "neutral"
