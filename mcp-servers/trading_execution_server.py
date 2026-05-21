#!/usr/bin/env python3
"""
MCP Server for Trade Execution using ICICI Direct Breeze API
Provides tools for live quotes, order placement, and position management
"""

import asyncio
import json
import os
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from breeze_connect import BreezeConnect
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trading-execution-server")

# ============================================================
# INITIALIZE BREEZE CLIENT
# ============================================================

def get_breeze_client():
    """Initialize BreezeConnect client with credentials"""
    api_key = os.environ.get("ICICI_API_KEY")
    api_secret = os.environ.get("ICICI_SECRET_KEY")
    session_token = os.environ.get("ICICI_SESSION_TOKEN")
    
    if not all([api_key, api_secret, session_token]):
        raise ValueError("Missing ICICI credentials. Set ICICI_API_KEY, ICICI_SECRET_KEY, ICICI_SESSION_TOKEN")
    
    breeze = BreezeConnect(
        api_key=api_key,
        api_secret=api_secret,
        session_token=session_token
    )
    return breeze

# Initialize MCP Server
server = Server("trading-execution")

# ============================================================
# TOOL DEFINITIONS
# ============================================================

@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List all available trading execution tools"""
    return [
        types.Tool(
            name="get_live_quote",
            description="Get live market quote for an NSE stock",
            inputSchema={
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "description": "Stock symbol (e.g., 'RELIANCE', 'TCS')"}
                },
                "required": ["stock_code"]
            }
        ),
        types.Tool(
            name="place_intraday_order",
            description="Place an intraday buy or sell order",
            inputSchema={
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string"},
                    "action": {"type": "string", "enum": ["buy", "sell"]},
                    "quantity": {"type": "integer", "minimum": 1},
                    "price": {"type": "number", "description": "Limit price for the order"},
                    "stoploss": {"type": "number", "description": "Stop loss price (optional)"}
                },
                "required": ["stock_code", "action", "quantity", "price"]
            }
        ),
        types.Tool(
            name="get_positions",
            description="Get current open positions",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="square_off_position",
            description="Square off an open position",
            inputSchema={
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string"},
                    "quantity": {"type": "integer"}
                },
                "required": ["stock_code", "quantity"]
            }
        ),
        types.Tool(
            name="get_order_status",
            description="Get status of an order by order ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"}
                },
                "required": ["order_id"]
            }
        ),
        types.Tool(
            name="get_portfolio_holdings",
            description="Get complete portfolio holdings",
            inputSchema={"type": "object", "properties": {}}
        )
    ]

# ============================================================
# TOOL IMPLEMENTATIONS
# ============================================================

def get_live_quote(stock_code: str) -> Dict[str, Any]:
    """Get live market quote"""
    try:
        breeze = get_breeze_client()
        response = breeze.get_quotes(
            stock_code=stock_code,
            exchange_code="NSE"
        )
        
        if response and response.get("Success"):
            data = response["Success"]
            return {
                "stock_code": stock_code,
                "ltp": data.get("ltp"),
                "open": data.get("open"),
                "high": data.get("high"),
                "low": data.get("low"),
                "close": data.get("close"),
                "volume": data.get("volume"),
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {"error": response.get("Error", "Unknown error")}
    except Exception as e:
        logger.error(f"Error getting quote: {e}")
        return {"error": str(e)}

def place_intraday_order(stock_code: str, action: str, quantity: int, price: float, stoploss: float = None) -> Dict[str, Any]:
    """Place an intraday order"""
    try:
        breeze = get_breeze_client()
        
        order_params = {
            "stock_code": stock_code,
            "exchange_code": "NSE",
            "action": action.lower(),
            "order_type": "limit",
            "price": price,
            "quantity": quantity,
            "validity": "day",
            "product_type": "intraday"
        }
        
        if stoploss:
            order_params["stoploss"] = stoploss
        
        response = breeze.place_order(**order_params)
        
        if response and response.get("Success"):
            return {
                "order_id": response["Success"].get("order_id"),
                "stock_code": stock_code,
                "action": action,
                "quantity": quantity,
                "price": price,
                "status": "placed",
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {"error": response.get("Error", "Order placement failed")}
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        return {"error": str(e)}

def get_positions() -> Dict[str, Any]:
    """Get current open positions"""
    try:
        breeze = get_breeze_client()
        response = breeze.get_positions()
        
        if response and response.get("Success"):
            positions = response["Success"]
            return {
                "positions": positions,
                "total_positions": len(positions) if isinstance(positions, list) else 0,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {"error": response.get("Error", "Failed to fetch positions")}
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        return {"error": str(e)}

def square_off_position(stock_code: str, quantity: int) -> Dict[str, Any]:
    """Square off an open position"""
    try:
        # First get current position to determine if we need to buy or sell
        breeze = get_breeze_client()
        positions_response = breeze.get_positions()
        
        if not positions_response or not positions_response.get("Success"):
            return {"error": "Could not fetch current positions"}
        
        positions = positions_response["Success"]
        current_position = None
        
        if isinstance(positions, list):
            for pos in positions:
                if pos.get("stock_code") == stock_code:
                    current_position = pos
                    break
        
        if not current_position:
            return {"error": f"No open position found for {stock_code}"}
        
        # Determine square-off action
        net_quantity = float(current_position.get("net_quantity", 0))
        if net_quantity > 0:
            action = "sell"
        elif net_quantity < 0:
            action = "buy"
            quantity = abs(quantity)
        else:
            return {"error": "Position has zero net quantity"}
        
        # Get market price for square off
        quote = get_live_quote(stock_code)
        if quote.get("error"):
            return {"error": "Could not get market price"}
        
        market_price = quote.get("ltp")
        
        # Place square off order
        response = breeze.place_order(
            stock_code=stock_code,
            exchange_code="NSE",
            action=action,
            order_type="market",
            quantity=quantity,
            validity="day",
            product_type="intraday"
        )
        
        if response and response.get("Success"):
            return {
                "order_id": response["Success"].get("order_id"),
                "stock_code": stock_code,
                "action": action,
                "quantity": quantity,
                "execution_price": market_price,
                "status": "squared_off",
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {"error": response.get("Error", "Square off failed")}
    except Exception as e:
        logger.error(f"Error squaring off: {e}")
        return {"error": str(e)}

def get_order_status(order_id: str) -> Dict[str, Any]:
    """Get status of a specific order"""
    try:
        breeze = get_breeze_client()
        response = breeze.get_order_detail(order_id=order_id)
        
        if response and response.get("Success"):
            return {
                "order_id": order_id,
                "status": response["Success"].get("order_status"),
                "filled_quantity": response["Success"].get("filled_quantity"),
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {"error": response.get("Error", "Order not found")}
    except Exception as e:
        logger.error(f"Error getting order status: {e}")
        return {"error": str(e)}

def get_portfolio_holdings() -> Dict[str, Any]:
    """Get complete portfolio holdings"""
    try:
        breeze = get_breeze_client()
        response = breeze.get_holdings()
        
        if response and response.get("Success"):
            holdings = response["Success"]
            total_value = 0
            
            if isinstance(holdings, list):
                for holding in holdings:
                    # Get current market price for each holding
                    quote = get_live_quote(holding.get("stock_code"))
                    if not quote.get("error"):
                        ltp = quote.get("ltp", 0)
                        quantity = float(holding.get("quantity", 0))
                        total_value += ltp * quantity
                        holding["current_price"] = ltp
                        holding["current_value"] = ltp * quantity
            
            return {
                "holdings": holdings,
                "total_holdings_value": total_value,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {"error": response.get("Error", "Failed to fetch holdings")}
    except Exception as e:
        logger.error(f"Error getting holdings: {e}")
        return {"error": str(e)}

# ============================================================
# MCP REQUEST HANDLER
# ============================================================

@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: Optional[Dict[str, Any]] = None
) -> List[types.TextContent]:
    """Handle incoming tool execution requests"""
    
    logger.info(f"Tool called: {name} with arguments: {arguments}")
    
    if name == "get_live_quote":
        stock_code = arguments.get("stock_code")
        result = get_live_quote(stock_code)
        
    elif name == "place_intraday_order":
        stock_code = arguments.get("stock_code")
        action = arguments.get("action")
        quantity = arguments.get("quantity")
        price = arguments.get("price")
        stoploss = arguments.get("stoploss")
        result = place_intraday_order(stock_code, action, quantity, price, stoploss)
        
    elif name == "get_positions":
        result = get_positions()
        
    elif name == "square_off_position":
        stock_code = arguments.get("stock_code")
        quantity = arguments.get("quantity")
        result = square_off_position(stock_code, quantity)
        
    elif name == "get_order_status":
        order_id = arguments.get("order_id")
        result = get_order_status(order_id)
        
    elif name == "get_portfolio_holdings":
        result = get_portfolio_holdings()
        
    else:
        result = {"error": f"Unknown tool: {name}"}
    
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

# ============================================================
# RUN THE SERVER
# ============================================================

async def main():
    """Main entry point for the MCP server"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="trading-execution",
                server_version="1.0.0"
            )
        )

if __name__ == "__main__":
    asyncio.run(main())