from agent.alpha import IntradayAlphaScanner
from agent.signals.technical import TechnicalFeatures


def test_intraday_alpha_scores_clean_breakout_as_buy():
    features = TechnicalFeatures(
        symbol="MARUTI",
        close=110.0,
        vwap=108.0,
        rsi=62.0,
        macd=1.3,
        macd_signal=0.8,
        atr=1.5,
        relative_volume=2.1,
        opening_range_high=108.5,
        opening_range_low=104.0,
        previous_high=109.0,
        previous_low=106.0,
        trend_bias="bullish",
    )

    setup = IntradayAlphaScanner().score_features(features)

    assert setup.symbol == "MARUTI"
    assert setup.action == "BUY"
    assert setup.conviction >= 70
    assert setup.setup == "opening_range_breakout"
    assert setup.entry_price == 110.0
    assert setup.stop_loss == 108.5
    assert setup.target_price == 112.7
    assert "relative volume spike" in " ".join(setup.reasons)


def test_intraday_alpha_holds_when_market_data_is_unavailable():
    scanner = IntradayAlphaScanner(
        historical_fetcher=lambda *args, **kwargs: {"error": "No historical data available"}
    )

    setup = scanner.analyze_symbol("INFY.N")

    assert setup.symbol == "INFY"
    assert setup.action == "HOLD"
    assert setup.conviction == 0
    assert setup.data_quality == "unavailable"
    assert "market_data_unavailable" in setup.reasons[0]
