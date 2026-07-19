"""
News Fetcher - Fetches news from various sources for sentiment analysis.
Supports NewsAPI, RSS feeds, and fallback simulated data.
"""

import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
import requests
from collections import deque

from agent.config import settings


class NewsSourceUnavailable(RuntimeError):
    """Raised when a required production news source is unavailable."""


class NewsFetcher:
    """
    Fetches financial news from multiple sources.
    Used by Sentiment Analyst during market hours.
    """
    
    def __init__(self):
        self.news_api_key = os.environ.get("NEWS_API_KEY") or settings.apis.news_api_key or ""
        self.allow_simulated_news = _allow_simulated_news()
        self.seen_headlines = deque(maxlen=500)  # Avoid duplicates
        
        # Keywords for filtering relevant financial news
        self.relevant_keywords = [
            "stock", "market", "nifty", "sensex", "rbi", "sebi", "reliance",
            "tcs", "infosys", "hdfc", "icici", "sbi", "bharti", "tatamotors"
        ]
    
    def fetch_india_news(self, minutes_back: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch recent Indian financial news.
        
        Args:
            minutes_back: How many minutes back to fetch news from
            
        Returns:
            List of news articles with title, source, url, published_at
        """
        news_items = []
        
        if not self.news_api_key:
            return self._fallback_news("india", self._get_simulated_news)
        
        from_time = (datetime.utcnow() - timedelta(minutes=minutes_back)).strftime("%Y-%m-%dT%H:%M:%S")
        
        queries = [
            "NIFTY 50",
            "BSE SENSEX",
            "Indian stock market",
            "RBI monetary policy",
            "SEBI",
            "India economy",
            "banking sector India",
            "IT sector India",
            "pharma sector India",
            "auto sector India"
        ]
        
        for query in queries:
            url = f"https://newsapi.org/v2/everything?q={query}&apiKey={self.news_api_key}&language=en&pageSize=10&sortBy=publishedAt&from={from_time}"
            
            try:
                response = requests.get(url, timeout=15)
                if response.status_code == 200:
                    articles = response.json().get("articles", [])
                    for article in articles:
                        title = article.get("title", "")
                        # Filter relevant news
                        if self._is_relevant_news(title):
                            news_item = {
                                "title": title,
                                "url": article.get("url", ""),
                                "source": article.get("source", {}).get("name", "Unknown"),
                                "published_at": article.get("publishedAt", ""),
                                "description": article.get("description", "")[:200],
                                "category": self._categorize_news(title)
                            }
                            if news_item["title"] not in self.seen_headlines:
                                self.seen_headlines.append(news_item["title"])
                                news_items.append(news_item)
            except Exception as e:
                print(f"Error fetching news for {query}: {e}")
            
            time.sleep(0.5)  # Rate limit protection
        
        # Return unique items
        return self._deduplicate_news(news_items)[:30] or self._fallback_news("india", self._get_simulated_news)
    
    def fetch_company_news(self, stock_symbol: str) -> List[Dict[str, Any]]:
        """
        Fetch news specific to a company/stock.
        
        Args:
            stock_symbol: Stock symbol (e.g., RELIANCE, TCS)
            
        Returns:
            List of news articles about the company
        """
        news_items = []
        
        if not self.news_api_key:
            return self._fallback_news("company", lambda: self._get_simulated_company_news(stock_symbol), stock_symbol)
        
        # Company name mapping for better search
        company_names = {
            "RELIANCE": "Reliance Industries",
            "TCS": "Tata Consultancy Services",
            "HDFCBANK": "HDFC Bank",
            "INFY": "Infosys",
            "ICICIBANK": "ICICI Bank",
            "SBIN": "State Bank of India",
            "BHARTIARTL": "Bharti Airtel",
            "KOTAKBANK": "Kotak Mahindra Bank",
            "BAJFINANCE": "Bajaj Finance",
            "ITC": "ITC Limited"
        }
        
        company_name = company_names.get(stock_symbol, stock_symbol)
        
        url = f"https://newsapi.org/v2/everything?q={company_name}+stock&apiKey={self.news_api_key}&language=en&pageSize=8&sortBy=publishedAt"
        
        try:
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                articles = response.json().get("articles", [])
                for article in articles[:5]:
                    news_items.append({
                        "title": article.get("title", ""),
                        "url": article.get("url", ""),
                        "source": article.get("source", {}).get("name", "Unknown"),
                        "published_at": article.get("publishedAt", ""),
                        "stock": stock_symbol,
                        "category": "company"
                    })
        except Exception as e:
            print(f"Error fetching company news for {stock_symbol}: {e}")
        
        return news_items[:10] or self._fallback_news("company", lambda: self._get_simulated_company_news(stock_symbol), stock_symbol)
    
    def fetch_sector_news(self) -> List[Dict[str, Any]]:
        """
        Fetch sector-wise news (Banking, IT, Pharma, Auto, Energy).
        
        Returns:
            List of sector news with sector classification
        """
        sectors = {
            "banking": ["bank", "banking", "credit", "loan", "npa", "rbi"],
            "it": ["it", "software", "technology", "digital", "cloud"],
            "pharma": ["pharma", "drug", "medicine", "healthcare", "vaccine"],
            "auto": ["auto", "car", "vehicle", "automobile", "ev"],
            "energy": ["energy", "oil", "gas", "renewable", "power"],
            "metals": ["metal", "steel", "aluminum", "mining"]
        }
        
        all_sector_news = []
        
        if self.news_api_key:
            for sector, keywords in sectors.items():
                query = f"{sector} sector India"
                url = f"https://newsapi.org/v2/everything?q={query}&apiKey={self.news_api_key}&language=en&pageSize=5"
                
                try:
                    response = requests.get(url, timeout=15)
                    if response.status_code == 200:
                        articles = response.json().get("articles", [])
                        for article in articles[:3]:
                            all_sector_news.append({
                                "title": article.get("title", ""),
                                "url": article.get("url", ""),
                                "source": article.get("source", {}).get("name", "Unknown"),
                                "sector": sector,
                                "category": "sector"
                            })
                except Exception as e:
                    print(f"Error fetching {sector} news: {e}")
                
                time.sleep(0.3)
        
        return self._fallback_news("sector", self._get_simulated_sector_news) if not all_sector_news else all_sector_news[:20]
    
    def fetch_global_news(self) -> List[Dict[str, Any]]:
        """
        Fetch global financial news.
        
        Returns:
            List of global news articles
        """
        news_items = []
        
        if self.news_api_key:
            queries = [
                "US markets", "Federal Reserve", "global economy",
                "oil prices", "dollar index", "China economy"
            ]
            
            for query in queries:
                url = f"https://newsapi.org/v2/everything?q={query}&apiKey={self.news_api_key}&language=en&pageSize=5"
                
                try:
                    response = requests.get(url, timeout=15)
                    if response.status_code == 200:
                        articles = response.json().get("articles", [])
                        for article in articles[:3]:
                            news_items.append({
                                "title": article.get("title", ""),
                                "url": article.get("url", ""),
                                "source": article.get("source", {}).get("name", "Unknown"),
                                "category": "global"
                            })
                except Exception as e:
                    print(f"Error fetching global news for {query}: {e}")
        
        return self._fallback_news("global", self._get_simulated_global_news) if not news_items else news_items[:15]
    
    def _is_relevant_news(self, title: str) -> bool:
        """Check if news is relevant to Indian stock market."""
        title_lower = title.lower()
        for keyword in self.relevant_keywords:
            if keyword.lower() in title_lower:
                return True
        return False
    
    def _categorize_news(self, title: str) -> str:
        """Categorize news into type (economy, policy, corporate, market)."""
        title_lower = title.lower()
        
        if any(word in title_lower for word in ["rbi", "monetary", "policy", "sebi", "govt", "budget"]):
            return "policy"
        elif any(word in title_lower for word in ["economy", "gdp", "growth", "inflation", "fii", "dii"]):
            return "economy"
        elif any(word in title_lower for word in ["results", "profit", "loss", "revenue", "acquisition", "merger"]):
            return "corporate"
        else:
            return "market"
    
    def _deduplicate_news(self, news_items: List[Dict]) -> List[Dict]:
        """Remove duplicate news articles."""
        seen = set()
        unique = []
        for item in news_items:
            title = item.get("title", "")
            if title not in seen:
                seen.add(title)
                unique.append(item)
        return unique

    def _fallback_news(self, category: str, factory, stock_symbol: str | None = None) -> List[Dict[str, Any]]:
        if self.allow_simulated_news:
            return [_mark_news_item(item, source_mode="simulated", source_status="simulated") for item in factory()]

        marker = {
            "title": f"{category} news source unavailable",
            "source": "system",
            "category": category,
            "source_mode": "unavailable",
            "source_status": "missing_news_api_key_or_empty_provider_response",
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
        if stock_symbol:
            marker["stock"] = stock_symbol
        return [marker]
    
    # ============================================================
    # SIMULATED NEWS (Fallback when API unavailable)
    # ============================================================
    
    def _get_simulated_news(self) -> List[Dict[str, Any]]:
        """Simulated news for testing when API key is not available."""
        return [
            {
                "title": "NIFTY 50 hits new all-time high amid strong FII inflows",
                "source": "Economic Times",
                "category": "market",
                "published_at": datetime.utcnow().isoformat()
            },
            {
                "title": "RBI keeps repo rate unchanged at 6.5%, maintains neutral stance",
                "source": "Business Standard",
                "category": "policy",
                "published_at": datetime.utcnow().isoformat()
            },
            {
                "title": "India's GDP growth expected to remain strong at 7.5%",
                "source": "Financial Express",
                "category": "economy",
                "published_at": datetime.utcnow().isoformat()
            },
            {
                "title": "IT sector shows signs of revival with new deal wins",
                "source": "Mint",
                "category": "market",
                "published_at": datetime.utcnow().isoformat()
            },
            {
                "title": "Banking stocks rally on strong quarterly results",
                "source": "Hindu Business Line",
                "category": "market",
                "published_at": datetime.utcnow().isoformat()
            }
        ]
    
    def _get_simulated_company_news(self, stock_symbol: str) -> List[Dict[str, Any]]:
        """Simulated company news for testing."""
        simulated = {
            "RELIANCE": {"title": "Reliance announces partnership with NVIDIA for AI infrastructure", "sentiment": "positive"},
            "TCS": {"title": "TCS wins multi-year digital transformation deal", "sentiment": "positive"},
            "HDFCBANK": {"title": "HDFC Bank reports strong deposit growth", "sentiment": "positive"},
            "INFY": {"title": "Infosys launches new AI platform", "sentiment": "positive"},
            "ICICIBANK": {"title": "ICICI Bank announces dividend", "sentiment": "positive"},
        }
        
        info = simulated.get(stock_symbol, {"title": f"{stock_symbol} shows positive momentum", "sentiment": "neutral"})
        
        return [{
            "title": info["title"],
            "source": "Economic Times",
            "stock": stock_symbol,
            "category": "company",
            "published_at": datetime.utcnow().isoformat()
        }]
    
    def _get_simulated_sector_news(self) -> List[Dict[str, Any]]:
        """Simulated sector news for testing."""
        return [
            {"title": "Banking sector sees robust credit growth of 15%", "sector": "banking", "source": "Financial Express"},
            {"title": "IT sector deal wins at record high", "sector": "it", "source": "Mint"},
            {"title": "Pharma exports grow 12% in Q2", "sector": "pharma", "source": "Business Standard"},
            {"title": "Auto sales surge during festive season", "sector": "auto", "source": "Economic Times"},
        ]
    
    def _get_simulated_global_news(self) -> List[Dict[str, Any]]:
        """Simulated global news for testing."""
        return [
            {"title": "Federal Reserve signals potential rate cut in September", "source": "Reuters"},
            {"title": "US jobs data beats expectations, easing recession fears", "source": "Bloomberg"},
            {"title": "China announces stimulus measures to boost economy", "source": "CNBC"},
        ]


# Singleton instance
_news_fetcher = None

def get_news_fetcher() -> NewsFetcher:
    """Get singleton news fetcher instance."""
    global _news_fetcher
    if _news_fetcher is None:
        _news_fetcher = NewsFetcher()
    return _news_fetcher


def _allow_simulated_news() -> bool:
    return os.environ.get("ALLOW_SIMULATED_NEWS", "").lower() in {"1", "true", "yes", "y", "on"} or bool(
        settings.apis.allow_simulated_news
    )


def _mark_news_item(item: Dict[str, Any], *, source_mode: str, source_status: str) -> Dict[str, Any]:
    marked = dict(item)
    marked["source_mode"] = source_mode
    marked["source_status"] = source_status
    return marked
