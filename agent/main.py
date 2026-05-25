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
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

# Strands imports
from strands import Agent, tool
from strands.models import BedrockModel

# Import specialist agent modules
from specialists.technical import TechnicalAnalyst
from specialists.sentiment import SentimentAnalyst
from specialists.fundamentals import FundamentalAnalyst
from specialists.social import SocialAnalyst
from specialists.derivatives import DerivativesAnalyst

# Import shared tools
from tools.market_data import get_live_quote, get_historical_data
from tools.order_execution import place_order, get_positions
from tools.database import save_trade_signal, get_trade_history

# Import overnight modules
from overnight.news_aggregator import NewsAggregator
from overnight.global_macro import GlobalMacroCollector
from overnight.pre_market_scanner import PreMarketScanner
from learning.pattern_analyzer import PatternAnalyzer
from learning.confidence_adjuster import ConfidenceAdjuster

# ============================================================
# CONFIGURATION FROM ENVIRONMENT VARIABLES
# ============================================================

AWS_REGION = os.environ.get("AWS_REGION", "eu-west-2")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "svc-trd-sessions-dev")
TRADES_TABLE = os.environ.get("TRADES_TABLE", "svc-trd-trades-dev")
LEARNING_TABLE = os.environ.get("LEARNING_TABLE", "svc-trd-learning-dev")
MARKET_STATE_TABLE = os.environ.get("MARKET_STATE_TABLE", "svc-trd-market-state-dev")

# Trading parameters
PAPER_TRADING = os.environ.get("PAPER_TRADING", "true").lower() == "true"
CAPITAL = float(os.environ.get("CAPITAL", 100000))
ANALYSIS_INTERVAL = int(os.environ.get("ANALYSIS_INTERVAL_SECONDS", 180))
MIN_CONFIDENCE = int(os.environ.get("MIN_CONFIDENCE_THRESHOLD", 70))
MAX_DAILY_LOSS_PERCENT = float(os.environ.get("MAX_DAILY_LOSS_PERCENT", 4))
MAX_POSITION_SIZE_PERCENT = float(os.environ.get("MAX_POSITION_SIZE_PERCENT", 10))
WATCHLIST_SIZE = int(os.environ.get("WATCHLIST_SIZE", 10))

# Static IP (for reference/logging)
STATIC_IP = os.environ.get("STATIC_IP", "3.8.245.57")

print(f"📋 Trading Bot Configuration:")
print(f"   Region: {AWS_REGION}")
print(f"   Model: {MODEL_ID}")
print(f"   Paper Trading: {PAPER_TRADING}")
print(f"   Capital: ₹{CAPITAL:,.2f}")
print(f"   Analysis Interval: {ANALYSIS_INTERVAL} seconds")
print(f"   Min Confidence: {MIN_CONFIDENCE}%")
print(f"   Max Daily Loss: {MAX_DAILY_LOSS_PERCENT}%")
print(f"   Max Position Size: {MAX_POSITION_SIZE_PERCENT}%")
print(f"   Static IP: {STATIC_IP}")

# Initialize Bedrock Model
model = BedrockModel(
    model_id=MODEL_ID,
    region_name=AWS_REGION,
    temperature=0.2,
    max_tokens=4096,
)

# ============================================================
# CREATE SPECIALIST AGENTS (without memory for ECS)
# ============================================================

technical_agent = TechnicalAnalyst(model=model)
sentiment_agent = SentimentAnalyst(model=model)
fundamental_agent = FundamentalAnalyst(model=model)
social_agent = SocialAnalyst(model=model)
derivatives_agent = DerivativesAnalyst(model=model)

# ============================================================
# WRAP SPECIALIST AGENTS AS TOOLS
# ============================================================

@tool
def consult_technical_analyst(stock_symbol: str) -> Dict[str, Any]:
    """Consult the technical analyst agent for RSI, MACD, and chart patterns."""
    result = technical_agent(f"Analyze {stock_symbol} technicals for intraday trading")
    return result if isinstance(result, dict) else {"analysis": str(result)[:500]}

