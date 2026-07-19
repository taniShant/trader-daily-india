from agent.contracts.signals import RiskLevel, SignalAction
from agent.data.quality import SourceQualityResult
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
        macd_signal=1 if bias == "bullish" else -2,
        atr=2,
        relative_volume=1.5,
        opening_range_high=101,
        opening_range_low=98,
        previous_high=102,
        previous_low=97,
        trend_bias=bias,
    )


def sentiment_features(*, source_quality: SourceQualityResult):
    return SentimentFeatures(
        global_score=0.5,
        indian_market_score=0.5,
        company_news_score=0.5,
        announcement_score=0.5,
        combined_score=0.5,
        event_count=5,
        bias="bullish",
        reasons=["all_sources_bullish"],
        source_quality_score=source_quality.score,
        source_quality_reasons=source_quality.reasons,
        live_trade_blocked=source_quality.live_trade_blocked,
    )


def test_signal_scorer_blocks_trade_when_source_quality_blocks_live_trade():
    source_quality = SourceQualityResult(
        passed=False,
        score=0.5,
        reasons=["global_news unavailable", "missing official announcements"],
        source_count=2,
        unavailable_count=2,
        live_trade_blocked=True,
    )

    signal = score_signal(
        symbol="RELIANCE",
        technical=technical("bullish"),
        sentiment=sentiment_features(source_quality=source_quality),
    )

    assert signal.action == SignalAction.HOLD
    assert signal.confidence == 0
    assert signal.risk_level == RiskLevel.HIGH
    assert "source_quality_block" in signal.reasons
    assert "global_news unavailable" in signal.reasons
    assert signal.raw_features["source_quality"]["live_trade_blocked"] is True


def test_signal_scorer_reduces_confidence_when_source_quality_is_degraded_but_not_blocked():
    full_quality_signal = score_signal(
        symbol="RELIANCE",
        technical=technical("bullish"),
        sentiment=sentiment_features(
            source_quality=SourceQualityResult(passed=True, score=1.0, reasons=[], source_count=5)
        ),
    )
    degraded_signal = score_signal(
        symbol="RELIANCE",
        technical=technical("bullish"),
        sentiment=sentiment_features(
            source_quality=SourceQualityResult(
                passed=True,
                score=0.8,
                reasons=["company_news stale"],
                source_count=5,
                stale_count=1,
                live_trade_blocked=False,
            )
        ),
    )

    assert full_quality_signal.action == SignalAction.BUY
    assert degraded_signal.action == SignalAction.BUY
    assert degraded_signal.confidence < full_quality_signal.confidence
    assert degraded_signal.raw_features["source_quality"]["score"] == 0.8
