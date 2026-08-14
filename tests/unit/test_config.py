import pytest

from agent.config import load_settings


def test_loads_prod_json_oracle_values_without_env_overrides(monkeypatch):
    monkeypatch.delenv("ORACLE_STATIC_IP", raising=False)
    monkeypatch.delenv("ORACLE_EXECUTION_PROXY_BASE_URL", raising=False)
    monkeypatch.delenv("PAPER_TRADING", raising=False)

    settings = load_settings("prod", include_env=False)

    assert settings.environment == "prod"
    assert settings.aws.region == "eu-west-2"
    assert settings.oracle.static_ip == "80.225.242.6"
    assert settings.oracle.execution_proxy_base_url == "http://80.225.242.6:8080"
    assert settings.oracle.collector_base_url == "http://80.225.242.6:8090"
    assert settings.trading.paper_trading is True
    assert settings.trading.capital == 10000000
    assert settings.trading.max_quantity_per_order == 5000
    assert settings.trading.market_closed_poll_seconds == 60
    assert settings.trading.micro_exit_check_interval_seconds == 30
    assert settings.trading.micro_min_relative_volume == 1.2
    assert settings.trading.micro_min_continuation_relative_volume == 1.6
    assert settings.trading.micro_max_candle_age_seconds == 180
    assert settings.trading.micro_reentry_cooldown_seconds == 300
    assert settings.trading.micro_continuation_target_pct == 0.003
    assert settings.trading.micro_continuation_max_hold_minutes == 6
    assert settings.trading.micro_opening_range_target_pct == 0.005
    assert settings.trading.micro_early_exit_enabled is True
    assert settings.trading.micro_invalidation_min_hold_seconds == 120
    assert settings.trading.micro_loss_throttle_count == 2
    assert settings.trading.micro_loss_throttle_window_minutes == 30
    assert settings.trading.micro_cost_slippage_bps == 5
    assert settings.trading.micro_min_expected_net_profit == 1000
    assert settings.trading.micro_min_target_to_cost_ratio == 1.8
    assert settings.trading.position_reconciliation_enabled is True
    assert settings.trading.run_startup_overnight_analysis is False
    assert settings.market_symbols.exchange == "NSE"
    assert settings.market_symbols.symbols["RELIANCE"].breeze == "RELIND"
    assert settings.market_symbols.symbols["MARUTI"].yahoo == "MARUTI.NS"