@tool
def consult_sentiment_analyst(stock_symbol: str) -> Dict[str, Any]:
    """Consult the sentiment analyst agent for news and emotion analysis."""
    result = sentiment_agent(f"Analyze news sentiment for {stock_symbol}")
    return result if isinstance(result, dict) else {"analysis": str(result)[:500]}

@tool
def consult_fundamental_analyst(stock_symbol: str) -> Dict[str, Any]:
    """Consult the fundamentals analyst agent for P/E, market cap, and growth."""
    result = fundamental_agent(f"Get fundamentals for {stock_symbol}")
    return result if isinstance(result, dict) else {"analysis": str(result)[:500]}

@tool
def consult_social_analyst(stock_symbol: str) -> Dict[str, Any]:
    """Consult the social sentiment analyst for Reddit/Twitter sentiment."""
    result = social_agent(f"Get social sentiment for {stock_symbol}")
    return result if isinstance(result, dict) else {"analysis": str(result)[:500]}

@tool
def consult_derivatives_analyst(stock_symbol: str) -> Dict[str, Any]:
    """Consult the derivatives analyst for options chain and implied volatility."""
    result = derivatives_agent(f"Analyze option chain for {stock_symbol}")
    return result if isinstance(result, dict) else {"analysis": str(result)[:500]}

# ============================================================
# ORCHESTRATOR AGENT 
# ============================================================

