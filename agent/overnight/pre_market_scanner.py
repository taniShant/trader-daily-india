"""
Pre-Market Scanner - Generates watchlist before market open using overnight analysis.
Combines technical momentum with news sentiment for better stock selection.
"""

import os
from datetime import datetime, timezone
from typing import List, Dict, Any
import boto3

from agent.data.symbols import resolve_symbol
from agent.overnight.state_store import get_daily_state, put_daily_state

class PreMarketScanner:
    """Scans all NIFTY stocks before market open to generate watchlist."""
    
    def __init__(self):
        self.region = os.environ.get("AWS_REGION", "eu-west-2")
        self.market_state_table = os.environ.get("MARKET_STATE_TABLE", "svc-trd-market-state-dev")
        self.watchlist_size = int(os.environ.get("WATCHLIST_SIZE", 10))
        self.min_avg_volume = int(os.environ.get("PREMARKET_MIN_AVG_VOLUME", 100000))
        self.min_price = float(os.environ.get("PREMARKET_MIN_PRICE", 20))
        self.excluded_symbols = {
            symbol.strip().upper()
            for symbol in os.environ.get("WATCHLIST_EXCLUDED_SYMBOLS", "TCS,HDFCBANK,SBIN").split(",")
            if symbol.strip()
        }
        self.required_symbols = [
            resolve_symbol(symbol.strip()).canonical
            for symbol in os.environ.get("WATCHLIST_REQUIRED_SYMBOLS", "MARUTI").split(",")
            if symbol.strip()
        ]
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.market_state_db = self.dynamodb.Table(self.market_state_table)
    
    def get_nifty_stocks(self) -> List[str]:
        """Get list of NIFTY 50 stocks."""
        return [
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
            "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE", "ITC",
            "HINDUNILVR", "AXISBANK", "LT", "SUNPHARMA", "TITAN",
            "MARUTI", "WIPRO", "ONGC", "NTPC", "POWERGRID",
            "ULTRACEMCO", "HCLTECH", "BAJAJFINSV", "ADANIPORTS", "ASIANPAINT",
            "GRASIM", "NESTLEIND", "JSWSTEEL", "TECHM", "INDUSINDBK",
            "DRREDDY", "BRITANNIA", "EICHERMOT", "COALINDIA", "DIVISLAB",
            "SBILIFE", "HDFCLIFE", "UPL", "BAJAJ-AUTO", "SHREECEM",
            "CIPLA", "HEROMOTOCO", "TATASTEEL", "HINDALCO", "BPCL",
            "IOC", "M&M", "TMCV", "TMPV", "TATACONSUM"
        ]

    def _is_excluded(self, symbol: str) -> bool:
        return resolve_symbol(symbol).canonical in self.excluded_symbols

    def _filter_excluded_symbols(self, symbols: List[str]) -> List[str]:
        return [symbol for symbol in symbols if not self._is_excluded(symbol)]

    def _with_required_symbols(self, symbols: List[str]) -> List[str]:
        """Keep configured must-watch symbols in the active trading list."""
        result = []
        for symbol in self._filter_excluded_symbols(symbols):
            canonical = resolve_symbol(symbol).canonical
            if canonical not in result:
                result.append(canonical)

        for symbol in self.required_symbols:
            if symbol in self.excluded_symbols or symbol in result:
                continue
            if len(result) >= self.watchlist_size:
                removable_index = next(
                    (index for index in range(len(result) - 1, -1, -1) if result[index] not in self.required_symbols),
                    None,
                )
                if removable_index is not None:
                    result.pop(removable_index)
            result.append(symbol)

        return result[: self.watchlist_size]

    def _with_required_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        selected = candidates[: self.watchlist_size]
        selected_symbols = {item["symbol"] for item in selected}

        for required_symbol in self.required_symbols:
            if required_symbol in self.excluded_symbols or required_symbol in selected_symbols:
                continue
            required_candidate = next(
                (item for item in candidates if item["symbol"] == required_symbol),
                None,
            )
            if required_candidate is None:
                continue
            if len(selected) >= self.watchlist_size:
                removable_index = next(
                    (
                        index
                        for index in range(len(selected) - 1, -1, -1)
                        if selected[index]["symbol"] not in self.required_symbols
                    ),
                    None,
                )
                if removable_index is not None:
                    selected.pop(removable_index)
            selected.append(required_candidate)
            selected_symbols.add(required_symbol)

        return selected[: self.watchlist_size]

    def score_candidate(self, symbol: str, hist) -> Dict[str, Any] | None:
        """Score one stock using momentum, liquidity, and gap context."""
        if hist is None or hist.empty or len(hist) < 2:
            return None

        mapping = resolve_symbol(symbol)
        current_price = float(hist['Close'].iloc[-1])
        prev_close = float(hist['Close'].iloc[-2])
        if current_price < self.min_price:
            return None

        volume = int(hist['Volume'].iloc[-1])
        avg_volume = float(hist['Volume'].tail(5).mean())
        if avg_volume < self.min_avg_volume:
            return None

        change_percent = ((current_price - prev_close) / prev_close) * 100
        volume_ratio = volume / avg_volume if avg_volume > 0 else 0
        is_gap_up = current_price > float(hist['High'].iloc[-2])
        is_gap_down = current_price < float(hist['Low'].iloc[-2])
        liquidity_score = min(30.0, avg_volume / self.min_avg_volume * 10)
        momentum_score = abs(change_percent) * min(volume_ratio, 5) * 10
        gap_score = 10 if is_gap_up or is_gap_down else 0
        total_score = round(momentum_score + liquidity_score + gap_score, 2)
        reasons = self._candidate_reasons(change_percent, volume_ratio, is_gap_up, is_gap_down, avg_volume)

        return {
            "symbol": mapping.canonical,
            "yahoo_symbol": mapping.yahoo,
            "breeze_stock_code": mapping.breeze,
            "current_price": round(current_price, 2),
            "change_percent": round(change_percent, 2),
            "volume": volume,
            "avg_volume": int(avg_volume),
            "volume_ratio": round(volume_ratio, 2),
            "momentum_score": round(momentum_score, 2),
            "liquidity_score": round(liquidity_score, 2),
            "gap_score": gap_score,
            "watchlist_score": total_score,
            "direction_bias": "bullish" if change_percent > 0 else "bearish" if change_percent < 0 else "neutral",
            "is_gap_up": bool(is_gap_up),
            "is_gap_down": bool(is_gap_down),
            "reasons": reasons,
        }
    
    def scan_stocks(self) -> List[Dict[str, Any]]:
        """
        Scan all stocks and return top candidates for today's watchlist.
        Uses momentum score (price change * volume ratio) for ranking.
        """
        import yfinance as yf

        stocks = self._filter_excluded_symbols(self.get_nifty_stocks())
        candidates = []
        
        for stock in stocks:
            try:
                mapping = resolve_symbol(stock)
                ticker = yf.Ticker(mapping.yahoo)
                hist = ticker.history(period="5d")
                candidate = self.score_candidate(stock, hist)
                if candidate:
                    candidates.append(candidate)
                
            except Exception as e:
                print(f"Error scanning {stock}: {e}")
        
        # Sort by total watchlist score (highest first)
        candidates.sort(key=lambda x: x["watchlist_score"], reverse=True)
        
        # Return top N candidates while keeping configured must-watch names.
        watchlist = self._with_required_candidates(candidates)
        
        # Store in DynamoDB
        self._store_watchlist(watchlist)
        
        return watchlist

    @staticmethod
    def _candidate_reasons(
        change_percent: float,
        volume_ratio: float,
        is_gap_up: bool,
        is_gap_down: bool,
        avg_volume: float,
    ) -> List[str]:
        reasons = []
        if abs(change_percent) >= 1:
            reasons.append(f"price move {change_percent:.2f}%")
        if volume_ratio >= 1.5:
            reasons.append(f"relative volume {volume_ratio:.2f}x")
        if is_gap_up:
            reasons.append("gap up versus previous high")
        if is_gap_down:
            reasons.append("gap down versus previous low")
        reasons.append(f"avg volume {int(avg_volume)}")
        return reasons
    
    def _store_watchlist(self, watchlist: List[Dict[str, Any]]):
        """Store pre-market watchlist in DynamoDB."""
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        
        item = get_daily_state(self.market_state_db, today, "watchlist")
        
        item["pre_market_watchlist"] = watchlist
        item["watchlist_size"] = len(watchlist)
        item["updated_at"] = now.isoformat()
        
        put_daily_state(self.market_state_db, today, "watchlist", item)
        print(f"✅ Stored pre-market watchlist for {today} ({len(watchlist)} stocks)")
    
    def get_watchlist(self) -> List[str]:
        """Retrieve today's watchlist from DynamoDB."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        item = get_daily_state(self.market_state_db, today, "watchlist")
        
        watchlist = item.get("pre_market_watchlist", [])
        if watchlist:
            return self._with_required_symbols([w["symbol"] for w in watchlist])
        
        # Fallback to default watchlist
        print("⚠️ No pre-market watchlist found, using default")
        # Previous broader fallback:
        # ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
        #  "SBIN", "BHARTIARTL", "KOTAKBANK", "BAJFINANCE", "ITC"]
        return self._with_required_symbols([
            "RELIANCE", "INFY", "ICICIBANK", "BHARTIARTL",
            "MARUTI", "JSWSTEEL", "BAJAJFINSV", "ASIANPAINT"
        ])
