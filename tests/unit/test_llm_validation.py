from agent.contracts.signals import SignalAction
from agent.signals.llm_validation import validate_llm_signal


def test_validate_llm_signal_accepts_valid_buy_json():
    signal = validate_llm_signal(
        {
            "action": "BUY",
            "confidence": 80,
            "entry_price": 100,
            "stop_loss": 98,
            "target_price": 104,
            "risk_level": "LOW",
            "sentiment_score": 0.4,
            "reasoning": "validated setup",
        },
        symbol="RELIANCE",
    )

    assert signal.action == SignalAction.BUY
    assert signal.confidence == 80
    assert signal.stop_loss < signal.entry_price < signal.target_price


def test_validate_llm_signal_extracts_json_from_text():
    signal = validate_llm_signal(
        'Recommendation: {"action":"HOLD","confidence":40,"reasoning":"mixed"}',
        symbol="TCS",
    )

    assert signal.action == SignalAction.HOLD
    assert "llm returned HOLD" in signal.reasons[0]


def test_validate_llm_signal_converts_invalid_json_to_hold():
    signal = validate_llm_signal("BUY RELIANCE now", symbol="RELIANCE")

    assert signal.action == SignalAction.HOLD
    assert signal.confidence == 0
    assert "invalid llm signal" in signal.reasons[0]


def test_validate_llm_signal_converts_unsafe_prices_to_hold():
    signal = validate_llm_signal(
        {
            "action": "BUY",
            "confidence": 90,
            "entry_price": 100,
            "stop_loss": 105,
            "target_price": 104,
        },
        symbol="RELIANCE",
    )

    assert signal.action == SignalAction.HOLD
    assert "invalid llm signal" in signal.reasons[0]
