"""
Complete MCP Server integration with Strands Agent
For ECS Fargate deployment with environment-based configuration.
"""

import asyncio
import os
from typing import Dict, Any, Optional

from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters

# ============================================================
# CONFIGURATION FROM ENVIRONMENT
# ============================================================

AWS_REGION = os.environ.get("AWS_REGION", "eu-west-2")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "svc-trd-sessions-dev")
TRADES_TABLE = os.environ.get("TRADES_TABLE", "svc-trd-trades-dev")
PAPER_TRADING = os.environ.get("PAPER_TRADING", "true").lower() == "true"
STATIC_IP = os.environ.get("STATIC_IP", "3.8.245.57")
MIN_CONFIDENCE = int(os.environ.get("MIN_CONFIDENCE_THRESHOLD", 70))

# Initialize model
model = BedrockModel(
    model_id=MODEL_ID,
    region_name=AWS_REGION,
    temperature=0.2,
    max_tokens=4096,
)

# Note: AgentCoreMemory may not be available in all environments
# For ECS, we use DynamoDB directly in the main bot
# memory = AgentCoreMemory(...) - Commented out for ECS compatibility

print(f"📋 MCP Integration Configuration:")
print(f"   Region: {AWS_REGION}")
print(f"   Model: {MODEL_ID}")
print(f"   Sessions Table: {SESSIONS_TABLE}")
print(f"   Trades Table: {TRADES_TABLE}")
print(f"   Paper Trading: {PAPER_TRADING}")
print(f"   Static IP: {STATIC_IP}")

# ============================================================
# MCP SERVER PATHS (Relative to project root)
# ============================================================

# MCP Server 1: Market Data
MARKET_DATA_SERVER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 
    "mcp-servers/market_data_server.py"
)

# MCP Server 2: News Sentiment
NEWS_SENTIMENT_SERVER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 
    "mcp-servers/news_sentiment_server.py"
)

# MCP Server 3: Trading Execution (optional)
TRADING_EXECUTION_SERVER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 
    "mcp-servers/trading_execution_server.py"
)

async def create_trading_agent_with_mcp(
    include_execution: bool = False
) -> Agent:
    """
    Create a trading agent connected to multiple MCP servers.
    
    Args:
        include_execution: Whether to include trading execution MCP server
        
    Returns:
        Configured Strands Agent with MCP tools
    """
    
    # Prepare MCP server parameters
    server_params = [
        StdioServerParameters(
            command="python",
            args=[MARKET_DATA_SERVER_PATH]
        ),
        StdioServerParameters(
            command="python",
            args=[NEWS_SENTIMENT_SERVER_PATH]
        )
    ]
    
    if include_execution:
        server_params.append(
            StdioServerParameters(
                command="python",
                args=[TRADING_EXECUTION_SERVER_PATH]
            )
        )
    
    # Create MCP clients
    mcp_clients = [
        MCPClient(lambda params=sp: stdio_client(params)) 
        for sp in server_params
    ]
    
    # Import specialist agents (no memory for ECS)
    from specialists.technical import TechnicalAnalyst
    from specialists.fundamentals import FundamentalAnalyst
    from specialists.derivatives import DerivativesAnalyst
    from specialists.sentiment import SentimentAnalyst
    from specialists.social import SocialAnalyst
    
    # Create specialist agents (without memory for ECS compatibility)
    technical_agent = TechnicalAnalyst(model=model)
    fundamental_agent = FundamentalAnalyst(model=model)
    derivatives_agent = DerivativesAnalyst(model=model)
    sentiment_agent = SentimentAnalyst(model=model)
    social_agent = SocialAnalyst(model=model)
    
    # Wrap specialist agents as tools (will be added to orchestrator separately)
    
    # Collect all MCP tools
    all_tools = []
    
    # Connect to all MCP servers and collect tools
    with mcp_clients[0], mcp_clients[1]:
        # Get tools from market data server
        mcp_tools_1 = mcp_clients[0].list_tools_sync()
        all_tools.extend(mcp_tools_1)
        
        # Get tools from news sentiment server
        mcp_tools_2 = mcp_clients[1].list_tools_sync()
        all_tools.extend(mcp_tools_2)
        
        # Optionally include execution server
        if include_execution and len(mcp_clients) > 2:
            with mcp_clients[2]:
                mcp_tools_3 = mcp_clients[2].list_tools_sync()
                all_tools.extend(mcp_tools_3)
        
        # Create orchestrator with all tools
        orchestrator = Agent(
            name="TradingOrchestrator",
            model=model,
            # No memory parameter for ECS - use DynamoDB directly in main bot
            tools=all_tools,
            system_prompt=f"""
            You are a senior trading strategist for the Indian stock market.
            
            STATIC IP: {STATIC_IP} (NAT Gateway - traffic appears from this IP)
            PAPER TRADING MODE: {PAPER_TRADING}
            
            You have access to:
            1. Market Data Tools (live quotes, historical data, technical indicators)
            2. News Sentiment Tools (FinBERT sentiment analysis)
            {"3. Trading Execution Tools (order placement, position management)" if include_execution else ""}
            
            Your job: Analyze stocks and provide intraday trading recommendations.
            
            Provide recommendations in JSON format with:
            - action: "BUY", "SELL", or "HOLD"
            - confidence: number (0-100) - must be at least {MIN_CONFIDENCE} to act
            - entry_price: number
            - stop_loss: number (2-3% below entry)
            - target_price: number
            - reasoning: string
            - risk_level: "LOW", "MEDIUM", or "HIGH"
            
            Always consult multiple data sources before making a decision.
            When uncertain, prefer HOLD over trading.
            """
        )
        
        return orchestrator

