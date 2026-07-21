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
