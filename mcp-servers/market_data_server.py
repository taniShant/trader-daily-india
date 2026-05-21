#!/usr/bin/env python3
"""
MCP Server for Indian Stock Market Data
Provides tools for fetching live quotes, historical data, and option chains
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import yfinance as yf
import pandas as pd
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Initialize MCP Server
server = Server("indian-market-data")

# ============================================================
# TOOL DEFINITIONS
# ============================================================

@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List all available market data tools"""
    return [
        types.Tool(
            name="get_live_quote",
            description="Get live quote for an Indian stock (NSE/BSE)",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Stock symbol (e.g., 'RELIANCE.NS', 'TCS.NS')"}
                },
                "required": ["symbol"]
            }
        ),
        types.Tool(
            name="get_historical_data",
            description="Get historical OHLCV data for a stock",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "period": {"type": "string", "description": "1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max"},
                    "interval": {"type": "string", "description": "1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo"}
                },
                "required": ["symbol"]
            }
        ),
        types.Tool(
            name="get_technical_indicators",
            description="Calculate RSI, MACD, Bollinger Bands for a stock",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "period": {"type": "string", "default": "1mo"}
                },
                "required": ["symbol"]
            }
        ),
        types.Tool(
            name="get_company_fundamentals",
            description="Get fundamental data (P/E, market cap, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"}
                },
                "required": ["symbol"]
            }
        ),
        types.Tool(
            name="get_option_chain",
            description="Get options chain for NSE stock",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"}
                },
                "required": ["symbol"]
            }
        ),
        types.Tool(
            name="get_market_sentiment",
            description="Get overall market sentiment (India VIX, advance-decline ratio)",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]

# ============================================================
# TOOL IMPLEMENTATIONS
# ============================================================

