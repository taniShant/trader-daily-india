"""
Complete Trading Agent with MCP Server Connection
Connects to both market data and trade execution MCP servers
"""

import asyncio
import os
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters
from agent.config import settings

# Initialize model
model = BedrockModel(
    model_id=settings.bedrock.reasoning_model_id,
    region_name=settings.bedrock.region,
)

async def create_trading_agent():
    """Create trading agent connected to execution MCP server"""
    
    # MCP Server for Trade Execution (ICICI Direct)
    execution_client = MCPClient(
        lambda: stdio_client(StdioServerParameters(
            command="python",
            args=["mcp_servers/trading_execution_server.py"],
            env={
                "ICICI_API_KEY": os.environ.get("ICICI_API_KEY", ""),
                "ICICI_SECRET_KEY": os.environ.get("ICICI_SECRET_KEY", ""),
                "ICICI_SESSION_TOKEN": os.environ.get("ICICI_SESSION_TOKEN", "")
            }
        ))
    )
    
    # MCP Server for Market Data
    market_data_client = MCPClient(
        lambda: stdio_client(StdioServerParameters(
            command="python",
            args=["mcp_servers/market_data_server.py"]
        ))
    )
    
    with execution_client, market_data_client:
        # Get all tools from both MCP servers
        execution_tools = execution_client.list_tools_sync()
        market_tools = market_data_client.list_tools_sync()
        all_tools = execution_tools + market_tools
        
        # Create the orchestrator agent
        orchestrator = Agent(
            name="TradingOrchestrator",
            model=model,
            tools=all_tools,
            system_prompt="""
            You are a senior trading strategist with live execution capabilities.
            
            Available tools:
            - get_live_quote: Check current stock price
            - place_intraday_order: Execute trades
            - get_positions: Check open positions
            - square_off_position: Close positions
            - get_portfolio_holdings: View portfolio
            
            Your workflow for each stock:
            1. Check live quote using get_live_quote
            2. Analyze technicals and sentiment
            3. If confident (70%+), place intraday order
            4. Set stoploss at 2-3% below entry
            5. Track position and suggest square-off time
            
            Output structured trading decision with order details.
            """
        )
        
        return orchestrator

def run_trading(stock_symbol: str, action: str, quantity: int = 10):
    """Execute a trading decision"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    agent = loop.run_until_complete(create_trading_agent())
    
    prompt = f"""
    Execute the following trade:
    - Stock: {stock_symbol}
    - Action: {action}
    - Quantity: {quantity}
    
    Before executing:
    1. Verify live price using get_live_quote
    2. Set appropriate limit price (within 0.5% of current price)
    3. Place order using place_intraday_order
    4. Return order confirmation
    """
    
    result = agent(prompt)
    return result

if __name__ == "__main__":
    # Example: Place a buy order for RELIANCE
    result = run_trading("RELIANCE", "buy", 10)
    print(result)
