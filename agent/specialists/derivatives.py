from strands import Agent, tool
from typing import Dict, Any, List
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from agent.data.symbols import yahoo_symbol


def _to_yahoo_symbol(stock_symbol: str) -> str:
    return yahoo_symbol(stock_symbol)


@tool
def get_option_chain_data(stock_symbol: str) -> Dict[str, Any]:
    """Fetch available option chain for a stock"""
    import yfinance as yf

    stock_symbol = _to_yahoo_symbol(stock_symbol)
    
    ticker = yf.Ticker(stock_symbol)
    
    try:
        expirations = ticker.options
        
        if not expirations:
            return {"error": "No options data available for this stock"}
        
        # Get nearest expiration
        nearest_expiry = expirations[0]
        option_chain = ticker.option_chain(nearest_expiry)
        
        calls = option_chain.calls
        puts = option_chain.puts
        
        # Calculate put/call ratio by volume
        call_volume = calls['volume'].sum() if 'volume' in calls.columns else 0
        put_volume = puts['volume'].sum() if 'volume' in puts.columns else 0
        put_call_ratio = put_volume / call_volume if call_volume > 0 else None
        
        # Find max open interest strikes
        max_call_oi = calls.loc[calls['openInterest'].idxmax()] if not calls.empty and 'openInterest' in calls.columns else None
        max_put_oi = puts.loc[puts['openInterest'].idxmax()] if not puts.empty and 'openInterest' in puts.columns else None
        
        return {
            "symbol": stock_symbol,
            "expiration": nearest_expiry,
            "put_call_volume_ratio": put_call_ratio,
            "max_call_open_interest": {
                "strike": float(max_call_oi['strike']) if max_call_oi is not None else None,
                "open_interest": int(max_call_oi['openInterest']) if max_call_oi is not None else None
            } if max_call_oi is not None else None,
            "max_put_open_interest": {
                "strike": float(max_put_oi['strike']) if max_put_oi is not None else None,
                "open_interest": int(max_put_oi['openInterest']) if max_put_oi is not None else None
            } if max_put_oi is not None else None,
            "calls_analyzed": len(calls),
            "puts_analyzed": len(puts)
        }
    except Exception as e:
        return {"error": str(e), "message": "Option chain data requires Breeze API for full NSE access"}

@tool
def calculate_implied_volatility(stock_symbol: str) -> Dict[str, Any]:
    """Estimate implied volatility from options prices"""
    import yfinance as yf

    # This is a simplified estimation. For production, use Breeze API
    stock_symbol = _to_yahoo_symbol(stock_symbol)
    
    ticker = yf.Ticker(stock_symbol)
    hist = ticker.history(period="1mo")
    
    if hist.empty:
        return {"error": "No price data available"}
    
    # Calculate historical volatility as proxy
    returns = hist['Close'].pct_change().dropna()
    historical_vol = returns.std() * np.sqrt(252) * 100
    
    # For NIFTY, India VIX is available
    if stock_symbol == "^NSEI.NS":
        try:
            vix = yf.Ticker("^INDIAVIX")
            vix_hist = vix.history(period="1d")
            current_vix = vix_hist['Close'].iloc[-1] if not vix_hist.empty else historical_vol
            return {
                "symbol": stock_symbol,
                "implied_volatility": current_vix,
                "historical_volatility": historical_vol,
                "source": "INDIA_VIX"
            }
        except:
            pass
    
    return {
        "symbol": stock_symbol,
        "implied_volatility_estimate": historical_vol,
        "historical_volatility": historical_vol,
        "note": "Estimated from historical data; use Breeze API for accurate IV"
    }

