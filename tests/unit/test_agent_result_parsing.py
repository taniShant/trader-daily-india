from types import SimpleNamespace

import agent.main as main_module
from agent.risk import RiskLimits, RiskManager
from decimal import Decimal


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


def test_analyze_stock_includes_alpha_context_in_prompt(monkeypatch):
    prompts = []
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
                      "reasoning": "Alpha scanner says no confirmed setup.",
                      "technical_summary": "No breakout.",
                      "sentiment_score": 0,
                      "risk_level": "HIGH"
                    }
                    """
                }
            ],
        }
    )

    def fake_orchestrator(prompt):
        prompts.append(prompt)
        return result

    monkeypatch.setattr(main_module, "get_orchestrator", lambda: fake_orchestrator)

    bot = main_module.TradingBot.__new__(main_module.TradingBot)
    bot.current_sentiment = 0.0
    bot.temp_caution_mode = False
    bot.confidence_adjuster = SimpleNamespace(get_adjustment_factor=lambda: 1.0)
    bot.alpha_scanner = SimpleNamespace(
        analyze_symbol=lambda symbol: SimpleNamespace(
            to_dict=lambda: {
                "symbol": symbol,
                "action": "BUY",
                "conviction": 82,
                "setup": "opening_range_breakout",
                "data_quality": "ok",
                "entry_price": 100.0,
                "stop_loss": 98.0,
                "target_price": 104.0,
                "reasons": ["price broke opening range"],
            }
        )
    )

    signal = bot._analyze_stock("MARUTI")

    assert signal is not None
    assert "Deterministic alpha scanner context" in prompts[0]
    assert "opening_range_breakout" in prompts[0]


def test_alpha_shortlist_selects_best_setups_before_deep_analysis():
    bot = main_module.TradingBot.__new__(main_module.TradingBot)
    bot.watchlist = ["AAA", "BBB"]
    bot.alpha_universe_size = 4
    bot.deep_analysis_size = 2
    bot.alpha_scan_workers = 2
    bot._alpha_context_cache = {}
    bot.pre_market_scanner = SimpleNamespace(
        get_nifty_stocks=lambda: ["AAA", "BBB", "CCC", "MARUTI"],
        _filter_excluded_symbols=lambda symbols: symbols,
        required_symbols=[],
    )

    contexts = {
        "AAA": {"symbol": "AAA", "action": "HOLD", "conviction": 20, "setup": "monitor", "data_quality": "ok"},
        "BBB": {"symbol": "BBB", "action": "BUY", "conviction": 82, "setup": "breakout", "data_quality": "ok"},
        "CCC": {"symbol": "CCC", "action": "SELL", "conviction": 76, "setup": "breakdown", "data_quality": "ok"},
        "MARUTI": {
            "symbol": "MARUTI",
            "action": "HOLD",
            "conviction": 0,
            "setup": "market_data_unavailable",
            "data_quality": "unavailable",
        },
    }
    bot.alpha_scanner = SimpleNamespace(
        analyze_symbol=lambda symbol: SimpleNamespace(to_dict=lambda: contexts[symbol])
    )

    selected = bot._select_deep_analysis_symbols()

    assert selected == ["BBB", "CCC"]
    assert bot._alpha_context_cache["BBB"]["setup"] == "breakout"
    assert bot._alpha_context_cache["CCC"]["setup"] == "breakdown"


def test_alpha_shortlist_keeps_required_symbol_when_available():
    bot = main_module.TradingBot.__new__(main_module.TradingBot)
    bot.watchlist = ["AAA", "BBB"]
    bot.alpha_universe_size = 4
    bot.deep_analysis_size = 2
    bot.alpha_scan_workers = 2
    bot._alpha_context_cache = {}
    bot.pre_market_scanner = SimpleNamespace(
        get_nifty_stocks=lambda: ["AAA", "BBB", "CCC", "MARUTI"],
        _filter_excluded_symbols=lambda symbols: symbols,
        required_symbols=["MARUTI"],
    )

    contexts = {
        "AAA": {"symbol": "AAA", "action": "HOLD", "conviction": 20, "setup": "monitor", "data_quality": "ok"},
        "BBB": {"symbol": "BBB", "action": "BUY", "conviction": 82, "setup": "breakout", "data_quality": "ok"},
        "CCC": {"symbol": "CCC", "action": "SELL", "conviction": 76, "setup": "breakdown", "data_quality": "ok"},
        "MARUTI": {"symbol": "MARUTI", "action": "HOLD", "conviction": 55, "setup": "watch", "data_quality": "ok"},
    }
    bot.alpha_scanner = SimpleNamespace(
        analyze_symbol=lambda symbol: SimpleNamespace(to_dict=lambda: contexts[symbol])
    )

    selected = bot._select_deep_analysis_symbols()

    assert "MARUTI" in selected
    assert len(selected) == 2


def test_get_alpha_context_uses_cached_shortlist_context():
    bot = main_module.TradingBot.__new__(main_module.TradingBot)
    bot._alpha_context_cache = {
        "MARUTI": {
            "symbol": "MARUTI",
            "action": "BUY",
            "conviction": 81,
            "setup": "cached_breakout",
            "data_quality": "ok",
        }
    }
    bot.alpha_scanner = SimpleNamespace(
        analyze_symbol=lambda symbol: (_ for _ in ()).throw(AssertionError("scanner should not be called"))
    )

    context = bot._get_alpha_context("MARUTI")

    assert context["setup"] == "cached_breakout"


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


def test_analyze_stock_downgrades_directional_signal_with_na_prices(monkeypatch):
    result = SimpleNamespace(
        message={
            "role": "assistant",
            "content": [
                {
                    "text": """
                    {
                      "action": "BUY",
                      "confidence": 75,
                      "entry_price": "N/A",
                      "stop_loss": "N/A",
                      "target_price": "N/A",
                      "reasoning": "Fundamentals are strong but price data is unavailable.",
                      "technical_summary": "Technical data unavailable.",
                      "sentiment_score": 0,
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

    signal = bot._analyze_stock("HEROMOTOCO")

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


def test_adjust_confidence_treats_missing_current_sentiment_as_neutral():
    bot = main_module.TradingBot.__new__(main_module.TradingBot)
    bot.current_sentiment = None
    bot.temp_caution_mode = False
    bot.confidence_adjuster = SimpleNamespace(get_adjustment_factor=lambda: 1.0)

    assert bot._adjust_confidence(70) == 70


def test_execute_signal_skips_hold_before_contract_validation(monkeypatch):
    events = []
    bot = main_module.TradingBot.__new__(main_module.TradingBot)
    bot.paper_trading = True

    def fail_contract_conversion(signal):
        raise AssertionError("HOLD should not be converted to execution contract")

    monkeypatch.setattr(main_module, "log_event", lambda event_name, **kwargs: events.append((event_name, kwargs)))
    bot._to_contract_signal = fail_contract_conversion

    signal = main_module.TradingSignal(
        date="2026-07-23",
        stock_symbol="RELIANCE",
        action="HOLD",
        confidence=65,
        entry_price=0.0,
        stop_loss=0.0,
        target_price=0.0,
        reasoning="No actionable intraday setup.",
        technical_summary="Missing technical data.",
        sentiment_score=0.0,
        risk_level="MEDIUM",
    )

    bot._execute_signal(signal)

    assert events[0][0] == "signal_hold"
    assert events[0][1]["symbol"] == "RELIANCE"


def test_record_signal_audit_persists_hold_without_trade_prices():
    signals = []
    bot = main_module.TradingBot.__new__(main_module.TradingBot)
    bot.paper_trading = True
    bot.current_session_id = "session-1"
    bot._audit_repositories = SimpleNamespace(
        signals=SimpleNamespace(put_signal=lambda signal, session_id=None: signals.append((signal, session_id)))
    )

    signal = main_module.TradingSignal(
        date="2026-07-30",
        stock_symbol="RELIANCE",
        action="HOLD",
        confidence=65,
        entry_price=0.0,
        stop_loss=0.0,
        target_price=0.0,
        reasoning="No confirmed breakout.",
        technical_summary="Mixed setup.",
        sentiment_score=0.0,
        risk_level="MEDIUM",
        signal_id="sig-hold-1",
    )

    contract_signal = bot._record_signal_audit(signal)

    assert contract_signal.signal_id == "sig-hold-1"
    assert contract_signal.entry_price is None
    assert signals[0][1] == "session-1"


def test_execute_signal_records_rejected_risk_decision(monkeypatch):
    risk_events = []
    events = []
    bot = main_module.TradingBot.__new__(main_module.TradingBot)
    bot.paper_trading = True
    bot.daily_pnl = 0.0
    bot.consecutive_losses = 0
    bot.min_confidence = 80
    bot.risk_manager = RiskManager(
        RiskLimits(
            capital=Decimal("100000"),
            max_daily_loss_percent=Decimal("4"),
            max_position_size_percent=Decimal("10"),
            min_confidence=80,
        )
    )
    bot._is_new_trade_allowed = lambda: True
    bot._audit_repositories = SimpleNamespace(
        risk_events=SimpleNamespace(put_decision=lambda decision: risk_events.append(decision))
    )

    monkeypatch.setattr(main_module, "log_event", lambda event_name, **kwargs: events.append((event_name, kwargs)))

    signal = main_module.TradingSignal(
        date="2026-07-30",
        stock_symbol="INFY",
        action="SELL",
        confidence=52,
        entry_price=1185.0,
        stop_loss=1195.0,
        target_price=1166.0,
        reasoning="Overbought pullback.",
        technical_summary="RSI stretched.",
        sentiment_score=0.0,
        risk_level="MEDIUM",
        signal_id="sig-sell-1",
    )

    bot._execute_signal(signal)

    assert risk_events[0].signal_id == "sig-sell-1"
    assert risk_events[0].status == main_module.RiskDecisionStatus.REJECTED
    assert "confidence 52% below minimum 80%" in risk_events[0].reasons
    assert events[0][0] == "risk_rejected"
