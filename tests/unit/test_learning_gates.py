from decimal import Decimal

from agent.learning.gates import LearningGate, apply_threshold_gate


def test_learning_gate_blocks_looser_threshold_with_small_sample_size():
    gate = LearningGate(min_samples_to_loosen=30, min_win_rate_to_loosen=Decimal("55"))

    decision = gate.evaluate_threshold_change(
        current_threshold=70,
        proposed_threshold=65,
        sample_size=12,
        win_rate=Decimal("75"),
    )

    assert decision.allowed is False
    assert decision.reason == "insufficient_sample_size"


def test_learning_gate_blocks_looser_threshold_with_weak_win_rate():
    decision = LearningGate().evaluate_threshold_change(
        current_threshold=70,
        proposed_threshold=65,
        sample_size=60,
        win_rate=Decimal("52"),
    )

    assert decision.allowed is False
    assert decision.reason == "win_rate_too_low"


def test_learning_gate_allows_tightening_without_sample_requirement():
    decision = LearningGate().evaluate_threshold_change(
        current_threshold=70,
        proposed_threshold=80,
        sample_size=0,
        win_rate=Decimal("0"),
    )

    assert decision.allowed is True
    assert decision.reason == "tightening_or_unchanged"


def test_apply_threshold_gate_keeps_current_threshold_when_loosen_is_blocked():
    threshold = apply_threshold_gate(
        current_threshold=70,
        proposed_threshold=65,
        sample_size=5,
        win_rate=Decimal("80"),
    )

    assert threshold == 70
