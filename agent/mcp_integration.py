"""
Complete MCP Server integration with Strands Agent
"""

import asyncio
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters
from strands import AgentCoreMemory

# Environment setup
import os
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"

# Initialize model
model = BedrockModel(
    model_id=MODEL_ID,
    region_name=AWS_REGION
)

# Initialize persistent memory
memory = AgentCoreMemory(
    table_name=os.environ.get("SESSIONS_TABLE", "TradingSessionTable"),
    session_ttl_seconds=2592000  # 30 days
)

async def create_trading_agent_with_mcp():
    """
    Create a trading agent connected to multiple MCP servers.
    This follows the pattern from the AWS telecom mediation example [citation:10]
    """
    
    # MCP Server 1: Market Data
    market_data_client = MCPClient(
        lambda: stdio_client(StdioServerParameters(
            command="python",
            args=["mcp_servers/market_data_server.py"]
        ))
    )
    
    # MCP Server 2: News Sentiment
    news_sentiment_client = MCPClient(
        lambda: stdio_client(StdioServerParameters(
            command="python",
            args=["mcp_servers/news_sentiment_server.py"]
        ))
    )
    
    # Import specialist agents
    from specialists.technical import TechnicalAnalyst
    from specialists.fundamentals import FundamentalAnalyst
    from specialists.derivatives import DerivativesAnalyst
    from specialists.sentiment import SentimentAnalyst
    
    # Create specialist agents
    technical_agent = TechnicalAnalyst(model=model, memory=memory)
    fundamental_agent = FundamentalAnalyst(model=model, memory=memory)
    derivatives_agent = DerivativesAnalyst(model=model, memory=memory)
    sentiment_agent = SentimentAnalyst(model=model, memory=memory)
    
    # Connect to MCP servers and list tools
    with market_data_client, news_sentiment_client:
        # Fetch all tools from MCP servers
        mcp_tools = []
        mcp_tools.extend(market_data_client.list_tools_sync())
        mcp_tools.extend(news_sentiment_client.list_tools_sync())
        
        # Create orchestrator with all tools
        orchestrator = Agent(
            name="TradingOrchestrator",
            model=model,
            memory=memory,
            session_id="trading_mcp_session",
            tools=mcp_tools,  # MCP tools available directly
            system_prompt="""
            You are a senior trading strategist with access to:
            1. Market Data Tools (live quotes, historical data, technical indicators)
            2. News Sentiment Tools (FinBERT sentiment analysis)
            3. Specialist Agents (technical, fundamental, derivatives analysis)
            
            Your job: Analyze stocks and provide intraday trading recommendations.
            Always consult multiple data sources before making a decision.
            """
        )
        
        return orchestrator

def run_trading_analysis(stock_symbol: str):
    """Run analysis using MCP-connected agent"""
    
    # Create event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Create agent
    agent = loop.run_until_complete(create_trading_agent_with_mcp())
    
    # Run analysis
    prompt = f"""
    Analyze {stock_symbol} for intraday trading. Use:
    1. Market data tools to get live quote and technical indicators
    2. News sentiment tools to analyze recent news
    3. Provide a final BUY/SELL/HOLD recommendation
    
    Include: confidence score, entry price, stop loss, target price
    """
    
    result = agent(prompt)
    return result

if __name__ == "__main__":
    result = run_trading_analysis("RELIANCE")
    print(result)