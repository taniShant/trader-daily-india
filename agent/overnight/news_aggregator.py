"""
News Aggregator - Real-time news scanning during market hours + overnight batch.
"""

import os
import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import boto3

from agent.overnight.state_store import get_daily_state, put_daily_state
import requests
from collections import deque

class NewsAggregator:
    """
    Aggregates news from multiple sources.
    - Overnight: Batch collection (once)
    - Market Hours: Real-time scanning every 3 minutes
    """
    
    def __init__(self):
        self.region = os.environ.get("AWS_REGION", "eu-west-2")
        self.market_state_table = os.environ.get("MARKET_STATE_TABLE", "svc-trd-market-state-dev")
        self.news_api_key = os.environ.get("NEWS_API_KEY", "")
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.market_state_db = self.dynamodb.Table(self.market_state_table)
        
        # Track already seen news to avoid duplicates
        self.seen_headlines = deque(maxlen=500)  # Keep last 500 headlines
        self.last_market_hours_scan = None
    
    # ============================================================
    # OVERNIGHT BATCH (Run once before market open)
    # ============================================================
    
    def overnight_aggregate(self) -> Dict[str, Any]:
        """
        Run once overnight (10:30 PM IST) to capture global news.
        """
        print("🌙 Running overnight news aggregation...")
        
        global_news = self._get_global_news()
        india_overnight = self._get_india_overnight_news()
        us_markets = self._get_us_market_summary()
        
        sentiment_score = self._calculate_sentiment(global_news + india_overnight)
        key_headlines = self._extract_key_headlines(global_news[:5] + india_overnight[:5])
        
        overnight_data = {
            "type": "overnight",
            "timestamp": datetime.utcnow().isoformat(),
            "global_news": global_news[:20],
            "india_overnight_news": india_overnight[:15],
            "us_markets": us_markets,
            "sentiment_score": sentiment_score,
            "key_headlines": key_headlines[:10],
        }
        
        self._store_news_data(overnight_data)
        return overnight_data
    
    def _get_us_market_summary(self) -> Dict[str, Any]:
        """Get US market closing summary."""
        try:
            import yfinance as yf
            indices = {
                "^GSPC": "S&P 500",
                "^DJI": "Dow Jones",
                "^IXIC": "NASDAQ"
            }
            summary = {}
            for symbol, name in indices.items():
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="2d")
                if not hist.empty and len(hist) >= 2:
                    current = hist['Close'].iloc[-1]
                    prev = hist['Close'].iloc[-2]
                    change_pct = ((current - prev) / prev) * 100
                    summary[name] = {
                        "close": round(current, 2),
                        "change_percent": round(change_pct, 2)
                    }
            return summary
        except Exception as e:
            print(f"Error fetching US markets: {e}")
            return {}
    
    # ============================================================
    # MARKET HOURS REAL-TIME SCANNING (Every 3 minutes)
    # ============================================================
    
    def real_time_scan(self) -> Dict[str, Any]:
        """
        Scan for breaking news during market hours.
        Called every 3 minutes by the trading bot.
        """
        if self.last_market_hours_scan:
            time_since_last = (datetime.utcnow() - self.last_market_hours_scan).total_seconds()
            if time_since_last < 120:  # Minimum 2 minutes between scans
                return {"new_news": [], "sentiment_update": None}
        
        self.last_market_hours_scan = datetime.utcnow()
        
        print("📡 Real-time news scan (market hours)...")
        
        # Get fresh news from the last 5 minutes
        india_breaking = self._get_india_breaking_news(minutes_back=5)
        sector_news = self._get_sector_news()
        company_news = self._get_company_news_realtime()
        
        # Filter out already seen news
        new_news = self._filter_new_headlines(india_breaking + sector_news + company_news)
        
        # Calculate real-time sentiment impact
        sentiment_update = self._calculate_sentiment(new_news) if new_news else None
        
        realtime_data = {
            "type": "realtime",
            "timestamp": datetime.utcnow().isoformat(),
            "new_news_count": len(new_news),
            "new_news": new_news[:20],
            "sentiment_update": sentiment_update,
            "has_breaking": len(new_news) > 0
        }
        
        # Store real-time updates (keep rolling for last 24 hours)
        self._store_realtime_update(realtime_data)
        
        return realtime_data
    
    def _get_india_breaking_news(self, minutes_back: int = 5) -> List[Dict[str, Any]]:
        """Fetch breaking Indian financial news from last N minutes."""
        news_items = []
        
        if not self.news_api_key:
            return self._get_simulated_breaking_news()
        
        # Use 'from' parameter to get news since last scan
        from_time = (datetime.utcnow() - timedelta(minutes=minutes_back)).strftime("%Y-%m-%dT%H:%M:%S")
        
        queries = [
            "NIFTY 50", "BSE SENSEX", "Indian stock market",
            "RBI", "SEBI", "India economy",
            "banking", "IT sector", "pharma"
        ]
        
        for query in queries:
            url = f"https://newsapi.org/v2/everything?q={query}&apiKey={self.news_api_key}&language=en&pageSize=10&sortBy=publishedAt&from={from_time}"
            try:
                response = requests.get(url, timeout=15)
                if response.status_code == 200:
                    articles = response.json().get("articles", [])
                    for a in articles:
                        published = a.get("publishedAt", "")
                        if published > from_time:
                            news_items.append({
                                "title": a["title"],
                                "url": a["url"],
                                "source": a["source"]["name"],
                                "published_at": published,
                                "category": "india",
                                "urgency": "breaking" if "breaking" in a["title"].lower() else "normal"
                            })
            except Exception as e:
                print(f"Error fetching breaking news for {query}: {e}")
        
        # Deduplicate
        seen_titles = set()
        unique_items = []
        for item in news_items:
            if item["title"] not in seen_titles:
                seen_titles.add(item["title"])
                unique_items.append(item)
        
        return unique_items[:15]
    
    def _get_sector_news(self) -> List[Dict[str, Any]]:
        """Fetch sector-specific news (Banking, IT, Pharma, Auto, Energy)."""
        sectors = ["banking", "IT", "pharma", "auto", "energy", "metals"]
        news_items = []
        
        if self.news_api_key:
            for sector in sectors:
                url = f"https://newsapi.org/v2/everything?q={sector}+sector+India&apiKey={self.news_api_key}&language=en&pageSize=5"
                try:
                    response = requests.get(url, timeout=15)
                    if response.status_code == 200:
                        articles = response.json().get("articles", [])
                        for a in articles[:3]:
                            news_items.append({
                                "title": a["title"],
                                "url": a["url"],
                                "source": a["source"]["name"],
                                "category": "sector",
                                "sector": sector
                            })
                except Exception as e:
                    print(f"Error fetching {sector} news: {e}")
        
        return self._get_simulated_sector_news() if not news_items else news_items[:10]
    
    def _get_company_news_realtime(self) -> List[Dict[str, Any]]:
        """Fetch real-time company news for NIFTY 50 stocks."""
        top_stocks = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "BHARTIARTL"]
        news_items = []
        
        if self.news_api_key:
            for stock in top_stocks:
                url = f"https://newsapi.org/v2/everything?q={stock}+stock&apiKey={self.news_api_key}&language=en&pageSize=3"
                try:
                    response = requests.get(url, timeout=15)
                    if response.status_code == 200:
                        articles = response.json().get("articles", [])
                        for a in articles[:2]:
                            news_items.append({
                                "title": a["title"],
                                "url": a["url"],
                                "source": a["source"]["name"],
                                "stock": stock,
                                "category": "company"
                            })
                except Exception as e:
                    print(f"Error fetching {stock} news: {e}")
        
        return self._get_simulated_company_news() if not news_items else news_items[:15]
    
    def _filter_new_headlines(self, news_items: List[Dict]) -> List[Dict]:
        """Filter out headlines already seen."""
        new_items = []
        for item in news_items:
            title = item.get("title", "")
            if title not in self.seen_headlines:
                self.seen_headlines.append(title)
                new_items.append(item)
        return new_items
    
    def _calculate_sentiment(self, news_items: List[Dict]) -> float:
        """Calculate sentiment score (-1 to +1) for news items."""
        if not news_items:
            return 0.0
        
        positive_keywords = [
            "surge", "rally", "gain", "profit", "growth", "positive", "up", "high",
            "record", "bullish", "upgrade", "beat", "strong", "opportunity", "boost"
        ]
        negative_keywords = [
            "drop", "fall", "loss", "risk", "negative", "down", "low", "crash",
            "bearish", "downgrade", "miss", "weak", "concern", "volatility", "slump"
        ]
        
        positive_count = 0
        negative_count = 0
        
        for item in news_items:
            title = item.get("title", "").lower()
            for word in positive_keywords:
                if word in title:
                    positive_count += 1
                    break
            for word in negative_keywords:
                if word in title:
                    negative_count += 1
                    break
        
        total = positive_count + negative_count
        if total == 0:
            return 0.0
        
        sentiment = (positive_count - negative_count) / total
        return round(sentiment, 2)
    
    def _extract_key_headlines(self, headlines: List[str]) -> List[str]:
        """Extract top headlines for quick view."""
        return headlines[:10]
    
    # ============================================================
    # SIMULATED NEWS (Fallback when API unavailable)
    # ============================================================
    
    def _get_simulated_breaking_news(self) -> List[Dict[str, Any]]:
        """Simulated breaking news for testing."""
        return [
            {"title": "NIFTY 50 hits new all-time high", "source": "Economic Times", "category": "india", "urgency": "breaking"},
            {"title": "RBI announces货币政策 decision today", "source": "Business Standard", "category": "india", "urgency": "normal"},
            {"title": "IT stocks rally on strong US demand outlook", "source": "Mint", "category": "sector", "sector": "IT"},
        ]
    
    def _get_simulated_sector_news(self) -> List[Dict[str, Any]]:
        """Simulated sector news for testing."""
        return [
            {"title": "Banking sector sees strong credit growth", "source": "Financial Express", "category": "sector", "sector": "banking"},
            {"title": "Pharma stocks gain on FDA approvals", "source": "Hindu Business Line", "category": "sector", "sector": "pharma"},
            {"title": "Auto sales surge in festive season", "source": "Economic Times", "category": "sector", "sector": "auto"},
        ]
    
    def _get_simulated_company_news(self) -> List[Dict[str, Any]]:
        """Simulated company news for testing."""
        return [
            {"title": "RELIANCE subsidiary announces new partnership", "source": "Economic Times", "stock": "RELIANCE"},
            {"title": "TCS wins new digital transformation deal", "source": "Business Standard", "stock": "TCS"},
            {"title": "HDFCBANK launches new digital lending product", "source": "Financial Express", "stock": "HDFCBANK"},
        ]
    
    def _get_india_overnight_news(self) -> List[Dict[str, Any]]:
        """Fetch Indian news from overnight period."""
        # Similar to _get_india_breaking_news but with larger time window
        return self._get_simulated_india_overnight_news()
    
    def _get_simulated_india_overnight_news(self) -> List[Dict[str, Any]]:
        """Simulated overnight Indian news."""
        return [
            {"title": "Government announces new infrastructure spending", "source": "Economic Times"},
            {"title": "FPIs net buyers in Indian equities", "source": "Business Standard"},
            {"title": "Rupee strengthens against dollar", "source": "Financial Express"},
        ]
    
    def _get_global_news(self) -> List[Dict[str, Any]]:
        """Fetch global news for overnight analysis."""
        return self._get_simulated_global_news()
    
    def _get_simulated_global_news(self) -> List[Dict[str, Any]]:
        """Simulated global news."""
        return [
            {"title": "Federal Reserve signals potential rate cut", "source": "Reuters"},
            {"title": "US jobs data beats expectations", "source": "Bloomberg"},
            {"title": "China announces stimulus measures", "source": "CNBC"},
        ]
    
    # ============================================================
    # DYNAMODB STORAGE
    # ============================================================
    
    def _store_news_data(self, news_data: Dict[str, Any]):
        """Store news data in DynamoDB."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        item = get_daily_state(self.market_state_db, today, "news")
        
        if news_data.get("type") == "overnight":
            item["overnight_news"] = news_data
            item["overnight_sentiment"] = news_data.get("sentiment_score", 0)
            item["overnight_updated_at"] = news_data.get("timestamp")
        else:
            # For real-time, maintain a rolling list
            realtime_updates = item.get("realtime_news_updates", [])
            realtime_updates.append(news_data)
            # Keep last 50 updates
            if len(realtime_updates) > 50:
                realtime_updates = realtime_updates[-50:]
            item["realtime_news_updates"] = realtime_updates
            item["latest_sentiment"] = news_data.get("sentiment_update", item.get("latest_sentiment", 0))
            item["realtime_updated_at"] = news_data.get("timestamp")
        
        put_daily_state(self.market_state_db, today, "news", item)
    
    def _store_realtime_update(self, realtime_data: Dict[str, Any]):
        """Store real-time news update (called every 3 minutes)."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        item = get_daily_state(self.market_state_db, today, "news")
        
        updates = item.get("realtime_news_updates", [])
        updates.append({
            "timestamp": realtime_data["timestamp"],
            "new_news_count": realtime_data["new_news_count"],
            "sentiment_update": realtime_data["sentiment_update"],
            "has_breaking": realtime_data["has_breaking"],
            "headlines": [n["title"] for n in realtime_data["new_news"][:5]]
        })
        
        # Keep last 50 updates
        if len(updates) > 50:
            updates = updates[-50:]
        
        item["realtime_news_updates"] = updates
        item["latest_sentiment"] = realtime_data.get("sentiment_update", item.get("latest_sentiment", 0))
        item["realtime_updated_at"] = realtime_data["timestamp"]
        
        put_daily_state(self.market_state_db, today, "news", item)
    
    def get_latest_sentiment(self) -> float:
        """Get the latest real-time sentiment score."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        item = get_daily_state(self.market_state_db, today, "news")
        return item.get("latest_sentiment", 0.0)
    
    def has_breaking_news(self) -> bool:
        """Check if there was breaking news in the last 3 minutes."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        item = get_daily_state(self.market_state_db, today, "news")
        updates = item.get("realtime_news_updates", [])
        if updates:
            last_update = updates[-1]
            return last_update.get("has_breaking", False)
        return False
