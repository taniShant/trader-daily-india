from strands import Agent, tool
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
from tools.market_data import get_historical_data, get_live_quote

@tool
def calculate_rsi(stock_symbol: str, period: int = 14) -> dict:
    """Calculate RSI indicator"""
    df = get_historical_data(stock_symbol, days=30)
    if df is None or df.empty:
        return {"error": "No data available"}
    
    df['rsi'] = ta.rsi(df['close'], length=period)
    current_rsi = df['rsi'].iloc[-1]
    
    return {
        "current_rsi": current_rsi,
        "signal": "oversold" if current_rsi < 30 else "overbought" if current_rsi > 70 else "neutral",
        "recommendation": "BUY_ON_DIPS" if current_rsi < 30 else "BOOK_PROFITS" if current_rsi > 70 else "HOLD"
    }

@tool
def calculate_macd(stock_symbol: str) -> dict:
    """Calculate MACD indicator"""
    df = get_historical_data(stock_symbol, days=60)
    if df is None or df.empty:
        return {"error": "No data available"}
    
    macd = ta.macd(df['close'])
    current_macd = macd['MACD_12_26_9'].iloc[-1]
    current_signal = macd['MACDs_12_26_9'].iloc[-1]
    
    return {
        "macd_line": current_macd,
        "signal_line": current_signal,
        "crossover": "bullish" if current_macd > current_signal else "bearish",
        "histogram": current_macd - current_signal
    }

@tool
def calculate_bollinger(stock_symbol: str) -> dict:
    """Calculate Bollinger Bands"""
    df = get_historical_data(stock_symbol, days=30)
    if df is None or df.empty:
        return {"error": "No data available"}
    
    bb = ta.bbands(df['close'], length=20, std=2)
    current_price = df['close'].iloc[-1]
    upper = bb['BBU_20_2.0'].iloc[-1]
    lower = bb['BBL_20_2.0'].iloc[-1]
    
    if current_price > upper:
        position = "above_upper"
        signal = "SELL"
    elif current_price < lower:
        position = "below_lower"
        signal = "BUY"
    else:
        position = "within_bands"
        signal = "HOLD"
    
    return {
        "current_price": current_price,
        "upper_band": upper,
        "lower_band": lower,
        "position": position,
        "signal": signal,
        "band_width": (upper - lower) / bb['BBM_20_2.0'].iloc[-1]
    }

class TechnicalAnalyst(Agent):
    """Specialist agent for technical analysis"""
    
    def __init__(self, model, memory):
        super().__init__(
            name="TechnicalAnalyst",
            model=model,
            memory=memory,
            tools=[calculate_rsi, calculate_macd, calculate_bollinger, get_live_quote],
            system_prompt="""
            You are a senior technical analyst. Your job is to analyze stock price data
            and technical indicators to identify trading opportunities.
            
            Analyze RSI, MACD, and Bollinger Bands together:
            - RSI < 30 + Price below lower Bollinger = STRONG BUY
            - RSI > 70 + Price above upper Bollinger = STRONG SELL
            - MACD bullish crossover + RSI neutral = CAUTIOUS BUY
            - Conflicting signals = HOLD or WAIT
            
            Output your analysis as JSON with fields:
            - trend (bullish/bearish/neutral)
            - rsi_signal
            - macd_signal
            - bollinger_signal
            - recommendation (BUY/SELL/HOLD)
            - confidence (0-100)
            - key_levels: support, resistance
            """
        )