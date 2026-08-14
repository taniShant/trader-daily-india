#!/usr/bin/env python3
"""
Multi-Agent Trading Orchestrator using Strands Agents-as-Tools pattern.
Runs continuously on ECS Fargate during market hours.
"""

import os
import json
import time
import signal
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dt_time, timezone
from decimal import Decimal
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

from .contracts.execution import OrderRequest, OrderStatus
from .contracts.risk import RiskDecisionStatus
from .contracts.signals import RiskLevel, SignalAction, TradeSignal as ContractTradeSignal
from .config import settings
from .execution.position_monitor import PositionAction, PositionMonitor
from .execution.router import get_broker
from .execution.square_off import square_off_positions
from .observability import log_event
from .risk import RiskLimits, RiskManager, RiskState
from .storage import (
    PositionSnapshot,
    TradeEventRecord,
    build_bot_heartbeat,
    market_state_repository,
    trading_audit_repositories,
)
from .time import MarketClock

# ============================================================
# CONFIGURATION FROM ENVIRONMENT VARIABLES
# ============================================================


def _read_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _read_float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

AWS_REGION = settings.aws.region
MODEL_ID = settings.bedrock.model_id
FAST_MODEL_ID = settings.bedrock.fast_model_id
REASONING_MODEL_ID = settings.bedrock.reasoning_model_id
DEEP_RESEARCH_MODEL_ID = settings.bedrock.deep_research_model_id
SESSIONS_TABLE = settings.dynamodb.session_table
TRADES_TABLE = settings.dynamodb.trades_table
LEARNING_TABLE = settings.dynamodb.learning_table
MARKET_STATE_TABLE = settings.dynamodb.market_state_table

# Trading parameters
PAPER_TRADING = settings.trading.paper_trading
CAPITAL = settings.trading.capital
ANALYSIS_INTERVAL = settings.trading.analysis_interval_seconds
MIN_CONFIDENCE = settings.trading.min_confidence_threshold
MAX_DAILY_LOSS_PERCENT = settings.trading.max_daily_loss_percent
MAX_POSITION_SIZE_PERCENT = settings.trading.max_position_size_percent
MAX_QUANTITY_PER_ORDER = settings.trading.max_quantity_per_order
WATCHLIST_SIZE = settings.trading.watchlist_size
ALPHA_UNIVERSE_SIZE = _read_int_env("ALPHA_UNIVERSE_SIZE", max(40, WATCHLIST_SIZE))
DEEP_ANALYSIS_SIZE = _read_int_env("DEEP_ANALYSIS_SIZE", WATCHLIST_SIZE)
ALPHA_SCAN_WORKERS = _read_int_env("ALPHA_SCAN_WORKERS", 8)
MICRO_TRADING_ENABLED = settings.trading.micro_trading_enabled
MICRO_SCAN_INTERVAL_SECONDS = settings.trading.micro_scan_interval_seconds
MICRO_MAX_HOLD_MINUTES = settings.trading.micro_max_hold_minutes
MICRO_MIN_CONFIDENCE = settings.trading.micro_min_confidence
MICRO_MIN_RELATIVE_VOLUME = settings.trading.micro_min_relative_volume
MICRO_MIN_CONTINUATION_RELATIVE_VOLUME = settings.trading.micro_min_continuation_relative_volume
MICRO_MAX_CANDLE_AGE_SECONDS = settings.trading.micro_max_candle_age_seconds
MICRO_MAX_SYMBOLS_PER_CYCLE = settings.trading.micro_max_symbols_per_cycle
MICRO_REENTRY_COOLDOWN_SECONDS = settings.trading.micro_reentry_cooldown_seconds
MICRO_DIAGNOSTIC_TOP_N = settings.trading.micro_diagnostic_top_n

# Oracle static IP (for reference/logging)
ORACLE_STATIC_IP = settings.oracle.static_ip

print(f"📋 Trading Bot Configuration:")
print(f"   Region: {AWS_REGION}")
print(f"   Default Model: {MODEL_ID}")
print(f"   Fast Model: {FAST_MODEL_ID}")
print(f"   Reasoning Model: {REASONING_MODEL_ID}")
print(f"   Deep Research Model: {DEEP_RESEARCH_MODEL_ID}")
print(f"   Paper Trading: {PAPER_TRADING}")
print(f"   Capital: ₹{CAPITAL:,.2f}")
print(f"   Analysis Interval: {ANALYSIS_INTERVAL} seconds")
print(f"   Min Confidence: {MIN_CONFIDENCE}%")
print(f"   Max Daily Loss: {MAX_DAILY_LOSS_PERCENT}%")
print(f"   Max Position Size: {MAX_POSITION_SIZE_PERCENT}%")
print(f"   Max Quantity Per Order: {MAX_QUANTITY_PER_ORDER}")
print(f"   Alpha Universe Size: {ALPHA_UNIVERSE_SIZE}")
print(f"   Deep Analysis Size: {DEEP_ANALYSIS_SIZE}")
print(f"   Alpha Scan Workers: {ALPHA_SCAN_WORKERS}")
print(f"   Micro Trading Enabled: {MICRO_TRADING_ENABLED}")
print(f"   Oracle Static IP: {ORACLE_STATIC_IP}")

models = {}
model_expirations = {}
technical_agent = None
sentiment_agent = None
fundamental_agent = None
social_agent = None
derivatives_agent = None
orchestrator = None


MODEL_IDS_BY_TASK = {
    "default": MODEL_ID,
    "fast": FAST_MODEL_ID,
    "reasoning": REASONING_MODEL_ID,
    "deep_research": DEEP_RESEARCH_MODEL_ID,
}

