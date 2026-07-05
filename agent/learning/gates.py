from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class LearningGateDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class LearningGate:
    min_samples_to_loosen: int = 30
    min_win_rate_to_loosen: Decimal = Decimal("55")

    def evaluate_threshold_change(
        self,
        *,
        current_threshold: int,
        proposed_threshold: int,
        sample_size: int,
        win_rate: Decimal,
    ) -> LearningGateDecision:
        if proposed_threshold >= current_threshold:
            return LearningGateDecision(True, "tightening_or_unchanged")
        if sample_size < self.min_samples_to_loosen:
            return LearningGateDecision(False, "insufficient_sample_size")
        if win_rate < self.min_win_rate_to_loosen:
            return LearningGateDecision(False, "win_rate_too_low")
        return LearningGateDecision(True, "enough_evidence_to_loosen")


def apply_threshold_gate(
    *,
    current_threshold: int,
    proposed_threshold: int,
    sample_size: int,
    win_rate: Decimal,
    gate: LearningGate | None = None,
) -> int:
    gate = gate or LearningGate()
    decision = gate.evaluate_threshold_change(
        current_threshold=current_threshold,
        proposed_threshold=proposed_threshold,
        sample_size=sample_size,
        win_rate=win_rate,
    )
    return proposed_threshold if decision.allowed else current_threshold