async def analyze_stock_with_mcp(
    stock_symbol: str, 
    include_execution: bool = False
) -> Dict[str, Any]:
    """
    Analyze a single stock using MCP-connected agent.
    
    Args:
        stock_symbol: Stock symbol (e.g., RELIANCE)
        include_execution: Whether to include execution tools
        
    Returns:
        Trading recommendation as dictionary
    """
    orchestrator = await create_trading_agent_with_mcp(include_execution)
    
    prompt = f"""
    Analyze {stock_symbol} for intraday trading.
    
    Required steps:
    1. Get live quote using market data tools
    2. Get technical indicators (RSI, MACD)
    3. Get news sentiment for {stock_symbol}
    4. Provide final BUY/SELL/HOLD recommendation
    
    Output format: JSON with fields: action, confidence, entry_price, 
    stop_loss, target_price, reasoning, risk_level
    """
    
    result = orchestrator(prompt)
    
    # Parse result
    if isinstance(result, str):
        try:
            import json
            import re
            json_match = re.search(r'\{[^{}]*\}', result)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
    
    return result if isinstance(result, dict) else {"action": "HOLD", "reasoning": str(result)[:500]}

def run_trading_analysis(
    stock_symbol: str, 
    include_execution: bool = False
) -> Dict[str, Any]:
    """
    Run analysis using MCP-connected agent (synchronous wrapper).
    
    Args:
        stock_symbol: Stock symbol to analyze
        include_execution: Whether to include execution tools
        
    Returns:
        Trading recommendation
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(
            analyze_stock_with_mcp(stock_symbol, include_execution)
        )
        return result
    finally:
        loop.close()

def analyze_multiple_stocks(
    watchlist: list,
    include_execution: bool = False
) -> list:
    """
    Analyze multiple stocks and return recommendations.
    
    Args:
        watchlist: List of stock symbols
        include_execution: Whether to include execution tools
        
    Returns:
        List of trading recommendations
    """
    results = []
    for stock in watchlist:
        try:
            result = run_trading_analysis(stock, include_execution)
            results.append({
                "stock": stock,
                "recommendation": result,
                "timestamp": __import__('datetime').datetime.utcnow().isoformat()
            })
            print(f"✅ Analyzed {stock}: {result.get('action', 'UNKNOWN')}")
        except Exception as e:
            print(f"❌ Error analyzing {stock}: {e}")
            results.append({
                "stock": stock,
                "recommendation": {"action": "ERROR", "error": str(e)},
                "timestamp": __import__('datetime').datetime.utcnow().isoformat()
            })
    return results

# ============================================================
# ENTRY POINT (for testing)
# ============================================================

if __name__ == "__main__":
    # Test single stock analysis
    result = run_trading_analysis("RELIANCE")
    print("\n" + "="*60)
    print("📊 TRADING RECOMMENDATION")
    print("="*60)
    print(result)
    
    # Test multiple stocks
    watchlist = ["RELIANCE", "TCS", "HDFCBANK"]
    results = analyze_multiple_stocks(watchlist)
    print("\n" + "="*60)
    print("📊 MULTI-STOCK ANALYSIS")
    print("="*60)
    for r in results:
        print(f"{r['stock']}: {r['recommendation'].get('action', 'UNKNOWN')}")