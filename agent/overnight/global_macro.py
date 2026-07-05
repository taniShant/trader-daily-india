"""
Global Macro Collector - Fetches global market data for overnight analysis.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List
import boto3

class GlobalMacroCollector:
    """Collects global market data including US closes, VIX, currency, commodities."""
    
    def __init__(self):
        self.region = os.environ.get("AWS_REGION", "eu-west-2")
        self.market_state_table = os.environ.get("MARKET_STATE_TABLE", "svc-trd-market-state-dev")
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.market_state_db = self.dynamodb.Table(self.market_state_table)
    
    def collect(self) -> Dict[str, Any]:
        """Collect all global macro data."""
        macro_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "us_markets": self._get_us_market_data(),
            "europe_markets": self._get_europe_market_data(),
            "asia_markets": self._get_asia_market_data(),
            "india_vix": self._get_india_vix(),
            "dollar_index": self._get_dollar_index(),
            "crude_oil": self._get_crude_oil(),
            "gold": self._get_gold(),
            "us_bond_yields": self._get_us_bond_yields(),
        }
        
        # Store in DynamoDB
        self._store_macro_data(macro_data)
        
        return macro_data
    
    def _get_us_market_data(self) -> Dict[str, Any]:
        """Get US market indices data."""
        import yfinance as yf

        indices = {
            "^GSPC": "S&P 500",
            "^DJI": "Dow Jones",
            "^IXIC": "NASDAQ",
            "^RUT": "Russell 2000"
        }
        
        data = {}
        for symbol, name in indices.items():
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="2d")
                if not hist.empty:
                    current = hist['Close'].iloc[-1]
                    prev = hist['Close'].iloc[-2] if len(hist) > 1 else current
                    change_pct = ((current - prev) / prev) * 100
                    data[name] = {
                        "value": round(current, 2),
                        "change_percent": round(change_pct, 2)
                    }
            except Exception as e:
                print(f"Error fetching {name}: {e}")
        
        return data
    
    def _get_europe_market_data(self) -> Dict[str, Any]:
        """Get European market indices data."""
        import yfinance as yf

        indices = {
            "^FTSE": "FTSE 100",
            "^GDAXI": "DAX",
            "^FCHI": "CAC 40",
        }
        
        data = {}
        for symbol, name in indices.items():
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="2d")
                if not hist.empty:
                    current = hist['Close'].iloc[-1]
                    prev = hist['Close'].iloc[-2] if len(hist) > 1 else current
                    change_pct = ((current - prev) / prev) * 100
                    data[name] = {
                        "value": round(current, 2),
                        "change_percent": round(change_pct, 2)
                    }
            except Exception as e:
                print(f"Error fetching {name}: {e}")
        
        return data
    
    def _get_asia_market_data(self) -> Dict[str, Any]:
        """Get Asian market indices data."""
        import yfinance as yf

        indices = {
            "^N225": "Nikkei 225",
            "000001.SS": "Shanghai Composite",
            "^HSI": "Hang Seng",
        }
        
        data = {}
        for symbol, name in indices.items():
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="2d")
                if not hist.empty:
                    current = hist['Close'].iloc[-1]
                    prev = hist['Close'].iloc[-2] if len(hist) > 1 else current
                    change_pct = ((current - prev) / prev) * 100
                    data[name] = {
                        "value": round(current, 2),
                        "change_percent": round(change_pct, 2)
                    }
            except Exception as e:
                print(f"Error fetching {name}: {e}")
        
        return data
    
    def _get_india_vix(self) -> Dict[str, Any]:
        """Get India VIX data."""
        import yfinance as yf

        try:
            ticker = yf.Ticker("^INDIAVIX")
            hist = ticker.history(period="5d")
            if not hist.empty:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2] if len(hist) > 1 else current
                change_pct = ((current - prev) / prev) * 100
                return {
                    "value": round(current, 2),
                    "change_percent": round(change_pct, 2),
                    "interpretation": "HIGH" if current > 20 else "LOW" if current < 12 else "NORMAL"
                }
        except Exception as e:
            print(f"Error fetching India VIX: {e}")
        
        return {"value": 0, "change_percent": 0, "interpretation": "UNKNOWN"}
    
    def _get_dollar_index(self) -> Dict[str, Any]:
        """Get US Dollar Index (DXY)."""
        import yfinance as yf

        try:
            ticker = yf.Ticker("DX-Y.NYB")
            hist = ticker.history(period="2d")
            if not hist.empty:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2] if len(hist) > 1 else current
                change_pct = ((current - prev) / prev) * 100
                return {"value": round(current, 2), "change_percent": round(change_pct, 2)}
        except Exception as e:
            print(f"Error fetching Dollar Index: {e}")
        
        return {"value": 0, "change_percent": 0}
    
    def _get_crude_oil(self) -> Dict[str, Any]:
        """Get Crude Oil prices (WTI)."""
        import yfinance as yf

        try:
            ticker = yf.Ticker("CL=F")
            hist = ticker.history(period="2d")
            if not hist.empty:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2] if len(hist) > 1 else current
                change_pct = ((current - prev) / prev) * 100
                return {"value": round(current, 2), "change_percent": round(change_pct, 2)}
        except Exception as e:
            print(f"Error fetching Crude Oil: {e}")
        
        return {"value": 0, "change_percent": 0}
    
    def _get_gold(self) -> Dict[str, Any]:
        """Get Gold prices."""
        import yfinance as yf

        try:
            ticker = yf.Ticker("GC=F")
            hist = ticker.history(period="2d")
            if not hist.empty:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2] if len(hist) > 1 else current
                change_pct = ((current - prev) / prev) * 100
                return {"value": round(current, 2), "change_percent": round(change_pct, 2)}
        except Exception as e:
            print(f"Error fetching Gold: {e}")
        
        return {"value": 0, "change_percent": 0}
    
    def _get_us_bond_yields(self) -> Dict[str, Any]:
        """Get US Treasury yields."""
        import yfinance as yf

        bonds = {
            "10-year": "^TNX",
            "2-year": "^IRX",
        }
        
        data = {}
        for name, symbol in bonds.items():
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="2d")
                if not hist.empty:
                    current = hist['Close'].iloc[-1]
                    prev = hist['Close'].iloc[-2] if len(hist) > 1 else current
                    change = current - prev
                    data[name] = {
                        "value": round(current, 2),
                        "change": round(change, 2)
                    }
            except Exception as e:
                print(f"Error fetching {name} yield: {e}")
        
        return data
    
    def _store_macro_data(self, macro_data: Dict[str, Any]):
        """Store macro data in DynamoDB."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        # Determine global sentiment
        global_sentiment = "neutral"
        us_data = macro_data.get("us_markets", {})
        
        sp500_change = us_data.get("S&P 500", {}).get("change_percent", 0)
        nasdaq_change = us_data.get("NASDAQ", {}).get("change_percent", 0)
        
        avg_change = (sp500_change + nasdaq_change) / 2 if sp500_change and nasdaq_change else 0
        
        if avg_change > 0.5:
            global_sentiment = "positive"
        elif avg_change < -0.5:
            global_sentiment = "negative"
        
        item = {
            "date": today,
            "timestamp": datetime.utcnow().isoformat(),
            "type": "global_macro",
            "global_sentiment": global_sentiment,
            "data": macro_data
        }
        
        self.market_state_db.put_item(Item=item)
        print(f"✅ Stored global macro data for {today}")
