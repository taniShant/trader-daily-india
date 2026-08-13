import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AwsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    region: str = "eu-west-2"
    account_id: str | None = None
    profile: str | None = None


class BedrockConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model_id: str = "anthropic.claude-3-7-sonnet-20250219-v1:0"
    fast_model_id: str = "anthropic.claude-3-7-sonnet-20250219-v1:0"
    reasoning_model_id: str = "anthropic.claude-3-7-sonnet-20250219-v1:0"
    deep_research_model_id: str = "anthropic.claude-opus-4-6-v1"
    region: str = "eu-west-2"


class CrossAccountBedrockConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    role_arn: str | None = None
    external_id: str | None = None
    region: str = "eu-west-2"
    session_name: str = "trd-bedrock-runtime"


class DynamoDbConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_table: str = "svc-trd-sessions-dev"
    trades_table: str = "svc-trd-trades-dev"
    learning_table: str = "svc-trd-learning-dev"
    market_state_table: str = "svc-trd-market-state-dev"
    signals_table: str = "svc-trd-signals-dev"
    risk_events_table: str = "svc-trd-risk-events-dev"
    orders_table: str = "svc-trd-orders-dev"
    fills_table: str = "svc-trd-fills-dev"
    positions_table: str = "svc-trd-positions-dev"


class TradingConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    capital: float = Field(default=100000, gt=0)
    max_daily_loss_percent: float = Field(default=4, gt=0)
    max_position_size_percent: float = Field(default=10, gt=0)
    max_quantity_per_order: int = Field(default=50, gt=0)
    min_confidence_threshold: int = Field(default=70, ge=0, le=100)
    analysis_interval_seconds: int = Field(default=180, gt=0)
    watchlist_size: int = Field(default=10, gt=0)
    micro_trading_enabled: bool = False
    micro_scan_interval_seconds: int = Field(default=30, gt=0)
    micro_max_hold_minutes: int = Field(default=10, gt=0)
    micro_min_confidence: int = Field(default=72, ge=0, le=100)
    micro_min_relative_volume: float = Field(default=1.5, gt=0)
    micro_min_continuation_relative_volume: float = Field(default=3.0, gt=0)
    micro_max_candle_age_seconds: int = Field(default=180, gt=0)
    micro_max_symbols_per_cycle: int = Field(default=40, gt=0)
    micro_diagnostic_top_n: int = Field(default=5, ge=0)
    paper_trading: bool = True


class OracleConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    static_ip: str = "80.225.242.6"
    execution_proxy_base_url: str = "http://80.225.242.6:8080"
    execution_proxy_health_url: str = "http://80.225.242.6:8080/health"
    collector_base_url: str = "http://80.225.242.6:8090"
    collector_health_url: str = "http://80.225.242.6:8090/health"
    execution_proxy_client_id: str = "aws-trading-bot"
    execution_proxy_shared_secret: str | None = None
    use_for_build: bool = True
    use_for_live_execution: bool = True

    @field_validator("execution_proxy_base_url", "execution_proxy_health_url", "collector_base_url", "collector_health_url")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return value


class IciciConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    api_key: str | None = None
    secret_key: str | None = None
    session_token: str | None = None
    static_ip: str = "80.225.242.6"


class ApiConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    news_api_key: str | None = None
    twitter_bearer_token: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    allow_simulated_news: bool = False


class MarketSymbolConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    breeze: str
    yahoo: str | None = None
    name: str | None = None
    exchange: str = "NSE"


class MarketSymbolsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    exchange: str = "NSE"
    symbols: dict[str, MarketSymbolConfig] = Field(default_factory=dict)


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    environment: str = "prod"
    aws: AwsConfig = Field(default_factory=AwsConfig)
    bedrock: BedrockConfig = Field(default_factory=BedrockConfig)
    cross_account_bedrock: CrossAccountBedrockConfig = Field(default_factory=CrossAccountBedrockConfig)
    dynamodb: DynamoDbConfig = Field(default_factory=DynamoDbConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    oracle: OracleConfig = Field(default_factory=OracleConfig)
    icici: IciciConfig = Field(default_factory=IciciConfig)
    apis: ApiConfig = Field(default_factory=ApiConfig)
    market_symbols: MarketSymbolsConfig = Field(default_factory=MarketSymbolsConfig)


def _load_json_config(environment: str) -> dict:
    config_path = PROJECT_ROOT / "cicd" / "env" / f"{environment}.json"
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text())


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def _apply_env_overrides(config: dict) -> dict:
    config = dict(config)
    config.setdefault("aws", {})
    config.setdefault("bedrock", {})
    config.setdefault("cross_account_bedrock", {})
    config.setdefault("dynamodb", {})
    config.setdefault("trading", {})
    config.setdefault("oracle", {})
    config.setdefault("icici", {})
    config.setdefault("apis", {})
    config.setdefault("market_symbols", {})

    if os.environ.get("ENVIRONMENT"):
        config["environment"] = os.environ["ENVIRONMENT"]

    env_map = {
        ("aws", "region"): "AWS_REGION",
        ("bedrock", "region"): "BEDROCK_REGION",
        ("bedrock", "model_id"): "BEDROCK_MODEL_ID",
        ("bedrock", "fast_model_id"): "BEDROCK_FAST_MODEL_ID",
        ("bedrock", "reasoning_model_id"): "BEDROCK_REASONING_MODEL_ID",
        ("bedrock", "deep_research_model_id"): "BEDROCK_DEEP_RESEARCH_MODEL_ID",
        ("cross_account_bedrock", "role_arn"): "CROSS_ACCOUNT_BEDROCK_ROLE_ARN",
        ("cross_account_bedrock", "external_id"): "CROSS_ACCOUNT_BEDROCK_EXTERNAL_ID",
        ("cross_account_bedrock", "region"): "CROSS_ACCOUNT_BEDROCK_REGION",
        ("cross_account_bedrock", "session_name"): "CROSS_ACCOUNT_BEDROCK_SESSION_NAME",
        ("dynamodb", "session_table"): "SESSIONS_TABLE",
        ("dynamodb", "trades_table"): "TRADES_TABLE",
        ("dynamodb", "learning_table"): "LEARNING_TABLE",
        ("dynamodb", "market_state_table"): "MARKET_STATE_TABLE",
        ("dynamodb", "signals_table"): "SIGNALS_TABLE",
        ("dynamodb", "risk_events_table"): "RISK_EVENTS_TABLE",
        ("dynamodb", "orders_table"): "ORDERS_TABLE",
        ("dynamodb", "fills_table"): "FILLS_TABLE",
        ("dynamodb", "positions_table"): "POSITIONS_TABLE",
        ("oracle", "static_ip"): "ORACLE_STATIC_IP",
        ("oracle", "execution_proxy_base_url"): "ORACLE_EXECUTION_PROXY_BASE_URL",
        ("oracle", "execution_proxy_health_url"): "ORACLE_EXECUTION_PROXY_HEALTH_URL",
        ("oracle", "collector_base_url"): "ORACLE_COLLECTOR_BASE_URL",
        ("oracle", "collector_health_url"): "ORACLE_COLLECTOR_HEALTH_URL",
        ("oracle", "execution_proxy_client_id"): "ORACLE_PROXY_CLIENT_ID",
        ("oracle", "execution_proxy_shared_secret"): "ORACLE_PROXY_SHARED_SECRET",
        ("icici", "api_key"): "ICICI_API_KEY",
        ("icici", "secret_key"): "ICICI_SECRET_KEY",
        ("icici", "session_token"): "ICICI_SESSION_TOKEN",
        ("icici", "static_ip"): "ICICI_STATIC_IP",
        ("apis", "news_api_key"): "NEWS_API_KEY",
        ("apis", "twitter_bearer_token"): "TWITTER_BEARER_TOKEN",
        ("apis", "reddit_client_id"): "REDDIT_CLIENT_ID",
        ("apis", "reddit_client_secret"): "REDDIT_CLIENT_SECRET",
    }
    for (section, key), env_name in env_map.items():
        if os.environ.get(env_name):
            config[section][key] = os.environ[env_name]

    numeric_env_map = {
        "CAPITAL": ("trading", "capital", float),
        "MAX_DAILY_LOSS_PERCENT": ("trading", "max_daily_loss_percent", float),
        "MAX_POSITION_SIZE_PERCENT": ("trading", "max_position_size_percent", float),
        "MAX_QUANTITY_PER_ORDER": ("trading", "max_quantity_per_order", int),
        "MIN_CONFIDENCE_THRESHOLD": ("trading", "min_confidence_threshold", int),
        "ANALYSIS_INTERVAL_SECONDS": ("trading", "analysis_interval_seconds", int),
        "WATCHLIST_SIZE": ("trading", "watchlist_size", int),
        "MICRO_SCAN_INTERVAL_SECONDS": ("trading", "micro_scan_interval_seconds", int),
        "MICRO_MAX_HOLD_MINUTES": ("trading", "micro_max_hold_minutes", int),
        "MICRO_MIN_CONFIDENCE": ("trading", "micro_min_confidence", int),
        "MICRO_MIN_RELATIVE_VOLUME": ("trading", "micro_min_relative_volume", float),
        "MICRO_MIN_CONTINUATION_RELATIVE_VOLUME": (
            "trading",
            "micro_min_continuation_relative_volume",
            float,
        ),
        "MICRO_MAX_CANDLE_AGE_SECONDS": ("trading", "micro_max_candle_age_seconds", int),
        "MICRO_MAX_SYMBOLS_PER_CYCLE": ("trading", "micro_max_symbols_per_cycle", int),
        "MICRO_DIAGNOSTIC_TOP_N": ("trading", "micro_diagnostic_top_n", int),
    }
    for env_name, (section, key, caster) in numeric_env_map.items():
        if os.environ.get(env_name):
            config[section][key] = caster(os.environ[env_name])

    config["trading"]["paper_trading"] = _env_bool(
        "PAPER_TRADING",
        bool(config["trading"].get("paper_trading", True)),
    )
    config["trading"]["micro_trading_enabled"] = _env_bool(
        "MICRO_TRADING_ENABLED",
        bool(config["trading"].get("micro_trading_enabled", False)),
    )
    config["oracle"]["use_for_build"] = _env_bool(
        "ORACLE_USE_FOR_BUILD",
        bool(config["oracle"].get("use_for_build", True)),
    )
    config["oracle"]["use_for_live_execution"] = _env_bool(
        "ORACLE_USE_FOR_LIVE_EXECUTION",
        bool(config["oracle"].get("use_for_live_execution", True)),
    )
    config["apis"]["allow_simulated_news"] = _env_bool(
        "ALLOW_SIMULATED_NEWS",
        bool(config["apis"].get("allow_simulated_news", False)),
    )
    config["cross_account_bedrock"]["enabled"] = _env_bool(
        "CROSS_ACCOUNT_BEDROCK_ENABLED",
        bool(config["cross_account_bedrock"].get("enabled", False)),
    )

    return config


def load_settings(environment: str | None = None, include_env: bool = True) -> Settings:
    env_name = environment or os.environ.get("CDK_DEPLOY_ENV") or os.environ.get("ENVIRONMENT") or "prod"
    config = _load_json_config(env_name)
    if not config:
        config = {"environment": env_name}
    if include_env:
        config = _apply_env_overrides(config)
    try:
        return Settings.model_validate(config)
    except ValidationError as exc:
        raise ValueError(f"Invalid runtime configuration: {exc}") from exc


settings = load_settings()
