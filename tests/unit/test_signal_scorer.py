from agent.contracts.signals import SignalAction
from agent.signals.derivatives import compute_derivatives_features
from agent.signals.scorer import score_signal
from agent.signals.sentiment import SentimentFeatures
from agent.signals.technical import TechnicalFeatures


def technical(bias="bullish"):
    return TechnicalFeatures(
        symbol="RELIANCE",
        close=100,
        vwap=99 if bias == "bullish" else 101,
        rsi=60 if bias == "bullish" else 40,
        macd=2 if bias == "bullish" else -2,
        macd_signal=1 if bias == "bullish" else -1,
        atr=2,
        relative_volume=1.5,
        opening_range_high=101,
        opening_range_low=98,
        previous_high=102,
        previous_low=97,
        trend_bias=bias,
    )


def sentiment(score=0.4, bias="bullish"):
    return SentimentFeatures(
        global_score=score,
        indian_market_score=score,
        company_news_score=score,
        announcement_score=score,
        combined_score=score,
        event_count=3,
        bias=bias,
        reasons=[f"combined:{score}"],
    )


def test_signal_scorer_emits_buy_signal_with_prices_and_reasons():
    signal = score_signal(
        symbol="RELIANCE",
        technical=technical("bullish"),
        sentiment=sentiment(0.4, "bullish"),
        derivatives=compute_derivatives_features(put_call_ratio=0.6),
    )

    assert signal.action == SignalAction.BUY
    assert signal.confidence >= 35
    assert signal.entry_price == 100
    assert signal.stop_loss < signal.entry_price < signal.target_price
    assert "technical:bullish" in signal.reasons


def test_signal_scorer_emits_hold_for_mixed_inputs():
    signal = score_signal(
        symbol="RELIANCE",
        technical=technical("neutral"),
        sentiment=sentiment(0.0, "neutral"),
        derivatives=compute_derivatives_features(),
    )

    assert signal.action == SignalAction.HOLD
    assert signal.entry_price is None


def test_signal_scorer_emits_sell_signal_for_bearish_inputs():
    signal = score_signal(
        symbol="RELIANCE",
        technical=technical("bearish"),
        sentiment=sentiment(-0.5, "bearish"),
        derivatives=compute_derivatives_features(put_call_ratio=1.6),
    )

    assert signal.action == SignalAction.SELL
    assert signal.target_price < signal.entry_price < signal.stop_loss
