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
from datetime import datetime, time as dt_time
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
from .storage import build_bot_heartbeat, market_state_repository
from .time import MarketClock

# ============================================================
# CONFIGURATION FROM ENVIRONMENT VARIABLES
# ============================================================

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
WATCHLIST_SIZE = settings.trading.watchlist_size

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
print(f"   Oracle Static IP: {ORACLE_STATIC_IP}")

models = {}
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


def get_model(task_type: str = "default"):
    """Initialize Bedrock models lazily by task type so imports stay offline/testable."""
    model_id = MODEL_IDS_BY_TASK.get(task_type, MODEL_ID)
    if task_type not in models:
        from strands.models import BedrockModel
        from .bedrock_session import build_bedrock_boto_session

        boto_session = build_bedrock_boto_session()
        model_kwargs = {
            "model_id": model_id,
            "temperature": 0.2,
            "max_tokens": 4096,
        }
        if boto_session is None:
            model_kwargs["region_name"] = AWS_REGION
        else:
            model_kwargs["boto_session"] = boto_session

        models[task_type] = BedrockModel(**model_kwargs)
    return models[task_type]


def get_specialist_agents():
    """Initialize specialist agents lazily."""
    global technical_agent, sentiment_agent, fundamental_agent, social_agent, derivatives_agent

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

# ============================================================
# ORCHESTRATOR AGENT 
# ============================================================

def get_orchestrator():
    """Initialize the orchestrator lazily."""
    global orchestrator
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

# ============================================================
# TRADING BOT CLASS (Continuous Market Hours)
# ============================================================

class TradingBot:
    """Continuous trading bot that runs throughout market hours."""
    
    def __init__(self):
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
        self.current_sentiment = 0.0
        self.temp_caution_mode = False
        self.running = True
        self.bot_id = os.environ.get("BOT_ID", "trading-bot")
        self.cycle_count = 0
        self._market_state_repository = None
        self.market_clock = MarketClock()
        self.risk_manager = self._build_risk_manager()
        self.broker = get_broker(paper_trading=self.paper_trading)
        self.position_monitor = PositionMonitor()
        
        # Initialize modules
        self.news_aggregator = NewsAggregator()
        self.global_macro = GlobalMacroCollector()
        self.pre_market_scanner = PreMarketScanner()
        self.pattern_analyzer = PatternAnalyzer()
        self.confidence_adjuster = ConfidenceAdjuster()
        
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
        print(f"Watchlist Size: {WATCHLIST_SIZE}")
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
                self.watchlist = [
                    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
                    "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE", "MARUTI", "ITC"
                ][:WATCHLIST_SIZE]
            print(f"📋 Watchlist ({len(self.watchlist)} stocks): {', '.join(self.watchlist)}")
        except Exception as e:
            print(f"Error loading watchlist: {e}")
            self.watchlist = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "MARUTI"][:WATCHLIST_SIZE]
    
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
        return min(quantity, 50)

    def _build_risk_manager(self) -> RiskManager:
        return RiskManager(
            RiskLimits(
                capital=Decimal(str(self.capital)),
                max_daily_loss_percent=Decimal(str(MAX_DAILY_LOSS_PERCENT)),
                max_position_size_percent=Decimal(str(MAX_POSITION_SIZE_PERCENT)),
                min_confidence=self.min_confidence,
                max_quantity_per_order=50,
            )
        )

    def _get_market_state_repository(self):
        if self._market_state_repository is None:
            self._market_state_repository = market_state_repository()
        return self._market_state_repository

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
        return ContractTradeSignal(
            signal_id=f"{signal.stock_symbol}-{signal.date}-{action}",
            symbol=signal.stock_symbol,
            action=action,
            confidence=signal.confidence,
            generated_at=datetime.utcnow(),
            entry_price=Decimal(str(signal.entry_price)),
            stop_loss=Decimal(str(signal.stop_loss)),
            target_price=Decimal(str(signal.target_price)),
            holding_window_minutes=30,
            risk_level=risk_level,
            sentiment_score=signal.sentiment_score,
            reasons=[signal.reasoning] if signal.reasoning else [],
            raw_features={
                "technical_summary": signal.technical_summary,
                "legacy_signal": asdict(signal),
            },
        )
    
    def _analyze_stock(self, stock_symbol: str) -> Optional[TradingSignal]:
        """Run multi-agent analysis for a single stock."""
        print(f"\n📊 Analyzing {stock_symbol}...")
        
        prompt = f"""
        Analyze {stock_symbol} for intraday trading.
        Current market sentiment: {self.current_sentiment}
        Call all specialist analysts, get live quote, and provide a final recommendation in JSON format.
        """
        
        try:
            result = get_orchestrator()(prompt)
            
            if isinstance(result, str):
                import re
                json_match = re.search(r'\{[^{}]*\}', result)
                if json_match:
                    result_dict = json.loads(json_match.group())
                else:
                    result_dict = {"action": "HOLD", "reasoning": result[:200]}
            else:
                result_dict = result
            
            # Adjust confidence based on learned patterns
            adjusted_confidence = self._adjust_confidence(result_dict.get("confidence", 50))
            
            return TradingSignal(
                date=datetime.now().strftime("%Y-%m-%d"),
                stock_symbol=stock_symbol,
                action=result_dict.get("action", "HOLD"),
                confidence=min(100, max(0, adjusted_confidence)),
                entry_price=float(result_dict.get("entry_price", 0.0)),
                stop_loss=float(result_dict.get("stop_loss", 0.0)),
                target_price=float(result_dict.get("target_price", 0.0)),
                reasoning=result_dict.get("reasoning", "")[:300],
                technical_summary=result_dict.get("technical_summary", "")[:200],
                sentiment_score=float(result_dict.get("sentiment_score", 0.0)),
                risk_level=result_dict.get("risk_level", "MEDIUM")
            )
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return None
    
    def _adjust_confidence(self, base_confidence: int) -> int:
        """Adjust confidence based on current market conditions."""
        adjusted = base_confidence
        
        # Adjust based on news sentiment
        if self.current_sentiment > 0.5:
            adjusted += 5
        elif self.current_sentiment < -0.3:
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

        # Analyze stocks in watchlist
        for stock in self.watchlist:
            signal = self._analyze_stock(stock)
            if signal:
                self._execute_signal(signal)
            time.sleep(1)
        
        self._monitor_positions()
    
    def run(self):
        """Main bot loop."""
        print("\n🚀 Trading Bot Started")
        print("📅 Monitoring market hours: 9:15 AM - 3:30 PM IST")
        print(f"⏱️  Analysis interval: {ANALYSIS_INTERVAL} seconds")
        print(f"📝 Paper Trading Mode: {self.paper_trading}")
        
        # Run overnight analysis first
        self._run_overnight_analysis()
        
        while self.running:
            try:
                if self._is_market_hours():
                    self.cycle_count += 1
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
