"""
Pre-Market Scanner - Generates watchlist before market open using overnight analysis.
Combines technical momentum with news sentiment for better stock selection.
"""

import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
import boto3
import yfinance as yf

class PreMarketScanner:
    """Scans all NIFTY stocks before market open to generate watchlist."""
    
    def __init__(self):
        self.region = os.environ.get("AWS_REGION", "eu-west-2")
        self.market_state_table = os.environ.get("MARKET_STATE_TABLE", "svc-trd-market-state-dev")
        self.watchlist_size = int(os.environ.get("WATCHLIST_SIZE", 10))
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.market_state_db = self.dynamodb.Table(self.market_state_table)
    
    def get_nifty_stocks(self) -> List[str]:
        """Get list of NIFTY 50 stocks."""
        return [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
            "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS", "BAJFINANCE.NS", "ITC.NS",
            "HINDUNILVR.NS", "AXISBANK.NS", "LT.NS", "SUNPHARMA.NS", "TITAN.NS",
            "MARUTI.NS", "WIPRO.NS", "ONGC.NS", "NTPC.NS", "POWERGRID.NS",
            "ULTRACEMCO.NS", "HCLTECH.NS", "BAJAJFINSV.NS", "ADANIPORTS.NS", "ASIANPAINT.NS",
            "GRASIM.NS", "NESTLE.NS", "JSWSTEEL.NS", "TECHM.NS", "INDUSINDBK.NS",
            "DRREDDY.NS", "BRITANNIA.NS", "EICHERMOT.NS", "COALINDIA.NS", "HDFC.NS",
            "DIVISLAB.NS", "SBILIFE.NS", "HDFCLIFE.NS", "UPL.NS", "BAJAJ-AUTO.NS",
            "SHREECEM.NS", "CIPLA.NS", "HEROMOTOCO.NS", "TATASTEEL.NS", "HINDALCO.NS",
            "BPCL.NS", "IOC.NS", "M&M.NS", "TATAMOTORS.NS", "TATACONSUM.NS"
        ]
    
    def scan_stocks(self) -> List[Dict[str, Any]]:
        """
        Scan all stocks and return top candidates for today's watchlist.
        Uses momentum score (price change * volume ratio) for ranking.
        """
        stocks = self.get_nifty_stocks()
        candidates = []
        
        for stock in stocks:
            try:
                ticker = yf.Ticker(stock)
                hist = ticker.history(period="5d")
                
                if hist.empty or len(hist) < 2:
                    continue
                
                current_price = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2]
                change_percent = ((current_price - prev_close) / prev_close) * 100
                
                volume = hist['Volume'].iloc[-1]
                avg_volume = hist['Volume'].mean()
                volume_ratio = volume / avg_volume if avg_volume > 0 else 1
                
                # Calculate momentum score
                momentum = change_percent * volume_ratio
                
                # Additional technical filter (optional)
                is_gap_up = current_price > hist['High'].iloc[-2]
                is_gap_down = current_price < hist['Low'].iloc[-2]
                
                candidates.append({
                    "symbol": stock.replace(".NS", ""),
                    "current_price": round(current_price, 2),
                    "change_percent": round(change_percent, 2),
                    "volume_ratio": round(volume_ratio, 2),
                    "momentum_score": round(momentum, 2),
                    "is_gap_up": is_gap_up,
                    "is_gap_down": is_gap_down,
                })
                
            except Exception as e:
                print(f"Error scanning {stock}: {e}")
        
        # Sort by momentum score (highest first)
        candidates.sort(key=lambda x: x["momentum_score"], reverse=True)
        
        # Return top N candidates
        watchlist = candidates[:self.watchlist_size]
        
        # Store in DynamoDB
        self._store_watchlist(watchlist)
        
        return watchlist
    
    def _store_watchlist(self, watchlist: List[Dict[str, Any]]):
        """Store pre-market watchlist in DynamoDB."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        # Get existing item or create new
        response = self.market_state_db.get_item(Key={"date": today})
        item = response.get("Item", {"date": today})
        
        item["pre_market_watchlist"] = watchlist
        item["watchlist_size"] = len(watchlist)
        item["timestamp"] = datetime.utcnow().isoformat()
        
        self.market_state_db.put_item(Item=item)
        print(f"✅ Stored pre-market watchlist for {today} ({len(watchlist)} stocks)")
    
    def get_watchlist(self) -> List[str]:
        """Retrieve today's watchlist from DynamoDB."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        response = self.market_state_db.get_item(Key={"date": today})
        item = response.get("Item", {})
        
        watchlist = item.get("pre_market_watchlist", [])
        if watchlist:
            return [w["symbol"] for w in watchlist]
        
        # Fallback to default watchlist
        print("⚠️ No pre-market watchlist found, using default")
        return ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
                "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE", "ITC"]