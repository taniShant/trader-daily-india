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
    assert settings.trading.micro_min_relative_volume == 1.2
    assert settings.trading.micro_min_continuation_relative_volume == 1.6


def test_environment_overrides_take_precedence(monkeypatch):
    monkeypatch.setenv("ORACLE_STATIC_IP", "1.2.3.4")
    monkeypatch.setenv("ORACLE_EXECUTION_PROXY_BASE_URL", "https://oracle.example.com")
    monkeypatch.setenv("ORACLE_COLLECTOR_BASE_URL", "https://collector.example.com")
    monkeypatch.setenv("BEDROCK_FAST_MODEL_ID", "fast-model")
    monkeypatch.setenv("BEDROCK_REASONING_MODEL_ID", "reasoning-model")
    monkeypatch.setenv("BEDROCK_DEEP_RESEARCH_MODEL_ID", "deep-model")
    monkeypatch.setenv("PAPER_TRADING", "false")
    monkeypatch.setenv("CAPITAL", "250000")
    monkeypatch.setenv("MICRO_MIN_CONTINUATION_RELATIVE_VOLUME", "1.7")
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
    assert settings.trading.micro_min_continuation_relative_volume == 1.7
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