def test_environment_overrides_take_precedence(monkeypatch):
    monkeypatch.setenv("ORACLE_STATIC_IP", "1.2.3.4")
    monkeypatch.setenv("ORACLE_EXECUTION_PROXY_BASE_URL", "https://oracle.example.com")
    monkeypatch.setenv("ORACLE_COLLECTOR_BASE_URL", "https://collector.example.com")
    monkeypatch.setenv("BEDROCK_FAST_MODEL_ID", "fast-model")
    monkeypatch.setenv("BEDROCK_REASONING_MODEL_ID", "reasoning-model")
    monkeypatch.setenv("BEDROCK_DEEP_RESEARCH_MODEL_ID", "deep-model")
    monkeypatch.setenv("PAPER_TRADING", "false")
    monkeypatch.setenv("CAPITAL", "250000")
    monkeypatch.setenv("MAX_QUANTITY_PER_ORDER", "250")
    monkeypatch.setenv("MARKET_CLOSED_POLL_SECONDS", "45")
    monkeypatch.setenv("MICRO_EXIT_CHECK_INTERVAL_SECONDS", "20")
    monkeypatch.setenv("MICRO_MIN_CONTINUATION_RELATIVE_VOLUME", "1.7")
    monkeypatch.setenv("MICRO_MAX_CANDLE_AGE_SECONDS", "240")
    monkeypatch.setenv("MICRO_REENTRY_COOLDOWN_SECONDS", "180")
    monkeypatch.setenv("MICRO_CONTINUATION_TARGET_PCT", "0.0025")
    monkeypatch.setenv("MICRO_CONTINUATION_MAX_HOLD_MINUTES", "5")
    monkeypatch.setenv("MICRO_OPENING_RANGE_TARGET_PCT", "0.006")
    monkeypatch.setenv("MICRO_EARLY_EXIT_ENABLED", "false")
    monkeypatch.setenv("MICRO_INVALIDATION_MIN_HOLD_SECONDS", "90")
    monkeypatch.setenv("MICRO_LOSS_THROTTLE_COUNT", "3")
    monkeypatch.setenv("MICRO_LOSS_THROTTLE_WINDOW_MINUTES", "45")
    monkeypatch.setenv("MICRO_COST_SLIPPAGE_BPS", "8")
    monkeypatch.setenv("MICRO_MIN_EXPECTED_NET_PROFIT", "750")
    monkeypatch.setenv("MICRO_MIN_TARGET_TO_COST_RATIO", "2.2")
    monkeypatch.setenv("POSITION_RECONCILIATION_ENABLED", "false")
    monkeypatch.setenv("RUN_STARTUP_OVERNIGHT_ANALYSIS", "true")
    monkeypatch.setenv("TRADES_TABLE", "trades-test")

    settings = load_settings("prod", include_env=True)

    assert settings.oracle.static_ip == "1.2.3.4"
    assert settings.oracle.execution_proxy_base_url == "https://oracle.example.com"
    assert settings.oracle.collector_base_url == "https://collector.example.com"
    assert settings.bedrock.fast_model_id == "fast-model"
    assert settings.bedrock.reasoning_model_id == "reasoning-model"
    assert settings.bedrock.deep_research_model_id == "deep-model"
    assert settings.trading.paper_trading is False
    assert settings.trading.capital == 250000
    assert settings.trading.max_quantity_per_order == 250
    assert settings.trading.market_closed_poll_seconds == 45
    assert settings.trading.micro_exit_check_interval_seconds == 20
    assert settings.trading.micro_min_continuation_relative_volume == 1.7
    assert settings.trading.micro_max_candle_age_seconds == 240
    assert settings.trading.micro_reentry_cooldown_seconds == 180
    assert settings.trading.micro_continuation_target_pct == 0.0025
    assert settings.trading.micro_continuation_max_hold_minutes == 5
    assert settings.trading.micro_opening_range_target_pct == 0.006
    assert settings.trading.micro_early_exit_enabled is False
    assert settings.trading.micro_invalidation_min_hold_seconds == 90
    assert settings.trading.micro_loss_throttle_count == 3
    assert settings.trading.micro_loss_throttle_window_minutes == 45
    assert settings.trading.micro_cost_slippage_bps == 8
    assert settings.trading.micro_min_expected_net_profit == 750
    assert settings.trading.micro_min_target_to_cost_ratio == 2.2
    assert settings.trading.position_reconciliation_enabled is False
    assert settings.trading.run_startup_overnight_analysis is True
    assert settings.dynamodb.trades_table == "trades-test"


def test_invalid_oracle_url_is_rejected(monkeypatch):
    monkeypatch.setenv("ORACLE_EXECUTION_PROXY_BASE_URL", "oracle.example.com")

    with pytest.raises(ValueError, match="Invalid runtime configuration"):
        load_settings("prod", include_env=True)


def test_runtime_settings_values_are_available_from_typed_config(monkeypatch):
    monkeypatch.setenv("ORACLE_STATIC_IP", "80.225.242.6")
    monkeypatch.setenv("AWS_REGION", "eu-west-2")
    monkeypatch.setenv("CAPITAL", "100000")

    settings = load_settings("prod", include_env=True)

    assert settings.oracle.static_ip == "80.225.242.6"
    assert settings.aws.region == "eu-west-2"
    assert settings.trading.capital == 100000