orchestrator = Agent(
    name="TradingOrchestrator",
    model=model,
    tools=[
        consult_technical_analyst,
        consult_sentiment_analyst,
        consult_fundamental_analyst,
        consult_social_analyst,
        consult_derivatives_analyst,
        get_live_quote,
        get_historical_data,
    ],
    system_prompt=f"""
    You are a senior trading strategist for the Indian stock market.
    
    STATIC IP: {STATIC_IP} (NAT Gateway - traffic appears from this IP)
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
    """
)

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
        
        # Initialize modules
        self.news_aggregator = NewsAggregator()
        self.global_macro = GlobalMacroCollector()
        self.pre_market_scanner = PreMarketScanner()
        self.pattern_analyzer = PatternAnalyzer()
        self.confidence_adjuster = ConfidenceAdjuster()
        
        self._setup_signal_handlers()
        self._update_watchlist()
        self._print_config()
    
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
        print(f"Static IP (NAT): {STATIC_IP}")
        print(f"Paper Trading: {self.paper_trading}")
        print(f"Capital: ₹{self.capital:,.2f}")
        print(f"Min Confidence: {self.min_confidence}%")
        print(f"Max Daily Loss: ₹{self.max_daily_loss:,.2f} ({MAX_DAILY_LOSS_PERCENT}%)")
        print(f"Max Position Size: ₹{self.max_position_size:,.2f} ({MAX_POSITION_SIZE_PERCENT}%)")
        print(f"Watchlist Size: {WATCHLIST_SIZE}")
        print(f"Analysis Interval: {ANALYSIS_INTERVAL} seconds")
        print(f"Bedrock Model: {MODEL_ID}")
        print("=" * 60)
    
    def _update_watchlist(self):
        """Update watchlist from pre-market scanner or use default."""
        try:
            self.watchlist = self.pre_market_scanner.get_watchlist()
            if not self.watchlist:
                self.watchlist = [
                    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
                    "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE", "ITC"
                ][:WATCHLIST_SIZE]
            print(f"📋 Watchlist ({len(self.watchlist)} stocks): {', '.join(self.watchlist)}")
        except Exception as e:
            print(f"Error loading watchlist: {e}")
            self.watchlist = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"][:WATCHLIST_SIZE]
    
    def _is_market_hours(self) -> bool:
        """Check if market is open (9:15 AM - 3:30 PM IST)."""
        now_utc = datetime.utcnow()
        market_open_utc = now_utc.replace(hour=3, minute=45)   # 9:15 AM IST
        market_close_utc = now_utc.replace(hour=10, minute=0)  # 3:30 PM IST
        return market_open_utc <= now_utc <= market_close_utc
    
    def _should_square_off(self) -> bool:
        """Check if nearing market close (square off by 3:20 PM IST)."""
        now_utc = datetime.utcnow()
        square_off_time_utc = now_utc.replace(hour=9, minute=50)  # 3:20 PM IST
        return now_utc >= square_off_time_utc
    
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
    
    def _analyze_stock(self, stock_symbol: str) -> Optional[TradingSignal]:
        """Run multi-agent analysis for a single stock."""
        print(f"\n📊 Analyzing {stock_symbol}...")
        
        prompt = f"""
        Analyze {stock_symbol} for intraday trading.
        Current market sentiment: {self.current_sentiment}
        Call all specialist analysts, get live quote, and provide a final recommendation in JSON format.
        """
        
        try:
            result = orchestrator(prompt)
            
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
        if signal.action == "HOLD":
            return
        
        if signal.confidence < self.min_confidence:
            print(f"   ⏭️ Skipping {signal.action} {signal.stock_symbol} - confidence {signal.confidence}% < {self.min_confidence}%")
            return
        
        if signal.risk_level == "HIGH":
            print(f"   ⏭️ Skipping {signal.action} {signal.stock_symbol} - risk level HIGH")
            return
        
        quantity = self._calculate_position_size(signal.entry_price, signal.confidence)
        
        if quantity == 0:
            print(f"   ⏭️ Skipping {signal.action} {signal.stock_symbol} - quantity zero")
            return
        
        print(f"\n🔔 EXECUTING: {signal.action} {signal.stock_symbol}")
        print(f"   Entry: ₹{signal.entry_price} | Stop: ₹{signal.stop_loss} | Target: ₹{signal.target_price}")
        print(f"   Quantity: {quantity} | Confidence: {signal.confidence}%")
        print(f"   Reasoning: {signal.reasoning[:100]}...")
        
        if self.paper_trading:
            print(f"   📝 [PAPER TRADE] Would have placed order")
            save_trade_signal(signal)
        else:
            try:
                result = place_order(
                    stock_code=signal.stock_symbol,
                    action=signal.action.lower(),
                    quantity=quantity,
                    price=signal.entry_price,
                    stoploss=signal.stop_loss
                )
                if result.get("success"):
                    print(f"   ✅ Order placed: {result.get('order_id')}")
                    self.active_positions[signal.stock_symbol] = {
                        "quantity": quantity,
                        "entry_price": signal.entry_price,
                        "stop_loss": signal.stop_loss,
                        "target": signal.target_price,
                        "order_id": result.get("order_id")
                    }
                    save_trade_signal(signal)
                else:
                    print(f"   ❌ Order failed: {result.get('error')}")
            except Exception as e:
                print(f"   ❌ Order error: {e}")
    
    def _monitor_positions(self):
        """Monitor open positions for stop-loss or target hits."""
        # In production, implement price checking and auto-square-off
        pass
    
    def _square_off_all(self):
        """Close all open positions."""
        if not self.active_positions:
            return
        
        print("\n🔒 Squaring off all positions...")
        for symbol, position in self.active_positions.items():
            if self.paper_trading:
                print(f"   📝 [PAPER] Would have squared off {symbol}")
            else:
                try:
                    result = place_order(
                        stock_code=symbol,
                        action="sell",
                        quantity=position["quantity"],
                        order_type="market"
                    )
                    if result.get("success"):
                        print(f"   ✅ Squared off {symbol}")
                    else:
                        print(f"   ❌ Failed to square off {symbol}: {result.get('error')}")
                except Exception as e:
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
                    self._run_market_hours_cycle()
                    time.sleep(ANALYSIS_INTERVAL)
                else:
                    time.sleep(3600)  # Check every hour outside market hours
            except KeyboardInterrupt:
                print("\n🛑 Bot stopped by user")
                self._square_off_all()
                break
            except Exception as e:
                print(f"❌ Error in main loop: {e}")
                time.sleep(60)

# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    bot = TradingBot()
    bot.run()