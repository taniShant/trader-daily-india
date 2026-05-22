"""
Market Data Tools - Fetches live and historical market data.
Supports both yfinance (fallback) and ICICI Breeze API (primary).
"""

import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import yfinance as yf

# Try to import Breeze Connect if available
try:
    from breeze_connect import BreezeConnect
    BREEZE_AVAILABLE = True
except ImportError:
    BREEZE_AVAILABLE = False
    print("⚠️ breeze-connect not available. Using yfinance only.")

class MarketDataProvider:
    """Provides market data from Breeze API (primary) or yfinance (fallback)."""
    
    def __init__(self):
        self.breeze = None
        self.use_breeze = BREEZE_AVAILABLE and self._init_breeze()
    
    def _init_breeze(self) -> bool:
        """Initialize Breeze Connect with credentials from environment."""
        api_key = os.environ.get("ICICI_API_KEY")
        secret_key = os.environ.get("ICICI_SECRET_KEY")
        session_token = os.environ.get("ICICI_SESSION_TOKEN")
        
        if not all([api_key, secret_key, session_token]):
            print("⚠️ ICICI credentials not fully configured. Using yfinance fallback.")
            return False
        
        try:
            self.breeze = BreezeConnect(api_key=api_key)
            self.breeze.generate_session(
                api_secret=secret_key,
                session_token=session_token
            )
            print("✅ Breeze Connect initialized successfully")
            return True
        except Exception as e:
            print(f"⚠️ Failed to initialize Breeze Connect: {e}")
            return False
    
    def get_live_quote(self, stock_symbol: str) -> Dict[str, Any]:
        """Get live quote for a stock."""
        if self.use_breeze and self.breeze:
            try:
                response = self.breeze.get_quotes(
                    stock_code=stock_symbol,
                    exchange_code="NSE"
                )
                if response and response.get("Success"):
                    data = response["Success"]
                    return {
                        "symbol": stock_symbol,
                        "ltp": data.get("ltp"),
                        "open": data.get("open"),
                        "high": data.get("high"),
                        "low": data.get("low"),
                        "close": data.get("close"),
                        "volume": data.get("volume"),
                        "source": "breeze"
                    }
            except Exception as e:
                print(f"Breeze quote error for {stock_symbol}: {e}")
        
        # Fallback to yfinance
        return self._get_yfinance_quote(stock_symbol)
    
    def _get_yfinance_quote(self, stock_symbol: str) -> Dict[str, Any]:
        """Fallback to yfinance for live quotes."""
        try:
            ticker = yf.Ticker(f"{stock_symbol}.NS")
            info = ticker.fast_info
            return {
                "symbol": stock_symbol,
                "ltp": info.get("lastPrice", 0),
                "open": info.get("open", 0),
                "high": info.get("dayHigh", 0),
                "low": info.get("dayLow", 0),
                "close": info.get("previousClose", 0),
                "volume": info.get("volume", 0),
                "source": "yfinance"
            }
        except Exception as e:
            print(f"yfinance quote error for {stock_symbol}: {e}")
            return {"symbol": stock_symbol, "error": str(e)}
    
    def get_historical_data(
        self, 
        stock_symbol: str, 
        days: int = 30,
        interval: str = "1d"
    ) -> Dict[str, Any]:
        """Get historical OHLCV data."""
        try:
            ticker = yf.Ticker(f"{stock_symbol}.NS")
            hist = ticker.history(period=f"{days}d", interval=interval)
            
            if hist.empty:
                return {"error": "No historical data available"}
            
            return {
                "symbol": stock_symbol,
                "days": days,
                "interval": interval,
                "data": hist.reset_index().to_dict(orient="records"),
                "latest_close": float(hist['Close'].iloc[-1]),
                "latest_volume": int(hist['Volume'].iloc[-1]),
                "high_52w": float(hist['High'].max()),
                "low_52w": float(hist['Low'].min()),
            }
        except Exception as e:
            return {"error": str(e)}
    
    def calculate_technical_indicators(self, stock_symbol: str, period: str = "1mo") -> Dict[str, Any]:
        """Calculate RSI, MACD, and Bollinger Bands."""
        try:
            import pandas as pd
            import pandas_ta as ta
            
            ticker = yf.Ticker(f"{stock_symbol}.NS")
            df = ticker.history(period=period)
            
            if df.empty:
                return {"error": "No data available"}
            
            # Calculate indicators
            df['rsi'] = ta.rsi(df['Close'], length=14)
            macd = ta.macd(df['Close'])
            bb = ta.bbands(df['Close'], length=20)
            
            latest = df.iloc[-1]
            
            return {
                "symbol": stock_symbol,
                "current_price": latest['Close'],
                "rsi": float(latest['rsi']) if pd.notna(latest['rsi']) else None,
                "macd": float(macd['MACD_12_26_9'].iloc[-1]) if macd is not None and not macd.empty else None,
                "macd_signal": float(macd['MACDs_12_26_9'].iloc[-1]) if macd is not None and not macd.empty else None,
                "bollinger_upper": float(bb['BBU_20_2.0'].iloc[-1]) if bb is not None and not bb.empty else None,
                "bollinger_lower": float(bb['BBL_20_2.0'].iloc[-1]) if bb is not None and not bb.empty else None,
                "signal": "OVERSOLD" if latest['rsi'] < 30 else "OVERBOUGHT" if latest['rsi'] > 70 else "NEUTRAL" if pd.notna(latest['rsi']) else "UNKNOWN"
            }
        except Exception as e:
            return {"error": str(e)}

# Singleton instance
_market_data = None

def get_market_data() -> MarketDataProvider:
    """Get singleton market data provider instance."""
    global _market_data
    if _market_data is None:
        _market_data = MarketDataProvider()
    return _market_data

@tool
def get_live_quote(stock_symbol: str) -> Dict[str, Any]:
    """Get live market quote for a stock."""
    provider = get_market_data()
    return provider.get_live_quote(stock_symbol)

@tool
def get_historical_data(stock_symbol: str, days: int = 30) -> Dict[str, Any]:
    """Get historical price data for technical analysis."""
    provider = get_market_data()
    return provider.get_historical_data(stock_symbol, days)