@server.call_tool()
async def handle_call_tool(
    name: str, 
    arguments: Optional[Dict[str, Any]] = None
) -> List[types.TextContent]:
    """Handle tool execution requests"""
    
    if name == "get_live_quote":
        symbol = arguments.get("symbol")
        if not symbol.endswith(".NS"):
            symbol = f"{symbol}.NS"
        
        ticker = yf.Ticker(symbol)
        info = ticker.info
        fast_info = ticker.fast_info
        
        result = {
            "symbol": symbol,
            "current_price": fast_info.get("lastPrice", 0),
            "open": fast_info.get("open", 0),
            "day_high": fast_info.get("dayHigh", 0),
            "day_low": fast_info.get("dayLow", 0),
            "volume": fast_info.get("volume", 0),
            "previous_close": fast_info.get("previousClose", 0),
            "change": fast_info.get("lastPrice", 0) - fast_info.get("previousClose", 0),
            "change_percent": ((fast_info.get("lastPrice", 0) - fast_info.get("previousClose", 0)) / fast_info.get("previousClose", 1)) * 100
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_historical_data":
        symbol = arguments.get("symbol")
        period = arguments.get("period", "1mo")
        interval = arguments.get("interval", "1d")
        
        if not symbol.endswith(".NS"):
            symbol = f"{symbol}.NS"
        
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        
        # Convert to serializable format
        hist_dict = hist.reset_index().to_dict(orient="records")
        for record in hist_dict:
            record["Date"] = str(record["Date"])
        
        return [types.TextContent(type="text", text=json.dumps(hist_dict[:50], indent=2, default=str))]
    
    elif name == "get_technical_indicators":
        symbol = arguments.get("symbol")
        period = arguments.get("period", "1mo")
        
        if not symbol.endswith(".NS"):
            symbol = f"{symbol}.NS"
        
        import pandas_ta as ta
        
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period)
        
        if df.empty:
            return [types.TextContent(type="text", text=json.dumps({"error": "No data available"}))]
        
        # Calculate indicators
        df['rsi'] = ta.rsi(df['Close'], length=14)
        macd = ta.macd(df['Close'])
        df['macd'] = macd['MACD_12_26_9'] if macd is not None else None
        df['macd_signal'] = macd['MACDs_12_26_9'] if macd is not None else None
        bb = ta.bbands(df['Close'], length=20)
        df['bb_upper'] = bb['BBU_20_2.0'] if bb is not None else None
        df['bb_lower'] = bb['BBL_20_2.0'] if bb is not None else None
        df['bb_middle'] = bb['BBM_20_2.0'] if bb is not None else None
        
        latest = df.iloc[-1]
        
        result = {
            "symbol": symbol,
            "current_price": latest['Close'],
            "rsi": float(latest['rsi']) if pd.notna(latest['rsi']) else None,
            "macd": float(latest['macd']) if pd.notna(latest.get('macd')) else None,
            "macd_signal": float(latest['macd_signal']) if pd.notna(latest.get('macd_signal')) else None,
            "bollinger_upper": float(latest['bb_upper']) if pd.notna(latest.get('bb_upper')) else None,
            "bollinger_lower": float(latest['bb_lower']) if pd.notna(latest.get('bb_lower')) else None,
            "bollinger_middle": float(latest['bb_middle']) if pd.notna(latest.get('bb_middle')) else None,
            "signal": "OVERSOLD" if latest['rsi'] < 30 else "OVERBOUGHT" if latest['rsi'] > 70 else "NEUTRAL" if pd.notna(latest['rsi']) else "UNKNOWN"
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_company_fundamentals":
        symbol = arguments.get("symbol")
        
        if not symbol.endswith(".NS"):
            symbol = f"{symbol}.NS"
        
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        result = {
            "symbol": symbol,
            "name": info.get("longName", ""),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE", 0),
            "forward_pe": info.get("forwardPE", 0),
            "dividend_yield": info.get("dividendYield", 0),
            "beta": info.get("beta", 0),
            "52_week_high": info.get("fiftyTwoWeekHigh", 0),
            "52_week_low": info.get("fiftyTwoWeekLow", 0),
            "target_price": info.get("targetMeanPrice", 0),
            "recommendation": info.get("recommendationKey", "unknown")
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_option_chain":
        symbol = arguments.get("symbol")
        # Note: yfinance has limited options data. For full NSE options, consider using nsepy or nsetools
        if not symbol.endswith(".NS"):
            symbol = f"{symbol}.NS"
        
        ticker = yf.Ticker(symbol)
        
        try:
            # Get option expiration dates
            expirations = ticker.options
            
            result = {
                "symbol": symbol,
                "expirations": expirations,
                "message": "Use nsepython or breeze-api for complete option chain data"
            }
        except Exception as e:
            result = {"error": str(e), "message": "Full option chain requires NSE API or Breeze API"}
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_market_sentiment":
        # Fetch India VIX
        try:
            vix = yf.Ticker("^INDIAVIX")
            vix_hist = vix.history(period="1d")
            current_vix = vix_hist['Close'].iloc[-1] if not vix_hist.empty else None
            
            # Fetch NIFTY 50 data
            nifty = yf.Ticker("^NSEI")
            nifty_hist = nifty.history(period="1d")
            nifty_close = nifty_hist['Close'].iloc[-1] if not nifty_hist.empty else None
            nifty_change = nifty_hist['Close'].pct_change().iloc[-1] * 100 if len(nifty_hist) > 1 else 0
            
            result = {
                "india_vix": current_vix,
                "nifty_close": nifty_close,
                "nifty_change_percent": nifty_change,
                "sentiment_interpretation": "HIGH_VOLATILITY" if current_vix and current_vix > 20 else "LOW_VOLATILITY" if current_vix and current_vix < 12 else "NORMAL",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            result = {"error": str(e)}
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

# ============================================================
# RUN THE SERVER
# ============================================================

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="indian-market-data",
                server_version="1.0.0"
            )
        )

if __name__ == "__main__":
    asyncio.run(main())