@tool
def get_put_call_ratio(stock_symbol: str) -> Dict[str, Any]:
    """Calculate put/call ratio for sentiment analysis"""
    import yfinance as yf

    stock_symbol = _to_yahoo_symbol(stock_symbol)
    
    ticker = yf.Ticker(stock_symbol)
    
    try:
        expirations = ticker.options
        if not expirations:
            return {"error": "No options data"}
        
        total_call_volume = 0
        total_put_volume = 0
        total_call_oi = 0
        total_put_oi = 0
        
        for expiry in expirations[:3]:  # Check next 3 expirations
            chain = ticker.option_chain(expiry)
            
            if 'volume' in chain.calls.columns:
                total_call_volume += chain.calls['volume'].sum()
                total_put_volume += chain.puts['volume'].sum()
            
            if 'openInterest' in chain.calls.columns:
                total_call_oi += chain.calls['openInterest'].sum()
                total_put_oi += chain.puts['openInterest'].sum()
        
        volume_ratio = total_put_volume / total_call_volume if total_call_volume > 0 else None
        oi_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else None
        
        sentiment = "BULLISH" if volume_ratio and volume_ratio < 0.7 else "BEARISH" if volume_ratio and volume_ratio > 1.3 else "NEUTRAL"
        
        return {
            "symbol": stock_symbol,
            "put_call_volume_ratio": volume_ratio,
            "put_call_open_interest_ratio": oi_ratio,
            "sentiment_signal": sentiment,
            "interpretation": "Options market expects upside" if volume_ratio and volume_ratio < 0.7 else "Options market expects downside" if volume_ratio and volume_ratio > 1.3 else "Options market is balanced"
        }
    except Exception as e:
        return {"error": str(e)}

@tool
def get_max_pain_strike(stock_symbol: str) -> Dict[str, Any]:
    """Calculate max pain strike price (where option buyers lose the most)"""
    import yfinance as yf

    stock_symbol = _to_yahoo_symbol(stock_symbol)
    
    ticker = yf.Ticker(stock_symbol)
    spot_price = ticker.history(period="1d")['Close'].iloc[-1] if not ticker.history(period="1d").empty else 0
    
    try:
        expirations = ticker.options
        if not expirations:
            return {"error": "No options data"}
        
        nearest_expiry = expirations[0]
        chain = ticker.option_chain(nearest_expiry)
        
        calls = chain.calls[['strike', 'openInterest']].copy()
        puts = chain.puts[['strike', 'openInterest']].copy()
        
        calls.columns = ['strike', 'call_oi']
        puts.columns = ['strike', 'put_oi']
        
        merged = pd.merge(calls, puts, on='strike', how='outer').fillna(0)
        
        # Calculate pain for each strike
        strikes = merged['strike'].values
        pain_values = []
        
        for test_strike in strikes:
            call_pain = sum(merged[merged['strike'] > test_strike]['call_oi'] * (merged[merged['strike'] > test_strike]['strike'] - test_strike))
            put_pain = sum(merged[merged['strike'] < test_strike]['put_oi'] * (test_strike - merged[merged['strike'] < test_strike]['strike']))
            pain_values.append(call_pain + put_pain)
        
        min_pain_idx = np.argmin(pain_values)
        max_pain = strikes[min_pain_idx]
        
        return {
            "symbol": stock_symbol,
            "spot_price": spot_price,
            "max_pain_strike": float(max_pain),
            "distance_from_spot": float(max_pain - spot_price),
            "interpretation": "Price may gravitate towards max pain at expiry" if abs(max_pain - spot_price) > spot_price * 0.02 else "Price is near max pain level"
        }
    except Exception as e:
        return {"error": str(e)}

class DerivativesAnalyst(Agent):
    """Specialist agent for options and derivatives analysis"""
    
    def __init__(self, model, memory=None):
        super().__init__(
            name="DerivativesAnalyst",
            model=model,
            tools=[
                get_option_chain_data,
                calculate_implied_volatility,
                get_put_call_ratio,
                get_max_pain_strike
            ],
            system_prompt="""
            You are a derivatives market specialist for NSE India.
            
            Your job is to analyze options market data to gauge institutional sentiment and potential price direction.
            
            Key indicators:
            1. **Put/Call Ratio**: High ratio (>1.3) suggests bearish sentiment; low ratio (<0.7) suggests bullish sentiment
            2. **Max Pain**: The strike price where option buyers lose the most; price tends to gravitate towards this at expiry
            3. **Implied Volatility**: High IV suggests uncertainty/panic; low IV suggests complacency
            
            Output JSON with:
            - market_sentiment (BULLISH/BEARISH/NEUTRAL)
            - confidence (0-100)
            - put_call_ratio (current value)
            - max_pain_strike
            - iv_interpretation (high/low/normal)
            - key_levels (support/resistance from options data)
            """
        )
