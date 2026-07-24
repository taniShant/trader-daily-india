"""
Market Data Tools - Fetches live and historical market data.
Supports both yfinance (fallback) and ICICI Breeze API (primary).
"""

import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from strands import tool

from agent.data.oracle_client import OracleCollectorClient
from agent.data.market_data import (
    normalize_ohlcv_bars,
    normalize_quote,
    ohlcv_bars_to_tool_payload,
    quote_to_tool_payload,
)
from agent.data.quality import check_ohlcv_quality, check_quote_quality
from agent.data.symbols import breeze_stock_code, canonical_symbol, yahoo_symbol

class MarketDataProvider:
    """Provides market data from Breeze API (primary) or yfinance (fallback)."""
    
    def __init__(self):
        self.breeze = None
        self.oracle_client = self._init_oracle_collector()
        self.use_breeze = self._init_breeze()

    def _init_oracle_collector(self) -> OracleCollectorClient | None:
        """Initialize Oracle collector client when AWS has a configured collector URL."""
        base_url = os.environ.get("ORACLE_COLLECTOR_BASE_URL")
        if not base_url:
            return None
        return OracleCollectorClient(base_url=base_url, timeout_seconds=5.0)
    
    def _init_breeze(self) -> bool:
        """Initialize Breeze Connect with credentials from environment."""
        api_key = os.environ.get("ICICI_API_KEY")
        secret_key = os.environ.get("ICICI_SECRET_KEY")
        session_token = os.environ.get("ICICI_SESSION_TOKEN")
        
        if not all([api_key, secret_key, session_token]):
            print("⚠️ ICICI credentials not fully configured. Using yfinance fallback.")
            return False
        
        try:
            BreezeConnect = _load_breeze_connect()
            if BreezeConnect is None:
                return False
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
        canonical = canonical_symbol(stock_symbol)
        oracle_client = getattr(self, "oracle_client", None)
        if oracle_client is not None:
            try:
                payload = oracle_client.fetch_quote(canonical)
                quote = normalize_quote(payload, symbol=canonical, source=payload.get("source", "oracle"))
                quality = check_quote_quality(quote, require_volume=True)
                if not quality.passed:
                    return _quality_error(canonical, quality.reasons)
                return quote_to_tool_payload(quote)
            except Exception as e:
                print(f"Oracle collector quote error for {stock_symbol}: {e}")

        if self.use_breeze and self.breeze:
            try:
                response = self.breeze.get_quotes(
                    stock_code=breeze_stock_code(stock_symbol),
                    exchange_code="NSE"
                )
                if response and response.get("Success"):
                    data = response["Success"]
                    quote = normalize_quote(data, symbol=canonical, source="breeze")
                    quality = check_quote_quality(quote, require_volume=True)
                    if not quality.passed:
                        return _quality_error(canonical, quality.reasons)
                    return quote_to_tool_payload(quote)
            except Exception as e:
                print(f"Breeze quote error for {stock_symbol}: {e}")
        
        # Fallback to yfinance
        return self._get_yfinance_quote(stock_symbol)
    
    def _get_yfinance_quote(self, stock_symbol: str) -> Dict[str, Any]:
        """Fallback to yfinance for live quotes."""
        try:
            import yfinance as yf

            canonical = canonical_symbol(stock_symbol)
            ticker = yf.Ticker(yahoo_symbol(stock_symbol))
            info = ticker.fast_info
            quote = normalize_quote(dict(info), symbol=canonical, source="yfinance")
            quality = check_quote_quality(quote, require_volume=True)
            if not quality.passed:
                return _quality_error(canonical, quality.reasons)
            return quote_to_tool_payload(quote)
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
        canonical = canonical_symbol(stock_symbol)
        oracle_client = getattr(self, "oracle_client", None)
        if oracle_client is not None:
            try:
                payload = oracle_client.fetch_ohlcv(canonical, days=days, interval=interval)
                source = payload.get("source") or _first_row_source(payload) or "oracle"
                bars = normalize_ohlcv_bars(
                    payload.get("data", []),
                    symbol=canonical,
                    interval=interval,
                    source=source,
                )
                quality = check_ohlcv_quality(
                    bars,
                    symbol=canonical,
                    interval=interval,
                    min_bars=1,
                    require_nonzero_volume=True,
                )
                if not quality.passed:
                    return _quality_error(canonical, quality.reasons)
                return ohlcv_bars_to_tool_payload(
                    symbol=canonical,
                    days=days,
                    interval=interval,
                    bars=bars,
                )
            except Exception as e:
                print(f"Oracle collector OHLCV error for {stock_symbol}: {e}")

        try:
            import yfinance as yf

            ticker = yf.Ticker(yahoo_symbol(stock_symbol))
            hist = ticker.history(period=f"{days}d", interval=interval)
            
            if hist.empty:
                return {"error": "No historical data available"}

            records = hist.reset_index().to_dict(orient="records")
            bars = normalize_ohlcv_bars(
                records,
                symbol=canonical,
                interval=interval,
                source="yfinance",
            )
            quality = check_ohlcv_quality(
                bars,
                symbol=canonical,
                interval=interval,
                min_bars=1,
                require_nonzero_volume=True,
            )
            if not quality.passed:
                return _quality_error(canonical, quality.reasons)
            
            return ohlcv_bars_to_tool_payload(
                symbol=canonical,
                days=days,
                interval=interval,
                bars=bars,
            )
        except Exception as e:
            return {"error": str(e)}
    
    def calculate_technical_indicators(self, stock_symbol: str, period: str = "1mo") -> Dict[str, Any]:
        """Calculate RSI, MACD, and Bollinger Bands."""
        try:
            import pandas as pd
            import pandas_ta as ta
            import yfinance as yf
            
            ticker = yf.Ticker(yahoo_symbol(stock_symbol))
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


def _quality_error(symbol: str, reasons: list[str]) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "error": "data_quality_failed",
        "reasons": reasons,
    }


def _first_row_source(payload: dict[str, Any]) -> str | None:
    rows = payload.get("data", [])
    if rows and isinstance(rows[0], dict):
        source = rows[0].get("source")
        return str(source) if source else None
    return None


def _load_breeze_connect():
    try:
        from breeze_connect import BreezeConnect

        return BreezeConnect
    except ImportError:
        print("⚠️ breeze-connect not available. Using yfinance only.")
        return None
    except Exception as exc:
        print(f"⚠️ breeze-connect import failed. Using yfinance only: {exc}")
        return None
