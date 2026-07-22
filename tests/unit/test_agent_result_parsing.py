from types import SimpleNamespace

import agent.main as main_module


def test_parse_recommendation_payload_from_strands_message_dict():
    result = SimpleNamespace(
        message={
            "role": "assistant",
            "content": [
                {
                    "text": """
                    Final recommendation:
                    ```json
                    {
                      "action": "BUY",
                      "confidence": 74,
                      "entry_price": 100.5,
                      "stop_loss": 98.0,
                      "target_price": 106.0,
                      "reasoning": "Momentum and sentiment agree.",
                      "technical_summary": "Breakout above VWAP.",
                      "sentiment_score": 0.4,
                      "risk_level": "MEDIUM"
                    }
                    ```
                    """
                }
            ],
        }
    )

    payload = main_module._parse_recommendation_payload(result)

    assert payload["action"] == "BUY"
    assert payload["confidence"] == 74
    assert payload["entry_price"] == 100.5


def test_analyze_stock_accepts_agent_result_object(monkeypatch):
    result = SimpleNamespace(
        message={
            "role": "assistant",
            "content": [
                {
                    "text": """
                    {
                      "action": "HOLD",
                      "confidence": 65,
                      "entry_price": 0,
                      "stop_loss": 0,
                      "target_price": 0,
                      "reasoning": "Insufficient technical data.",
                      "technical_summary": "Data unavailable.",
                      "sentiment_score": 0,
                      "risk_level": "HIGH"
                    }
                    """
                }
            ],
        }
    )

    monkeypatch.setattr(main_module, "get_orchestrator", lambda: lambda prompt: result)

    bot = main_module.TradingBot.__new__(main_module.TradingBot)
    bot.current_sentiment = 0.0
    bot.temp_caution_mode = False
    bot.confidence_adjuster = SimpleNamespace(get_adjustment_factor=lambda: 1.0)

    signal = bot._analyze_stock("MARUTI")

    assert signal is not None
    assert signal.stock_symbol == "MARUTI"
    assert signal.action == "HOLD"
    assert signal.confidence == 65
    assert signal.risk_level == "HIGH"


def test_analyze_stock_downgrades_directional_signal_with_missing_prices(monkeypatch):
    result = SimpleNamespace(
        message={
            "role": "assistant",
            "content": [
                {
                    "text": """
                    {
                      "action": "BUY",
                      "confidence": 82,
                      "entry_price": null,
                      "stop_loss": null,
                      "target_price": null,
                      "reasoning": "Fundamental catalyst is strong.",
                      "technical_summary": "Missing live price.",
                      "sentiment_score": 0.3,
                      "risk_level": "MEDIUM"
                    }
                    """
                }
            ],
        }
    )

    monkeypatch.setattr(main_module, "get_orchestrator", lambda: lambda prompt: result)

    bot = main_module.TradingBot.__new__(main_module.TradingBot)
    bot.current_sentiment = 0.0
    bot.temp_caution_mode = False
    bot.confidence_adjuster = SimpleNamespace(get_adjustment_factor=lambda: 1.0)

    signal = bot._analyze_stock("JSWSTEEL")

    assert signal is not None
    assert signal.action == "HOLD"
    assert signal.confidence == 50
    assert signal.entry_price == 0.0
    assert signal.stop_loss == 0.0
    assert signal.target_price == 0.0
    assert signal.risk_level == "HIGH"
    assert "downgraded to HOLD" in signal.reasoning


def test_analyze_stock_refreshes_bedrock_runtime_after_expired_token(monkeypatch):
    result = SimpleNamespace(
        message={
            "role": "assistant",
            "content": [
                {
                    "text": """
                    {
                      "action": "HOLD",
                      "confidence": 62,
                      "entry_price": 0,
                      "stop_loss": 0,
                      "target_price": 0,
                      "reasoning": "Recovered after credential refresh.",
                      "technical_summary": "No clear intraday setup.",
                      "sentiment_score": 0,
                      "risk_level": "MEDIUM"
                    }
                    """
                }
            ],
        }
    )
    calls = []
    refresh_reasons = []

    def fake_orchestrator(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            raise Exception(
                "An error occurred (ExpiredTokenException) when calling the "
                "ConverseStream operation: The security token included in the request is expired"
            )
        return result

    monkeypatch.setattr(main_module, "get_orchestrator", lambda: fake_orchestrator)
    monkeypatch.setattr(main_module, "refresh_bedrock_runtime", lambda reason: refresh_reasons.append(reason))

    bot = main_module.TradingBot.__new__(main_module.TradingBot)
    bot.current_sentiment = 0.0
    bot.temp_caution_mode = False
    bot.confidence_adjuster = SimpleNamespace(get_adjustment_factor=lambda: 1.0)

    signal = bot._analyze_stock("MARUTI")

    assert signal is not None
    assert signal.stock_symbol == "MARUTI"
    assert signal.action == "HOLD"
    assert len(calls) == 2
    assert refresh_reasons == ["expired_token"]