BEDROCK_SESSION_REFRESH_SKEW_SECONDS = 300


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_expiration(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return None


def _is_model_cache_valid(task_type: str) -> bool:
    if task_type not in models:
        return False

    expiration = _normalize_expiration(model_expirations.get(task_type))
    if expiration is None:
        return True

    seconds_remaining = (expiration - _utc_now()).total_seconds()
    return seconds_remaining > BEDROCK_SESSION_REFRESH_SKEW_SECONDS


def _is_cached_model_stale(task_type: str) -> bool:
    return task_type in models and not _is_model_cache_valid(task_type)


def _reset_agent_singletons() -> None:
    global technical_agent, sentiment_agent, fundamental_agent, social_agent, derivatives_agent, orchestrator
    technical_agent = None
    sentiment_agent = None
    fundamental_agent = None
    social_agent = None
    derivatives_agent = None
    orchestrator = None


def refresh_bedrock_runtime(reason: str = "manual") -> None:
    """Clear cached Bedrock-backed agents so the next call gets fresh credentials."""
    models.clear()
    model_expirations.clear()
    _reset_agent_singletons()
    print(f"🔄 Refreshed Bedrock runtime cache ({reason})")


def _is_expired_token_error(error: Exception) -> bool:
    text = str(error)
    return "ExpiredTokenException" in text or "security token included in the request is expired" in text


def get_model(task_type: str = "default"):
    """Initialize Bedrock models lazily by task type so imports stay offline/testable."""
    model_id = MODEL_IDS_BY_TASK.get(task_type, MODEL_ID)
    if not _is_model_cache_valid(task_type):
        from strands.models import BedrockModel
        from .bedrock_session import build_bedrock_session_info

        session_info = build_bedrock_session_info()
        model_kwargs = {
            "model_id": model_id,
            "temperature": 0.2,
            "max_tokens": 4096,
        }
        if session_info is None:
            model_kwargs["region_name"] = AWS_REGION
            model_expirations.pop(task_type, None)
        else:
            model_kwargs["boto_session"] = session_info.boto_session
            model_expirations[task_type] = session_info.expiration

        models[task_type] = BedrockModel(**model_kwargs)
    return models[task_type]


def get_specialist_agents():
    """Initialize specialist agents lazily."""
    global technical_agent, sentiment_agent, fundamental_agent, social_agent, derivatives_agent

    if _is_cached_model_stale("reasoning"):
        refresh_bedrock_runtime("session_near_expiry")

    if technical_agent is None:
        from .specialists.technical import TechnicalAnalyst
        from .specialists.sentiment import SentimentAnalyst
        from .specialists.fundamentals import FundamentalAnalyst
        from .specialists.social import SocialAnalyst
        from .specialists.derivatives import DerivativesAnalyst

        runtime_model = get_model("reasoning")
        technical_agent = TechnicalAnalyst(model=runtime_model)
        sentiment_agent = SentimentAnalyst(model=runtime_model)
        fundamental_agent = FundamentalAnalyst(model=runtime_model)
        social_agent = SocialAnalyst(model=runtime_model)
        derivatives_agent = DerivativesAnalyst(model=runtime_model)

    return {
        "technical": technical_agent,
        "sentiment": sentiment_agent,
        "fundamental": fundamental_agent,
        "social": social_agent,
        "derivatives": derivatives_agent,
    }

# ============================================================
# WRAP SPECIALIST AGENTS AS TOOLS
# ============================================================

def consult_technical_analyst(stock_symbol: str) -> Dict[str, Any]:
    """Consult the technical analyst agent for RSI, MACD, and chart patterns."""
    result = get_specialist_agents()["technical"](f"Analyze {stock_symbol} technicals for intraday trading")
    return result if isinstance(result, dict) else {"analysis": str(result)[:500]}

def consult_sentiment_analyst(stock_symbol: str) -> Dict[str, Any]:
    """Consult the sentiment analyst agent for news and emotion analysis."""
    result = get_specialist_agents()["sentiment"](f"Analyze news sentiment for {stock_symbol}")
    return result if isinstance(result, dict) else {"analysis": str(result)[:500]}

def consult_fundamental_analyst(stock_symbol: str) -> Dict[str, Any]:
    """Consult the fundamentals analyst agent for P/E, market cap, and growth."""
    result = get_specialist_agents()["fundamental"](f"Get fundamentals for {stock_symbol}")
    return result if isinstance(result, dict) else {"analysis": str(result)[:500]}

def consult_social_analyst(stock_symbol: str) -> Dict[str, Any]:
    """Consult the social sentiment analyst for Reddit/Twitter sentiment."""
    result = get_specialist_agents()["social"](f"Get social sentiment for {stock_symbol}")
    return result if isinstance(result, dict) else {"analysis": str(result)[:500]}

def consult_derivatives_analyst(stock_symbol: str) -> Dict[str, Any]:
    """Consult the derivatives analyst for options chain and implied volatility."""
    result = get_specialist_agents()["derivatives"](f"Analyze option chain for {stock_symbol}")
    return result if isinstance(result, dict) else {"analysis": str(result)[:500]}


def _extract_text_from_content(content: Any) -> str:
    """Extract model text from common Strands/Bedrock message content shapes."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    if isinstance(content, dict):
        return str(content.get("text") or content)
    return str(content or "")


def _agent_result_to_text(result: Any) -> str:
    """Normalize Strands AgentResult and plain values into parseable text."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return json.dumps(result)

    structured_output = getattr(result, "structured_output", None)
    if structured_output is not None:
        if hasattr(structured_output, "model_dump_json"):
            return structured_output.model_dump_json()
        if hasattr(structured_output, "model_dump"):
            return json.dumps(structured_output.model_dump())

    message = getattr(result, "message", None)
    if isinstance(message, dict):
        return _extract_text_from_content(message.get("content"))

    content = getattr(message, "content", None)
    if content is not None:
        return _extract_text_from_content(content)

    return str(result)


def _parse_recommendation_payload(result: Any) -> Dict[str, Any]:
    """Parse a final trading recommendation from model output."""
    if isinstance(result, dict):
        return result

    text = _agent_result_to_text(result)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    import re

    code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    json_text = code_block_match.group(1) if code_block_match else None
    if json_text is None:
        json_match = re.search(r"\{.*?\}", text, flags=re.DOTALL)
        json_text = json_match.group(0) if json_match else None

    if json_text:
        try:
            parsed = json.loads(json_text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return {"action": "HOLD", "confidence": 50, "reasoning": text[:300], "risk_level": "HIGH"}


def _coerce_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_feature(features: Dict[str, Any], name: str) -> str:
    if name not in features or features.get(name) is None:
        return "na"
    value = features.get(name)
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _optional_positive_decimal(value: Any) -> Decimal | None:
    numeric = _coerce_float(value)
    if numeric <= 0:
        return None
    return Decimal(str(numeric))


def _has_missing_trade_prices(payload: Dict[str, Any]) -> bool:
    missing_values = {"", "n/a", "na", "none", "null", "-"}
    for field in ["entry_price", "stop_loss", "target_price"]:
        value = payload.get(field)
        if value is None:
            return True
        if isinstance(value, str) and value.strip().lower() in missing_values:
            return True
        try:
            if float(value) <= 0:
                return True
        except (TypeError, ValueError):
            return True
    return False


def _normalize_recommendation_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload)
    action = str(normalized.get("action") or "HOLD").upper()
    reasoning = str(normalized.get("reasoning") or "")

    if action in {"BUY", "SELL"} and _has_missing_trade_prices(normalized):
        normalized["action"] = "HOLD"
        normalized["risk_level"] = "HIGH"
        normalized["confidence"] = min(_coerce_int(normalized.get("confidence"), 50), 50)
        normalized["reasoning"] = (
            f"{reasoning} Missing entry/stop/target prices; downgraded to HOLD for safety."
        ).strip()
    else:
        normalized["action"] = action
        normalized["confidence"] = _coerce_int(normalized.get("confidence"), 50)

    normalized["entry_price"] = _coerce_float(normalized.get("entry_price"))
    normalized["stop_loss"] = _coerce_float(normalized.get("stop_loss"))
    normalized["target_price"] = _coerce_float(normalized.get("target_price"))
    normalized["sentiment_score"] = _coerce_float(normalized.get("sentiment_score"))
    normalized["risk_level"] = str(normalized.get("risk_level") or "MEDIUM").upper()
    normalized["reasoning"] = str(normalized.get("reasoning") or "")
    normalized["technical_summary"] = str(normalized.get("technical_summary") or "")
    return normalized

# ============================================================
# ORCHESTRATOR AGENT 
# ============================================================

def get_orchestrator():
    """Initialize the orchestrator lazily."""
    global orchestrator
    if _is_cached_model_stale("reasoning"):
        refresh_bedrock_runtime("session_near_expiry")

    if orchestrator is None:
        from strands import Agent, tool
        from .tools.market_data import get_live_quote, get_historical_data

        orchestrator = Agent(
            name="TradingOrchestrator",
            model=get_model("reasoning"),
            tools=[
                tool(consult_technical_analyst),
                tool(consult_sentiment_analyst),
                tool(consult_fundamental_analyst),
                tool(consult_social_analyst),
                tool(consult_derivatives_analyst),
                get_live_quote,
                get_historical_data,
            ],
            system_prompt=f"""
            You are a senior trading strategist for the Indian stock market.

            ORACLE STATIC IP: {ORACLE_STATIC_IP} (ICICI Breeze execution proxy boundary)
            PAPER TRADING MODE: {PAPER_TRADING}

            Your job is to analyze a given stock and provide a final intraday trading recommendation.

            FOR EACH STOCK, YOU MUST:
            1. Call ALL specialist analysts (technical, sentiment, fundamental, social, derivatives)
            2. Use get_live_quote for current price
            3. Synthesize their findings into a unified view

            Provide a final recommendation in JSON format with:
            - action: "BUY", "SELL", or "HOLD"
            - confidence: number (0-100) - must be at least {MIN_CONFIDENCE} to execute
            - entry_price: number (within 2% of current price)
            - stop_loss: number (2-3% below entry for BUY)
            - target_price: number (based on technical resistance)
            - reasoning: string (brief explanation)
            - technical_summary: string
            - sentiment_score: number (-1 to +1)
            - risk_level: "LOW", "MEDIUM", or "HIGH"

            RISK MANAGEMENT RULES:
            - Maximum position size: {MAX_POSITION_SIZE_PERCENT}% of capital per trade
            - Maximum daily loss: {MAX_DAILY_LOSS_PERCENT}% of total capital
            - When uncertain, prefer HOLD over trading
            """,
        )
    return orchestrator

# ============================================================
# DATA CLASS FOR TRADING SIGNAL
# ============================================================

@dataclass
class TradingSignal:
    """Structured trading signal output."""
    date: str
    stock_symbol: str
    action: str
    confidence: int
    entry_price: float
    stop_loss: float
    target_price: float
    reasoning: str
    technical_summary: str
    sentiment_score: float
    risk_level: str
    signal_id: str = ""

# ============================================================
# TRADING BOT CLASS (Continuous Market Hours)
# ============================================================

class TradingBot:
    """Continuous trading bot that runs throughout market hours."""
    
    def __init__(self):
        from .alpha import IntradayAlphaScanner
        from .overnight.news_aggregator import NewsAggregator
        from .overnight.global_macro import GlobalMacroCollector
        from .overnight.pre_market_scanner import PreMarketScanner
        from .learning.pattern_analyzer import PatternAnalyzer
        from .learning.confidence_adjuster import ConfidenceAdjuster

        self.active_positions = {}
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.capital = CAPITAL
        self.paper_trading = PAPER_TRADING
        self.min_confidence = MIN_CONFIDENCE
        self.max_daily_loss = CAPITAL * (MAX_DAILY_LOSS_PERCENT / 100)
        self.max_position_size = CAPITAL * (MAX_POSITION_SIZE_PERCENT / 100)
        self.watchlist = []
        self.alpha_universe_size = ALPHA_UNIVERSE_SIZE
        self.deep_analysis_size = DEEP_ANALYSIS_SIZE
        self.alpha_scan_workers = ALPHA_SCAN_WORKERS
        self._alpha_context_cache = {}
        self.micro_trading_enabled = MICRO_TRADING_ENABLED
        self.micro_engine = None
        self.current_sentiment = 0.0
        self.temp_caution_mode = False
        self.running = True
        self.bot_id = os.environ.get("BOT_ID", "trading-bot")
        self.current_session_id = f"{self.bot_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
        self.cycle_count = 0
        self._market_state_repository = None
        self._audit_repositories = None
        self.market_clock = MarketClock()
        self.risk_manager = self._build_risk_manager()
        self.broker = get_broker(paper_trading=self.paper_trading)
        self.micro_engine = self._build_micro_engine() if self.micro_trading_enabled else None
        self.position_monitor = PositionMonitor()
        
        # Initialize modules
        self.news_aggregator = NewsAggregator()
        self.global_macro = GlobalMacroCollector()
        self.pre_market_scanner = PreMarketScanner()
        self.pattern_analyzer = PatternAnalyzer()
        self.confidence_adjuster = ConfidenceAdjuster()
        self.alpha_scanner = IntradayAlphaScanner()
        
        self._setup_signal_handlers()
        self._update_watchlist()
        self._print_config()
        self._record_heartbeat("started")
    
    def _setup_signal_handlers(self):
        """Handle graceful shutdown."""
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)
    
    def _shutdown(self, signum, frame):
        print("\n🛑 Received shutdown signal. Squaring off positions...")
        self.running = False
        self._square_off_all()
        sys.exit(0)
    
    def _print_config(self):
        """Print bot configuration."""
        print("=" * 60)
        print("🤖 TRADING BOT CONFIGURATION")
        print("=" * 60)
        print(f"Oracle Static IP: {ORACLE_STATIC_IP}")
        print(f"Paper Trading: {self.paper_trading}")
        print(f"Capital: ₹{self.capital:,.2f}")
        print(f"Min Confidence: {self.min_confidence}%")
        print(f"Max Daily Loss: ₹{self.max_daily_loss:,.2f} ({MAX_DAILY_LOSS_PERCENT}%)")
        print(f"Max Position Size: ₹{self.max_position_size:,.2f} ({MAX_POSITION_SIZE_PERCENT}%)")
        print(f"Max Quantity Per Order: {MAX_QUANTITY_PER_ORDER}")
        print(f"Watchlist Size: {WATCHLIST_SIZE}")
        print(f"Alpha Universe Size: {self.alpha_universe_size}")
        print(f"Deep Analysis Size: {self.deep_analysis_size}")
        print(f"Alpha Scan Workers: {self.alpha_scan_workers}")
        print(f"Micro Trading Enabled: {self.micro_trading_enabled}")
        if self.micro_trading_enabled:
            print(f"Micro Scan Interval: {MICRO_SCAN_INTERVAL_SECONDS} seconds")
            print(f"Micro Max Hold: {MICRO_MAX_HOLD_MINUTES} minutes")
            print(f"Micro Min Confidence: {MICRO_MIN_CONFIDENCE}%")
            print(f"Micro Min Relative Volume: {MICRO_MIN_RELATIVE_VOLUME:.2f}x")
            print(f"Micro Continuation Min Relative Volume: {MICRO_MIN_CONTINUATION_RELATIVE_VOLUME:.2f}x")
            print(f"Micro Max Candle Age: {MICRO_MAX_CANDLE_AGE_SECONDS} seconds")
            print(f"Micro Symbols Per Cycle: {MICRO_MAX_SYMBOLS_PER_CYCLE}")
        print(f"Analysis Interval: {ANALYSIS_INTERVAL} seconds")
        print(f"Bedrock Fast Model: {FAST_MODEL_ID}")
        print(f"Bedrock Reasoning Model: {REASONING_MODEL_ID}")
        print(f"Bedrock Deep Research Model: {DEEP_RESEARCH_MODEL_ID}")
        print("=" * 60)
    
    def _update_watchlist(self):
        """Update watchlist from pre-market scanner or use default."""
        try:
            self.watchlist = self.pre_market_scanner.get_watchlist()
            if not self.watchlist:
                # Previous broader fallback:
                # ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
                #  "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE", "MARUTI", "ITC"]
                self.watchlist = [
                    "RELIANCE", "INFY", "ICICIBANK", "BHARTIARTL",
                    "MARUTI", "JSWSTEEL", "BAJAJFINSV", "ASIANPAINT"
                ][:WATCHLIST_SIZE]
            print(f"📋 Watchlist ({len(self.watchlist)} stocks): {', '.join(self.watchlist)}")
        except Exception as e:
            print(f"Error loading watchlist: {e}")
            # Previous emergency fallback:
            # ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "MARUTI"]
            self.watchlist = [
                "RELIANCE", "INFY", "ICICIBANK", "BHARTIARTL",
                "MARUTI", "JSWSTEEL", "BAJAJFINSV", "ASIANPAINT"
            ][:WATCHLIST_SIZE]
    
    def _is_market_hours(self) -> bool:
        """Check if market is open (9:15 AM - 3:30 PM IST)."""
        return self.market_clock.is_market_open()

    def _is_new_trade_allowed(self) -> bool:
        """Check if fresh entries are allowed before the new-trade cutoff."""
        return self.market_clock.is_new_trade_allowed()
    
    def _should_square_off(self) -> bool:
        """Check if nearing market close (square off by 3:20 PM IST)."""
        return self.market_clock.should_square_off()
    
    def _check_circuit_breakers(self) -> bool:
        """Check if trading should continue based on risk limits."""
        if self.daily_pnl <= -self.max_daily_loss:
            print(f"⚠️ Daily loss limit reached: ₹{abs(self.daily_pnl):,.2f}")
            return False
        if self.consecutive_losses >= 3:
            print("⚠️ 3 consecutive losses - halting trading")
            return False
        return True
    
    def _calculate_position_size(self, price: float, confidence: int) -> int:
        """Calculate position size based on capital and confidence."""
        base_value = self.capital * (MAX_POSITION_SIZE_PERCENT / 100)
        confidence_multiplier = confidence / 100
        trade_value = base_value * confidence_multiplier
        quantity = int(trade_value / price)
        return min(quantity, MAX_QUANTITY_PER_ORDER)

    def _build_risk_manager(self) -> RiskManager:
        return RiskManager(
            RiskLimits(
                capital=Decimal(str(self.capital)),
                max_daily_loss_percent=Decimal(str(MAX_DAILY_LOSS_PERCENT)),
                max_position_size_percent=Decimal(str(MAX_POSITION_SIZE_PERCENT)),
                min_confidence=self.min_confidence,
                max_quantity_per_order=MAX_QUANTITY_PER_ORDER,
            )
        )

    def _build_micro_engine(self):
        from .micro import MicroTradeConfig, MicroTradingEngine
        from .tools.market_data import get_market_data

        return MicroTradingEngine(
            market_data_provider=get_market_data(),
            broker=self.broker,
            risk_manager=self.risk_manager,
            config=MicroTradeConfig(
                enabled=True,
                max_hold_minutes=MICRO_MAX_HOLD_MINUTES,
                min_confidence=MICRO_MIN_CONFIDENCE,
                min_relative_volume=MICRO_MIN_RELATIVE_VOLUME,
                min_continuation_relative_volume=MICRO_MIN_CONTINUATION_RELATIVE_VOLUME,
                max_candle_age_seconds=MICRO_MAX_CANDLE_AGE_SECONDS,
                max_symbols_per_cycle=MICRO_MAX_SYMBOLS_PER_CYCLE,
                reentry_cooldown_seconds=MICRO_REENTRY_COOLDOWN_SECONDS,
            ),
        )

    def _get_market_state_repository(self):
        if self._market_state_repository is None:
            self._market_state_repository = market_state_repository()
        return self._market_state_repository

    def _get_audit_repositories(self):
        if getattr(self, "_audit_repositories", None) is None:
            self._audit_repositories = trading_audit_repositories()
        return self._audit_repositories

    def _record_heartbeat(self, status: str) -> None:
        try:
            heartbeat = build_bot_heartbeat(
                bot_id=self.bot_id,
                status=status,
                mode="paper" if self.paper_trading else "live",
                environment=settings.environment,
                cycle=self.cycle_count,
                market_open=self._is_market_hours(),
                active_positions=len(self.active_positions),
                daily_pnl=Decimal(str(self.daily_pnl)),
            )
            self._get_market_state_repository().put_heartbeat(heartbeat)
        except Exception as e:
            print(f"⚠️ Heartbeat write failed: {e}")

    def _to_contract_signal(self, signal: TradingSignal) -> ContractTradeSignal:
        """Convert current orchestrator signal shape into the risk contract."""
        action = SignalAction(signal.action.upper())
        risk_level = RiskLevel(signal.risk_level.upper())
        entry_price = _optional_positive_decimal(signal.entry_price)
        stop_loss = _optional_positive_decimal(signal.stop_loss)
        target_price = _optional_positive_decimal(signal.target_price)
        return ContractTradeSignal(
            signal_id=signal.signal_id or f"{signal.stock_symbol}-{signal.date}-{action}",
            symbol=signal.stock_symbol,
            action=action,
            confidence=signal.confidence,
            generated_at=datetime.now(timezone.utc),
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
            holding_window_minutes=30 if action != SignalAction.HOLD else None,
            risk_level=risk_level,
            sentiment_score=signal.sentiment_score,
            reasons=[signal.reasoning] if signal.reasoning else [],
            raw_features={
                "technical_summary": signal.technical_summary,
                "legacy_signal": asdict(signal),
            },
        )

    def _record_signal_audit(self, signal: TradingSignal) -> ContractTradeSignal | None:
        try:
            contract_signal = self._to_contract_signal(signal)
            self._get_audit_repositories().signals.put_signal(
                contract_signal,
                session_id=getattr(self, "current_session_id", None),
            )
            print(f"   🧾 Recorded signal audit for {signal.stock_symbol}")
            return contract_signal
        except Exception as e:
            print(f"   ⚠️ Signal audit write failed for {signal.stock_symbol}: {e}")
            return None

    def _record_risk_decision(self, decision) -> None:
        try:
            self._get_audit_repositories().risk_events.put_decision(decision)
        except Exception as e:
            print(f"   ⚠️ Risk audit write failed for {decision.signal_id}: {e}")

    @staticmethod
    def _alpha_setup_rank(context: Dict[str, Any]) -> tuple:
        """Rank deterministic setups before spending LLM calls."""
        action = str(context.get("action") or "HOLD").upper()
        data_quality = str(context.get("data_quality") or "").lower()
        features = context.get("features") if isinstance(context.get("features"), dict) else {}
        conviction = _coerce_int(context.get("conviction"), 0)
        relative_volume = _coerce_float(features.get("relative_volume") or features.get("volume_ratio"))

        data_score = 1 if data_quality == "ok" else 0
        action_score = {"BUY": 3, "SELL": 3, "HOLD": 1}.get(action, 0)
        return (data_score, action_score, conviction, relative_volume)

    @staticmethod
    def _dedupe_symbols(symbols: List[str]) -> List[str]:
        from .data.symbols import resolve_symbol

        result = []
        seen = set()
        for symbol in symbols:
            try:
                canonical = resolve_symbol(symbol).canonical
            except Exception:
                canonical = str(symbol).strip().upper()
            if not canonical or canonical in seen:
                continue
            seen.add(canonical)
            result.append(canonical)
        return result

    def _get_alpha_universe(self) -> List[str]:
        """Build a broad but bounded universe for the fast deterministic scan."""
        universe = list(self.watchlist)
        try:
            universe.extend(self.pre_market_scanner.get_nifty_stocks())
        except Exception as e:
            print(f"   ⚠️ Could not load broad alpha universe: {e}")

        universe = self._dedupe_symbols(universe)
        filter_excluded = getattr(self.pre_market_scanner, "_filter_excluded_symbols", None)
        if callable(filter_excluded):
            universe = self._dedupe_symbols(filter_excluded(universe))

        return universe[: max(1, self.alpha_universe_size)]

    def _scan_alpha_candidate(self, symbol: str) -> Dict[str, Any]:
        setup = self.alpha_scanner.analyze_symbol(symbol)
        return setup.to_dict()

    def _select_deep_analysis_symbols(self) -> List[str]:
        """Use alpha scanning to choose which symbols deserve full agent analysis."""
        universe = self._get_alpha_universe()
        self._alpha_context_cache = {}
        if not universe:
            return list(self.watchlist)

        max_workers = max(1, min(self.alpha_scan_workers, len(universe)))
        contexts = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_symbol = {
                executor.submit(self._scan_alpha_candidate, symbol): symbol
                for symbol in universe
            }
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    context = future.result()
                except Exception as e:
                    context = {
                        "symbol": symbol,
                        "action": "HOLD",
                        "conviction": 0,
                        "setup": "scanner_error",
                        "data_quality": "unavailable",
                        "reasons": [str(e)],
                    }
                canonical = str(context.get("symbol") or symbol).upper()
                context["symbol"] = canonical
                self._alpha_context_cache[canonical] = context
                contexts.append(context)

        contexts.sort(key=self._alpha_setup_rank, reverse=True)
        limit = max(1, min(self.deep_analysis_size, len(contexts)))
        selected = contexts[:limit]
        selected_symbols = {context["symbol"] for context in selected}

        required_symbols = getattr(self.pre_market_scanner, "required_symbols", [])
        for required_symbol in self._dedupe_symbols(required_symbols):
            if required_symbol in selected_symbols or required_symbol not in self._alpha_context_cache:
                continue
            required_context = self._alpha_context_cache[required_symbol]
            if len(selected) >= limit:
                removable_index = next(
                    (
                        index
                        for index in range(len(selected) - 1, -1, -1)
                        if selected[index]["symbol"] not in required_symbols
                    ),
                    None,
                )
                if removable_index is not None:
                    selected.pop(removable_index)
            selected.append(required_context)
            selected_symbols.add(required_symbol)

        selected = selected[:limit]
        summary = ", ".join(
            f"{context['symbol']}:{context.get('action', 'HOLD')}:{context.get('conviction', 0)}:"
            f"{context.get('data_quality', 'unknown')}"
            for context in selected
        )
        print(
            f"⚡ Alpha universe scan: {len(universe)} symbols -> "
            f"{len(selected)} deep candidates"
        )
        if summary:
            print(f"   Candidates: {summary}")

        return [context["symbol"] for context in selected]
    
    def _analyze_stock(self, stock_symbol: str) -> Optional[TradingSignal]:
        """Run multi-agent analysis for a single stock."""
        print(f"\n📊 Analyzing {stock_symbol}...")
        alpha_context = self._get_alpha_context(stock_symbol)
        
        prompt = f"""
        Analyze {stock_symbol} for intraday trading.
        Current market sentiment: {self.current_sentiment}
        Deterministic alpha scanner context: {alpha_context}
        Treat the alpha scanner as the primary price/volume setup gate:
        - If alpha action is HOLD or data_quality is unavailable, prefer HOLD unless live quote and technical tools provide valid prices.
        - If alpha action is BUY/SELL, validate it against news, fundamentals, sentiment, derivatives, and risk.
        - Do not issue BUY/SELL unless entry_price, stop_loss, and target_price are numeric.
        Call all specialist analysts, get live quote, and provide a final recommendation in JSON format.
        """
        
        for attempt in range(2):
            try:
                result = get_orchestrator()(prompt)
                break
            except Exception as e:
                if attempt == 0 and _is_expired_token_error(e):
                    print("   🔄 Bedrock credentials expired; refreshing assumed-role session and retrying")
                    refresh_bedrock_runtime("expired_token")
                    continue
                print(f"   ❌ Error: {e}")
                return None

        try:
            result_dict = _normalize_recommendation_payload(_parse_recommendation_payload(result))
            
            # Adjust confidence based on learned patterns
            adjusted_confidence = self._adjust_confidence(result_dict["confidence"])
            
            return TradingSignal(
                date=datetime.now().strftime("%Y-%m-%d"),
                stock_symbol=stock_symbol,
                action=result_dict["action"],
                confidence=min(100, max(0, adjusted_confidence)),
                entry_price=result_dict["entry_price"],
                stop_loss=result_dict["stop_loss"],
                target_price=result_dict["target_price"],
                reasoning=result_dict["reasoning"][:300],
                technical_summary=result_dict["technical_summary"][:200],
                sentiment_score=result_dict["sentiment_score"],
                risk_level=result_dict["risk_level"],
                signal_id=(
                    f"{stock_symbol}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}-"
                    f"{result_dict['action']}"
                ),
            )
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return None

    def _get_alpha_context(self, stock_symbol: str) -> Dict[str, Any]:
        try:
            cached_context = getattr(self, "_alpha_context_cache", {}).get(stock_symbol.upper())
            if cached_context:
                print(
                    f"   🔎 Alpha scanner: {cached_context['action']} "
                    f"{cached_context['symbol']} ({cached_context['conviction']}%) - "
                    f"{cached_context['setup']}"
                )
                return cached_context

            setup = self.alpha_scanner.analyze_symbol(stock_symbol)
            context = setup.to_dict()
            print(
                f"   🔎 Alpha scanner: {context['action']} "
                f"{context['symbol']} ({context['conviction']}%) - {context['setup']}"
            )
            return context
        except Exception as e:
            print(f"   ⚠️ Alpha scanner error for {stock_symbol}: {e}")
            return {
                "symbol": stock_symbol,
                "action": "HOLD",
                "conviction": 0,
                "setup": "scanner_error",
                "data_quality": "unavailable",
                "reasons": [str(e)],
            }
    
    def _adjust_confidence(self, base_confidence: int) -> int:
        """Adjust confidence based on current market conditions."""
        adjusted = base_confidence
        current_sentiment = _coerce_float(self.current_sentiment)
        
        # Adjust based on news sentiment
        if current_sentiment > 0.5:
            adjusted += 5
        elif current_sentiment < -0.3:
            adjusted -= 10
        
        # Adjust based on caution mode
        if self.temp_caution_mode:
            adjusted -= 15
        
        # Adjust based on pattern learning
        try:
            learning_adjustment = self.confidence_adjuster.get_adjustment_factor()
            adjusted = int(adjusted * learning_adjustment)
        except:
            pass
        
        return max(50, min(90, adjusted))
    
    def _execute_signal(self, signal: TradingSignal):
        """Execute or log a trading signal."""
        if signal.action.upper() == "HOLD":
            log_event(
                "signal_hold",
                symbol=signal.stock_symbol,
                mode="paper" if self.paper_trading else "live",
                confidence=signal.confidence,
                reason=signal.reasoning[:200],
            )
            print(f"   ⏭️ Skipping HOLD {signal.stock_symbol} - no order required")
            return

        if self.risk_manager.limits.min_confidence != self.min_confidence:
            self.risk_manager = self._build_risk_manager()

        contract_signal = self._to_contract_signal(signal)
        risk_decision = self.risk_manager.evaluate(
            contract_signal,
            RiskState(
                daily_pnl=Decimal(str(self.daily_pnl)),
                consecutive_losses=self.consecutive_losses,
                new_trades_allowed=self._is_new_trade_allowed(),
            ),
        )
        self._record_risk_decision(risk_decision)

        if risk_decision.status == RiskDecisionStatus.REJECTED:
            reason = "; ".join(risk_decision.reasons)
            log_event(
                "risk_rejected",
                symbol=signal.stock_symbol,
                signal_id=contract_signal.signal_id,
                mode="paper" if self.paper_trading else "live",
                reason=reason,
                confidence=signal.confidence,
            )
            print(
                f"   ⏭️ Skipping {signal.action} {signal.stock_symbol} - "
                f"{reason}"
            )
            return

        quantity = risk_decision.approved_quantity
        
        print(f"\n🔔 EXECUTING: {signal.action} {signal.stock_symbol}")
        print(f"   Entry: ₹{signal.entry_price} | Stop: ₹{signal.stop_loss} | Target: ₹{signal.target_price}")
        print(f"   Quantity: {quantity} | Confidence: {signal.confidence}%")
        print(f"   Reasoning: {signal.reasoning[:100]}...")
        
        order_request = OrderRequest(
            client_order_id=f"{contract_signal.signal_id}-{risk_decision.decision_id}",
            signal_id=contract_signal.signal_id,
            risk_decision_id=risk_decision.decision_id,
            symbol=signal.stock_symbol,
            side=risk_decision.side,
            order_type=risk_decision.order_type,
            quantity=quantity,
            price=risk_decision.approved_price,
            stop_loss=contract_signal.stop_loss,
            target_price=contract_signal.target_price,
            requested_at=datetime.utcnow(),
        )

        try:
            from .tools.database import save_trade_signal

            status = self.broker.place_order(order_request)
            if self._is_successful_order_status(status):
                log_event(
                    "order_submitted",
                    symbol=signal.stock_symbol,
                    signal_id=contract_signal.signal_id,
                    order_id=order_request.client_order_id,
                    mode="paper" if self.paper_trading else "live",
                    status=status,
                    quantity=quantity,
                )
                print(f"   ✅ Order status: {status}")
                self.active_positions[signal.stock_symbol] = {
                    "quantity": quantity,
                    "entry_price": signal.entry_price,
                    "stop_loss": signal.stop_loss,
                    "target": signal.target_price,
                    "side": risk_decision.side,
                    "order_id": order_request.client_order_id,
                    "signal_id": contract_signal.signal_id,
                    "status": status,
                    "opened_at": datetime.utcnow().isoformat(),
                    "timeout_minutes": contract_signal.holding_window_minutes or 30,
                }
                save_trade_signal(signal)
            else:
                log_event(
                    "order_failed",
                    symbol=signal.stock_symbol,
                    signal_id=contract_signal.signal_id,
                    order_id=order_request.client_order_id,
                    mode="paper" if self.paper_trading else "live",
                    reason=f"broker_status:{status}",
                )
                print(f"   ❌ Order failed with status: {status}")
        except Exception as e:
            log_event(
                "order_error",
                symbol=signal.stock_symbol,
                signal_id=contract_signal.signal_id,
                order_id=order_request.client_order_id,
                mode="paper" if self.paper_trading else "live",
                reason=str(e),
            )
            print(f"   ❌ Order error: {e}")
    
    def _monitor_positions(self):
        """Monitor open positions for stop-loss or target hits."""
        if not self.active_positions:
            return

        from .tools.market_data import get_live_quote

        for symbol, position in list(self.active_positions.items()):
            quote = get_live_quote(symbol)
            if quote.get("error"):
                print(f"   ⚠️ Cannot monitor {symbol}: {quote.get('error')}")
                continue
            decision = self.position_monitor.evaluate(
                symbol,
                position,
                current_price=Decimal(str(quote["ltp"])),
                square_off_due=self._should_square_off(),
            )
            if decision.action == PositionAction.SQUARE_OFF:
                log_event(
                    "position_square_off_triggered",
                    symbol=symbol,
                    order_id=position.get("order_id"),
                    mode="paper" if self.paper_trading else "live",
                    reason=decision.reason,
                )
                status = self.broker.square_off(symbol, abs(int(position["quantity"])))
                if self._is_successful_order_status(status):
                    exit_price = Decimal(str(quote["ltp"]))
                    self._record_position_exit(symbol, position, exit_price, status, decision.reason)
                    print(f"   ✅ Position square-off triggered for {symbol}: {decision.reason}")
                    self.active_positions.pop(symbol, None)
                else:
                    print(f"   ❌ Position square-off failed for {symbol}: {status}")

    @staticmethod
    def _is_successful_order_status(status: OrderStatus) -> bool:
        return status in {
            OrderStatus.SUBMITTED,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
        }
    
    def _square_off_all(self):
        """Close all open positions."""
        if not self.active_positions:
            return
        
        print("\n🔒 Squaring off all positions...")
        results = square_off_positions(self.broker, self.active_positions)
        for result in results:
            symbol = result.symbol
            position = self.active_positions.get(symbol, {})
            try:
                if result.success:
                    exit_price = self._position_exit_price(position)
                    self._record_position_exit(symbol, position, exit_price, result.status, result.reason)
                    log_event(
                        "square_off_submitted",
                        symbol=symbol,
                        order_id=position.get("order_id"),
                        mode="paper" if self.paper_trading else "live",
                        status=result.status,
                    )
                    print(f"   ✅ Squared off {symbol}")
                else:
                    log_event(
                        "square_off_failed",
                        symbol=symbol,
                        order_id=position.get("order_id"),
                        mode="paper" if self.paper_trading else "live",
                        reason=result.reason,
                    )
                    print(f"   ❌ Failed to square off {symbol}: {result.status}")
            except Exception as e:
                log_event(
                    "square_off_error",
                    symbol=symbol,
                    order_id=position.get("order_id"),
                    mode="paper" if self.paper_trading else "live",
                    reason=str(e),
                )
                print(f"   ❌ Error squaring off {symbol}: {e}")
        
        self.active_positions.clear()

    def _record_position_exit(
        self,
        symbol: str,
        position: dict[str, Any],
        exit_price: Decimal,
        status: OrderStatus,
        reason: str,
    ) -> None:
        try:
            session_id = getattr(self, "current_session_id", None) or self.bot_id
            now = datetime.now(timezone.utc)
            quantity = int(position.get("quantity", 0))
            absolute_quantity = abs(quantity)
            if absolute_quantity <= 0:
                return

            entry_price = Decimal(str(position.get("entry_price")))
            is_long = self._is_long_position(position)
            realized_pnl = (
                (exit_price - entry_price) * Decimal(absolute_quantity)
                if is_long
                else (entry_price - exit_price) * Decimal(absolute_quantity)
            )
            exit_action = "SELL" if is_long else "BUY"
            signal_id = str(position.get("signal_id") or position.get("order_id") or f"exit-{symbol}")
            order_id = str(position.get("order_id") or f"exit-{symbol}-{now.strftime('%Y%m%dT%H%M%S%f')}")

            repos = self._get_audit_repositories()
            repos.positions.put_snapshot(
                PositionSnapshot(
                    symbol=symbol,
                    session_id=session_id,
                    quantity=0,
                    average_price=entry_price,
                    last_price=exit_price,
                    unrealized_pnl=Decimal("0"),
                    updated_at=now,
                    side="LONG" if is_long else "SHORT",
                    status="CLOSED",
                )
            )
            repos.pnl.put_trade_event(
                TradeEventRecord(
                    trade_id=f"micro-exit-{symbol}-{now.strftime('%Y%m%dT%H%M%S%f')}",
                    date=now.date().isoformat(),
                    timestamp=now,
                    symbol=symbol,
                    action=exit_action,
                    price=exit_price,
                    quantity=absolute_quantity,
                    pnl=realized_pnl,
                    session_id=session_id,
                    signal_id=signal_id,
                    order_id=order_id,
                    status=status.value,
                    source="paper" if self.paper_trading else "live",
                    confidence=0,
                )
            )
            print(
                f"   🧾 Recorded exit audit for {symbol}: "
                f"{reason}, pnl={realized_pnl:.2f}"
            )
        except Exception as e:
            print(f"   ⚠️ Exit audit write failed for {symbol}: {e}")

    @staticmethod
    def _is_long_position(position: dict[str, Any]) -> bool:
        side = str(position.get("side", "")).upper()
        if side in {"BUY", "LONG"}:
            return True
        if side in {"SELL", "SHORT"}:
            return False
        return int(position.get("quantity", 0)) > 0

    @staticmethod
    def _position_exit_price(position: dict[str, Any]) -> Decimal:
        for key in ("last_price", "current_price", "entry_price"):
            value = position.get(key)
            if value is not None:
                return Decimal(str(value))
        return Decimal("0")
    
    def _run_overnight_analysis(self):
        """Run overnight analysis (global macro + news + pre-market scan)."""
        print("\n🌙 Running overnight analysis...")
        
        try:
            global_data = self.global_macro.collect()
            print(f"   ✅ Global macro data collected (Sentiment: {global_data.get('global_sentiment', 'neutral')})")
        except Exception as e:
            print(f"   ❌ Global macro error: {e}")
        
        try:
            news_data = self.news_aggregator.overnight_aggregate()
            print(f"   ✅ Overnight news aggregated (Sentiment: {news_data.get('sentiment_score', 0)})")
        except Exception as e:
            print(f"   ❌ News aggregation error: {e}")
        
        try:
            watchlist = self.pre_market_scanner.scan_stocks()
            print(f"   ✅ Pre-market watchlist generated ({len(watchlist)} stocks)")
        except Exception as e:
            print(f"   ❌ Pre-market scan error: {e}")
        
        try:
            patterns = self.pattern_analyzer.analyze_patterns(days=30)
            print(f"   ✅ Pattern analysis complete ({patterns.get('total_trades', 0)} trades analyzed)")
            
            # Update confidence threshold based on patterns
            new_threshold = self.confidence_adjuster.update_from_patterns()
            if new_threshold != self.min_confidence:
                print(f"   📊 Confidence threshold adjusted: {self.min_confidence}% → {new_threshold}%")
                self.min_confidence = new_threshold
        except Exception as e:
            print(f"   ❌ Pattern analysis error: {e}")
    
    def _run_market_hours_cycle(self):
        """Execute one trading cycle during market hours."""
        if not self._check_circuit_breakers():
            return
        
        if self._should_square_off():
            self._square_off_all()
            return
        
        # Scan real-time news
        try:
            news_update = self.news_aggregator.real_time_scan()
            if news_update.get("has_breaking"):
                print(f"📰 BREAKING NEWS! Sentiment: {news_update.get('sentiment_update')}")
                if news_update.get("sentiment_update") and news_update["sentiment_update"] < -0.5:
                    self.temp_caution_mode = True
                elif news_update.get("sentiment_update") and news_update["sentiment_update"] > 0.5:
                    self.temp_caution_mode = False
            
            self.current_sentiment = self.news_aggregator.get_latest_sentiment()
        except Exception as e:
            print(f"⚠️ News scan error: {e}")
        
        if not self._is_new_trade_allowed():
            print("⏳ New-trade cutoff reached; monitoring existing positions only.")
            self._monitor_positions()
            return

        # Run a fast deterministic alpha pass first, then spend LLM calls only on the best setups.
        try:
            deep_candidates = self._select_deep_analysis_symbols()
        except Exception as e:
            print(f"⚠️ Alpha shortlist failed; falling back to watchlist: {e}")
            self._alpha_context_cache = {}
            deep_candidates = list(self.watchlist)

        for stock in deep_candidates:
            signal = self._analyze_stock(stock)
            if signal:
                self._record_signal_audit(signal)
            if signal and signal.action.upper() == "HOLD":
                print(f"   ⏭️ Skipping HOLD {signal.stock_symbol} - continuing watchlist")
            elif signal:
                self._execute_signal(signal)
            time.sleep(1)
        
        self._monitor_positions()

    def _run_micro_market_cycle(self) -> None:
        """Execute one fast micro-trading cycle during market hours."""
        if not self._check_circuit_breakers():
            return

        if self._should_square_off():
            self._square_off_all()
            return

        if not self._is_new_trade_allowed():
            print("⏳ New-trade cutoff reached; monitoring existing micro positions only.")
            self._monitor_positions()
            return

        self._run_micro_trading_cycle()
        self._monitor_positions()

    def _run_micro_trading_cycle(self) -> None:
        if not self.micro_engine:
            return

        print("⚡ Running micro-trading fast lane...")
        attempts = self.micro_engine.scan_once(
            self._get_alpha_universe(),
            risk_state=RiskState(
                daily_pnl=Decimal(str(self.daily_pnl)),
                consecutive_losses=self.consecutive_losses,
                new_trades_allowed=self._is_new_trade_allowed(),
            ),
        )
        executed = [attempt for attempt in attempts if attempt.executed]
        actionable = [
            attempt for attempt in attempts
            if attempt.setup.action in {"BUY", "SELL"}
        ]
        print(
            f"⚡ Micro lane: {len(attempts)} scanned, "
            f"{len(actionable)} actionable, {len(executed)} executed"
        )
        self._log_micro_rejection_summary(attempts)
        self._persist_micro_attempts(attempts)
        self._log_micro_diagnostics(attempts)

    def _log_micro_rejection_summary(self, attempts) -> None:
        if not attempts:
            return

        summary = {
            "data_unavailable": 0,
            "volume_failed": 0,
            "continuation_volume_failed": 0,
            "volatility_failed": 0,
            "vwap_extension_failed": 0,
            "confidence_failed": 0,
            "position_or_cooldown": 0,
            "other_hold": 0,
        }
        for attempt in attempts:
            setup = attempt.setup
            if setup.action in {"BUY", "SELL"}:
                if setup.confidence < MICRO_MIN_CONFIDENCE:
                    summary["confidence_failed"] += 1
                continue

            reason_text = " ".join([*(setup.reasons or []), attempt.skipped_reason or ""]).lower()
            features = setup.features or {}
            relative_volume = _coerce_float(features.get("relative_volume"), 0.0)
            classified = False

            if "market_data_unavailable" in reason_text or "micro_setup_error" in reason_text:
                summary["data_unavailable"] += 1
                classified = True
            if "stale_candle" in reason_text or "candle_timestamp" in reason_text:
                summary["data_unavailable"] += 1
                classified = True
            if "position_" in reason_text or "cooldown" in reason_text:
                summary["position_or_cooldown"] += 1
                classified = True
            if relative_volume and relative_volume < MICRO_MIN_RELATIVE_VOLUME:
                summary["volume_failed"] += 1
                classified = True
            if relative_volume and relative_volume < MICRO_MIN_CONTINUATION_RELATIVE_VOLUME:
                summary["continuation_volume_failed"] += 1
                classified = True
            if "volatility too" in reason_text:
                summary["volatility_failed"] += 1
                classified = True
            if "overextended versus vwap" in reason_text:
                summary["vwap_extension_failed"] += 1
                classified = True
            if setup.confidence < MICRO_MIN_CONFIDENCE and setup.setup != "micro_monitor":
                summary["confidence_failed"] += 1
                classified = True
            if not classified:
                summary["other_hold"] += 1

        details = ", ".join(f"{key}={value}" for key, value in summary.items() if value)
        print(f"⚡ Micro rejection summary: {details or 'none'}")

    def _persist_micro_attempts(self, attempts) -> None:
        for attempt in attempts:
            if not any((attempt.signal, attempt.risk_decision, attempt.order, attempt.executed)):
                continue

            try:
                self._persist_micro_attempt(attempt)
            except Exception as e:
                print(f"   ⚠️ Micro audit write failed for {attempt.symbol}: {e}")

    def _persist_micro_attempt(self, attempt) -> None:
        repos = self._get_audit_repositories()
        session_id = getattr(self, "current_session_id", None) or self.bot_id

        if attempt.signal:
            repos.signals.put_signal(attempt.signal, session_id=session_id)

        if attempt.risk_decision:
            repos.risk_events.put_decision(attempt.risk_decision)

        if not attempt.order:
            return

        status = attempt.order_status or OrderStatus.CREATED
        broker_order_id = None
        fills = []
        get_fills = getattr(self.broker, "get_fills", None)
        if callable(get_fills):
            fills = get_fills(attempt.order.client_order_id)
            if fills:
                broker_order_id = fills[0].broker_order_id

        repos.orders.put_order(attempt.order, status=status, broker_order_id=broker_order_id)
        for fill in fills:
            repos.fills.put_fill(fill)

        if self._is_successful_order_status(status):
            self._record_micro_position(attempt, fills, session_id)
            self._record_micro_trade_event(attempt, fills, session_id, status)

    def _record_micro_position(self, attempt, fills, session_id: str) -> None:
        order = attempt.order
        if not order:
            return

        fill_price = fills[-1].fill_price if fills else order.price
        if fill_price is None:
            return

        signed_quantity = order.quantity if order.side.value == "BUY" else -order.quantity
        self.active_positions[order.symbol] = {
            "quantity": signed_quantity,
            "entry_price": float(fill_price),
            "stop_loss": float(order.stop_loss) if order.stop_loss is not None else None,
            "target": float(order.target_price) if order.target_price is not None else None,
            "side": order.side,
            "order_id": order.client_order_id,
            "signal_id": order.signal_id,
            "status": attempt.order_status,
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "timeout_minutes": attempt.signal.holding_window_minutes if attempt.signal else MICRO_MAX_HOLD_MINUTES,
        }

        snapshot = PositionSnapshot(
            symbol=order.symbol,
            session_id=session_id,
            quantity=signed_quantity,
            average_price=fill_price,
            last_price=fill_price,
            unrealized_pnl=Decimal("0"),
            updated_at=datetime.now(timezone.utc),
            side="LONG" if order.side.value == "BUY" else "SHORT",
            status="OPEN",
        )
        self._get_audit_repositories().positions.put_snapshot(snapshot)

    def _record_micro_trade_event(self, attempt, fills, session_id: str, status: OrderStatus) -> None:
        order = attempt.order
        if not order:
            return

        fill_price = fills[-1].fill_price if fills else order.price
        if fill_price is None:
            return

        now = datetime.now(timezone.utc)
        source = fills[-1].source if fills else "broker"
        trade = TradeEventRecord(
            trade_id=f"micro-{order.symbol}-{now.strftime('%Y%m%dT%H%M%S%f')}",
            date=now.date().isoformat(),
            timestamp=now,
            symbol=order.symbol,
            action=order.side.value,
            price=fill_price,
            quantity=order.quantity,
            pnl=Decimal("0"),
            session_id=session_id,
            signal_id=order.signal_id,
            order_id=order.client_order_id,
            status=status.value,
            source=source,
            confidence=attempt.signal.confidence if attempt.signal else 0,
        )
        self._get_audit_repositories().pnl.put_trade_event(trade)

    def _log_micro_diagnostics(self, attempts) -> None:
        if not attempts or MICRO_DIAGNOSTIC_TOP_N <= 0:
            return

        if any(attempt.setup.action in {"BUY", "SELL"} for attempt in attempts):
            candidates = [
                attempt for attempt in attempts
                if attempt.setup.action in {"BUY", "SELL"} or attempt.executed
            ]
            title = "⚡ Micro actionable detail"
        else:
            candidates = sorted(attempts, key=self._micro_attempt_rank, reverse=True)
            title = "⚡ Micro nearest setups"

        print(title + ":")
        for attempt in candidates[:MICRO_DIAGNOSTIC_TOP_N]:
            setup = attempt.setup
            features = setup.features or {}
            reasons = "; ".join(setup.reasons[:3])
            if attempt.skipped_reason and attempt.skipped_reason not in reasons:
                reasons = f"{reasons}; skipped={attempt.skipped_reason}"
            print(
                "   "
                f"{setup.symbol}: {setup.action}/{setup.setup} conf={setup.confidence} "
                f"rv={_format_feature(features, 'relative_volume')} "
                f"rsi={_format_feature(features, 'rsi')} "
                f"atr={_format_feature(features, 'atr')} "
                f"close={_format_feature(features, 'close')} "
                f"vwap={_format_feature(features, 'vwap')} "
                f"trend={features.get('trend_bias', 'na')} "
                f"candle={features.get('latest_timestamp', 'na')} "
                f"source={features.get('latest_source', 'na')} "
                f"reason={reasons}"
            )

    @staticmethod
    def _micro_attempt_rank(attempt) -> tuple:
        setup = attempt.setup
        features = setup.features or {}
        relative_volume = _coerce_float(features.get("relative_volume"), 0.0)
        confidence = _coerce_int(setup.confidence, 0)
        trend_score = 1 if features.get("trend_bias") in {"bullish", "bearish"} else 0
        return (confidence, relative_volume, trend_score)
    
    def run(self):
        """Main bot loop."""
        print("\n🚀 Trading Bot Started")
        print("📅 Monitoring market hours: 9:15 AM - 3:30 PM IST")
        print(f"⏱️  Analysis interval: {ANALYSIS_INTERVAL} seconds")
        if self.micro_engine:
            print(f"⚡ Micro scan interval: {MICRO_SCAN_INTERVAL_SECONDS} seconds")
        print(f"📝 Paper Trading Mode: {self.paper_trading}")
        
        # Run overnight analysis first
        self._run_overnight_analysis()
        
        while self.running:
            try:
                if self._is_market_hours():
                    self.cycle_count += 1
                    if self.micro_engine:
                        self._record_heartbeat("micro_cycle_start")
                        self._run_micro_market_cycle()
                        self._record_heartbeat("micro_cycle_complete")
                        time.sleep(MICRO_SCAN_INTERVAL_SECONDS)
                    else:
                        self._record_heartbeat("market_cycle_start")
                        self._run_market_hours_cycle()
                        self._record_heartbeat("market_cycle_complete")
                        time.sleep(ANALYSIS_INTERVAL)
                else:
                    self._record_heartbeat("waiting_for_market")
                    time.sleep(3600)  # Check every hour outside market hours
            except KeyboardInterrupt:
                print("\n🛑 Bot stopped by user")
                self._square_off_all()
                break
            except Exception as e:
                print(f"❌ Error in main loop: {e}")
                self._record_heartbeat("runtime_error")
                time.sleep(60)

# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
