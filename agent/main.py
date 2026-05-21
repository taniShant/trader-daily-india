#!/usr/bin/env python3
"""
Multi-Agent Trading Orchestrator using Strands Agents-as-Tools pattern.
Deploys to Amazon Bedrock AgentCore.
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

# Strands imports
from strands import Agent, tool, AgentCoreMemory, Session
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

# ============================================================
# CONFIGURATION
# ============================================================

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "TradingSessionTable")

# Initialize Bedrock Model
model = BedrockModel(
    model_id=MODEL_ID,
    region_name=AWS_REGION,
    temperature=0.2,  # Lower temperature for more deterministic trading decisions
    max_tokens=4096,
)

# Initialize persistent memory using AgentCore
memory = AgentCoreMemory(
    table_name=SESSIONS_TABLE,
    session_ttl_seconds=2592000,  # 30 days
)

# ============================================================
# CREATE SPECIALIST AGENTS
# ============================================================

# Instantiate each specialist agent
technical_agent = TechnicalAnalyst(model=model, memory=memory)
sentiment_agent = SentimentAnalyst(model=model, memory=memory)
fundamental_agent = FundamentalAnalyst(model=model, memory=memory)
social_agent = SocialAnalyst(model=model, memory=memory)
derivatives_agent = DerivativesAnalyst(model=model, memory=memory)

# ============================================================
# WRAP SPECIALIST AGENTS AS TOOLS (Agents-as-Tools Pattern)
# ============================================================

@tool
def consult_technical_analyst(stock_symbol: str) -> Dict[str, Any]:
    """
    Consult the technical analyst agent for RSI, MACD, and chart patterns.
    """
    result = technical_agent(f"Analyze {stock_symbol} technicals for intraday trading")
    return json.loads(result) if isinstance(result, str) else result

@tool
def consult_sentiment_analyst(stock_symbol: str) -> Dict[str, Any]:
    """
    Consult the sentiment analyst agent for news and emotion analysis.
    Uses FinBERT and NRC Emotion Lexicon.
    """
    result = sentiment_agent(f"Analyze news sentiment for {stock_symbol}")
    return json.loads(result) if isinstance(result, str) else result

@tool
def consult_fundamental_analyst(stock_symbol: str) -> Dict[str, Any]:
    """
    Consult the fundamentals analyst agent for P/E, market cap, and growth.
    """
    result = fundamental_agent(f"Get fundamentals for {stock_symbol}")
    return json.loads(result) if isinstance(result, str) else result

@tool
def consult_social_analyst(stock_symbol: str) -> Dict[str, Any]:
    """
    Consult the social sentiment analyst for Reddit/Twitter sentiment.
    """
    result = social_agent(f"Get social sentiment for {stock_symbol}")
    return json.loads(result) if isinstance(result, str) else result

@tool
def consult_derivatives_analyst(stock_symbol: str) -> Dict[str, Any]:
    """
    Consult the derivatives analyst for options chain and implied volatility.
    """
    result = derivatives_agent(f"Analyze option chain for {stock_symbol}")
    return json.loads(result) if isinstance(result, str) else result

# ============================================================
# ORCHESTRATOR AGENT (The Coordinator)
# ============================================================

orchestrator = Agent(
    name="TradingOrchestrator",
    model=model,
    memory=memory,
    session_id="trading_session",  # Persistent session across runs
    tools=[
        consult_technical_analyst,
        consult_sentiment_analyst,
        consult_fundamental_analyst,
        consult_social_analyst,
        consult_derivatives_analyst,
        get_live_quote,
        get_historical_data,
        get_trade_history,
    ],
    system_prompt="""
    You are a senior trading strategist for the Indian stock market.
    
    Your job is to analyze a given stock and provide a final intraday trading recommendation.
    
    FOR EACH STOCK, YOU MUST:
    1. Call ALL specialist analysts (technical, sentiment, fundamental, social, derivatives)
    2. Synthesize their findings into a unified view
    3. Consider recent trade history from get_trade_history
    4. Provide a final recommendation with:
       - Action: BUY, SELL, or HOLD
       - Confidence score (0-100)
       - Entry price (within 2% of current price)
       - Stop loss price (2-3% below entry for BUY)
       - Target price (based on technical resistance)
       - Reasoning summary
    
    RISK MANAGEMENT RULES:
    - Never recommend more than 3 trades per day
    - Maximum position size: 10% of capital per trade
    - Maximum daily loss: 4% of total capital
    
    Be decisive but conservative. When uncertain, prefer HOLD over trading.
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
    action: str  # BUY, SELL, HOLD
    confidence: int
    entry_price: float
    stop_loss: float
    target_price: float
    reasoning: str
    technical_summary: str
    sentiment_score: float
    risk_level: str  # LOW, MEDIUM, HIGH

# ============================================================
# MAIN EXECUTION FUNCTION
# ============================================================

def analyze_stock(stock_symbol: str) -> TradingSignal:
    """
    Run the multi-agent analysis for a single stock.
    """
    print(f"\n{'='*60}")
    print(f"🤖 Analyzing {stock_symbol} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    # Prompt the orchestrator
    prompt = f"""
    Analyze {stock_symbol} for intraday trading.
    Consult all specialist analysts and provide a final recommendation.
    Consider the current market context and risk management rules.
    """
    
    result = orchestrator(prompt)
    
    # Parse the result into TradingSignal
    if isinstance(result, str):
        try:
            result_dict = json.loads(result)
        except json.JSONDecodeError:
            # Fallback for plain text response
            result_dict = {"action": "HOLD", "reasoning": result[:500]}
    else:
        result_dict = result
    
    # Create structured signal
    signal = TradingSignal(
        date=datetime.now().strftime("%Y-%m-%d"),
        stock_symbol=stock_symbol,
        action=result_dict.get("action", "HOLD"),
        confidence=result_dict.get("confidence", 50),
        entry_price=result_dict.get("entry_price", 0.0),
        stop_loss=result_dict.get("stop_loss", 0.0),
        target_price=result_dict.get("target_price", 0.0),
        reasoning=result_dict.get("reasoning", ""),
        technical_summary=result_dict.get("technical_summary", ""),
        sentiment_score=result_dict.get("sentiment_score", 0.0),
        risk_level=result_dict.get("risk_level", "MEDIUM"),
    )
    
    # Save to database
    save_trade_signal(signal)
    
    return signal

def run_daily_analysis(watchlist: List[str]) -> List[TradingSignal]:
    """
    Run analysis for all stocks in the watchlist.
    Returns list of trading signals.
    """
    results = []
    for stock in watchlist:
        try:
            signal = analyze_stock(stock)
            results.append(signal)
            print(f"✅ {stock}: {signal.action} (Confidence: {signal.confidence}%)")
        except Exception as e:
            print(f"❌ Error analyzing {stock}: {e}")
    
    return results

# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    # NIFTY 50 liquid stocks for intraday trading
    WATCHLIST = [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
        "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE", "ITC"
    ]
    
    # Run analysis
    signals = run_daily_analysis(WATCHLIST)
    
    # Print summary
    print("\n" + "="*60)
    print("📊 DAILY TRADING SUMMARY")
    print("="*60)
    for signal in signals:
        if signal.action != "HOLD":
            print(f"🔔 {signal.action} {signal.stock_symbol} @ ₹{signal.entry_price}")
            print(f"   Stop: ₹{signal.stop_loss} | Target: ₹{signal.target_price}")
            print(f"   Confidence: {signal.confidence}% | Risk: {signal.risk_level}\n")