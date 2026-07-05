from agent.signals.derivatives import compute_derivatives_features


def test_derivatives_features_fail_closed_when_unavailable():
    features = compute_derivatives_features()

    assert features.available is False
    assert features.bias == "neutral"
    assert "derivatives data unavailable" in features.reasons


def test_derivatives_features_infer_bullish_bias_from_low_pcr_and_max_pain():
    features = compute_derivatives_features(
        put_call_ratio=0.55,
        implied_volatility=18,
        max_pain=105,
        spot_price=100,
    )

    assert features.available is True
    assert features.open_interest_bias == "bullish"
    assert features.volatility_bias == "normal"
    assert features.bias == "bullish"
    assert "pcr:0.55" in features.reasons


def test_derivatives_features_identify_high_volatility():
    features = compute_derivatives_features(put_call_ratio=1.5, implied_volatility=40)

    assert features.open_interest_bias == "bearish"
    assert features.volatility_bias == "high"
    assert features.bias == "bearish"
