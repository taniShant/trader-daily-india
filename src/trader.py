import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # Python 3.9+

# 1. ICICI Breeze API connection
from breeze_connect import BreezeConnect

# 2. AI & Analysis Libraries
from strands import Agent, tool
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import feedparser
import requests

# --- Configuration: Add your actual API keys here ---
ICICI_API_KEY = "YOUR_ICICI_API_KEY"
ICICI_SECRET_KEY = "YOUR_ICICI_SECRET_KEY"
ICICI_SESSION_TOKEN = "YOUR_SESSION_TOKEN"
NEWS_API_KEY = "YOUR_NEWSDATA.IO_API_KEY"  # You can get a free tier

# This is a pre-defined list available in many libraries like yfinance
nifty_50_symbols = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "HINDUNILVR.NS",
    "ICICIBANK.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS", "BAJFINANCE.NS"
    # ... you would have all 50 here
]

def get_daily_trading_signal_for_universe():
    """Scans the liquid universe and generates signals for the best candidates."""
    
    # 1. Define your universe (e.g., NIFTY 50)
    # You can fetch this dynamically from an API or keep it as a list.
    liquid_universe = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"] # Add all 50 here

    # 2. Quick Pre-screening based on Volume & Volatility
    # This avoids running expensive analysis on dead stocks.
    top_candidates = []
    for stock in liquid_universe:
        # Fetch just today's data or recent volume
        data = get_historical_data(stock, days=5)
        if data is not None and not data.empty:
            avg_volume = data['volume'].mean()
            if avg_volume > 100000: # Only consider if volume > 100,000 shares
                top_candidates.append(stock)

    # 3. Run Full Analysis Only on the Shortlisted Candidates
    final_signals = []
    for stock in top_candidates:
        print(f"\n--- Running Full Analysis on {stock} ---")
        signal = get_daily_trading_signal(stock) # Your original analysis function
        final_signals.append({"stock": stock, "signal": signal})
    
    return final_signals

# --- Initialize the ICICI Breeze SDK ---
breeze = BreezeConnect(api_key=ICICI_API_KEY)
breeze.generate_session(api_secret=ICICI_SECRET_KEY,
                        session_token=ICICI_SESSION_TOKEN)
print("✅ Connected to ICICI Direct Breeze API.")

# --- 1. Function to Fetch Data from ICICI Direct ---
def get_historical_data(stock_symbol, days=30):
    """Fetches historical OHLCV data for a given stock from ICICI Direct."""
    end_date = datetime.now(ZoneInfo("Asia/Kolkata"))
    start_date = end_date - timedelta(days=days)
    
    # Format dates as required by Breeze API (ISO8601)
    from_date_str = start_date.strftime('%Y-%m-%dT06:00:00.000Z')
    to_date_str = end_date.strftime('%Y-%m-%dT06:00:00.000Z')
    
    print(f"📥 Fetching data for {stock_symbol}...")
    # The actual API call as per breeze-connect documentation [citation:1][citation:7]
    # This is a conceptual example. Refer to official docs for exact method.
    data = breeze.get_historical_data(
        interval="day",
        from_date=from_date_str,
        to_date=to_date_str,
        stock_code=stock_symbol,
        exchange_code="NSE"
    )
    
    if data.get('Success') and data.get('data'):
        df = pd.DataFrame(data['data'])
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.rename(columns={'datetime': 'date', 'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'volume': 'volume'})
        df.set_index('date', inplace=True)
        return df
    else:
        print(f"⚠️ Failed to fetch data: {data.get('Error', 'Unknown error')}")
        return None

# --- 2. AI-Powered Analysis Tools (Using Strands Agent Framework) ---

# Initialize the FinBERT model for sentiment analysis [citation:10]
tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")

def get_sentiment(text):
    """Analyzes sentiment of a given text using FinBERT."""
    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True)
    outputs = model(**inputs)
    scores = torch.nn.functional.softmax(outputs.logits, dim=-1)
    sentiment_score = {
        "positive": scores[0][0].item(),
        "neutral": scores[0][1].item(),
        "negative": scores[0][2].item(),
    }
    sentiment = max(sentiment_score, key=sentiment_score.get)
    return sentiment, sentiment_score[sentiment]


from strands import Agent, tool

@tool
def get_company_fundamentals(stock_symbol: str) -> dict:
    """
    Fetch fundamental data using Yahoo Finance (yfinance)
    """
    import yfinance as yf
    
    ticker = yf.Ticker(f"{stock_symbol}.NS")  # NSE suffix
    info = ticker.info
    
    return {
        "pe_ratio": info.get("trailingPE"),
        "market_cap": info.get("marketCap"),
        "dividend_yield": info.get("dividendYield"),
        "52_week_high": info.get("fiftyTwoWeekHigh"),
        "52_week_low": info.get("fiftyTwoWeekLow"),
        "recommendation": info.get("recommendationKey")  # buy/hold/sell from analysts
    }

# First, download NRC Emotion Lexicon
# https://saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm

def get_emotion_scores(text: str) -> dict:
    """
    Map text to finance-relevant emotions [citation:3]
    """
    emotions = {
        "fear": 0, "greed": 0, "optimism": 0, 
        "panic": 0, "confidence": 0, "uncertainty": 0
    }
    
    # Tokenize and match against emotion lexicon
    # ... implementation
    
    return emotions

@tool
def get_social_sentiment(stock_symbol: str) -> dict:
    """
    Fetch Reddit/Discord mentions for a stock
    """
    # Using Reddit API (requires credentials)
    import praw
    
    reddit = praw.Reddit(
        client_id="YOUR_ID",
        client_secret="YOUR_SECRET",
        user_agent="trading_bot"
    )
    
    subreddit = reddit.subreddit("IndianStreetBets")  # or "DalalStreetTalks"
    mentions = []
    
    for post in subreddit.search(stock_symbol, limit=50):
        mentions.append({
            "title": post.title,
            "score": post.score,
            "num_comments": post.num_comments
        })
    
    # Analyze sentiment of these mentions
    return {"mentions_count": len(mentions), "data": mentions}

# ============================================================
# SPECIALIST AGENT 1: Technical Analysis
# ============================================================
tech_agent = Agent(
    tools=[calculate_rsi, calculate_macd, calculate_bollinger],
    system_prompt="You are a technical analyst. Analyze price patterns and indicators."
)

# ============================================================
# SPECIALIST AGENT 2: News & Sentiment (FinBERT + NRC Emotions)
# ============================================================
news_agent = Agent(
    tools=[get_stock_specific_news, analyze_finbert_sentiment, get_emotion_scores],
    system_prompt="You analyze news sentiment using FinBERT and detect market emotions like fear/greed."
)

# ============================================================
# SPECIALIST AGENT 3: Company Fundamentals
# ============================================================
fundamental_agent = Agent(
    tools=[get_company_fundamentals, get_analyst_ratings],
    system_prompt="You analyze company financials, P/E ratios, and growth metrics."
)

# ============================================================
# SPECIALIST AGENT 4: Social/Alternative Data
# ============================================================
social_agent = Agent(
    tools=[get_reddit_sentiment, get_twitter_mentions],
    system_prompt="You analyze social media and forum discussions for crowd sentiment."
)

# ============================================================
# COORDINATOR AGENT (Synthesizes all inputs)
# ============================================================
coordinator = Agent(
    tools=[],  # No direct tools - delegates to specialist agents [citation:2]
    system_prompt="""
    You are a senior trading coordinator. Your job:
    1. Delegate to each specialist agent to gather their analysis
    2. Synthesize technical + sentiment + fundamental + social signals
    3. Provide a final BUY/SELL/HOLD recommendation for intraday trading
    4. Include confidence score (0-100) and risk assessment
    
    Trading rules:
    - Intraday only: Square off before 3:20 PM IST
    - Consider stop-loss at 2% below entry
    """
)

# ============================================================
# MAIN EXECUTION
# ============================================================
def get_daily_trading_signal(stock_symbol):
    # Gather all analyses
    tech_signal = tech_agent(f"Analyze {stock_symbol} technicals for today")
    news_signal = news_agent(f"Get news sentiment for {stock_symbol}")
    fundamental_signal = fundamental_agent(f"Get fundamentals for {stock_symbol}")
    social_signal = social_agent(f"Get social sentiment for {stock_symbol}")
    
    # Synthesize
    final_signal = coordinator(f"""
    Stock: {stock_symbol}
    Technical Analysis: {tech_signal}
    News Sentiment: {news_signal}
    Fundamentals: {fundamental_signal}
    Social Sentiment: {social_signal}
    
    Provide final intraday trading signal.
    """)
    
    return final_signal


@tool
def analyze_technical_trends(symbol: str) -> dict:
    """Tool 1: Fetches price data and calculates technical indicators like RSI."""
    df = get_historical_data(symbol, days=30)
    if df is None or df.empty:
        return {"error": "Could not fetch data for analysis."}

    # Calculate 14-day RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = rsi.iloc[-1]
    
    return {
        "current_price": df['close'].iloc[-1],
        "rsi": current_rsi,
        "signal": "overbought" if current_rsi > 70 else "oversold" if current_rsi < 30 else "neutral",
        "suggestion": "Consider BUY on dips" if current_rsi < 30 else "Consider BOOKING PROFITS" if current_rsi > 70 else "HOLD"
    }

@tool
def analyze_market_sentiment(symbol: str) -> dict:
    """Tool 2: Fetches latest Indian market news and performs sentiment analysis."""
    # Using NewsData.io as seen in the reference trading bot [citation:10]
    news_url = f"https://newsdata.io/api/1/news?country=in&category=business&apikey={NEWS_API_KEY}"
    response = requests.get(news_url)
    news_articles = response.json().get('results', [])[:10]  # Get top 10 news
    
    if not news_articles:
        return {"sentiment": "neutral", "confidence": 0.5, "headlines": []}
    
    sentiments = []
    headlines = []
    for article in news_articles:
        title = article['title']
        sentiment, score = get_sentiment(title)
        sentiments.append(score)
        headlines.append(f"{title} ({sentiment}: {score:.2f})")
    
    avg_sentiment_score = np.mean(sentiments)
    overall_sentiment = "positive" if avg_sentiment_score > 0.6 else "negative" if avg_sentiment_score < 0.4 else "neutral"
    
    return {
        "sentiment": overall_sentiment,
        "confidence": avg_sentiment_score,
        "headlines": headlines
    }

# --- 3. Create the Orchestrator Agent ---
# This agent will use the tools above to make a final decision [citation:2][citation:9]
orchestrator = Agent(
    tools=[analyze_technical_trends, analyze_market_sentiment],
    system_prompt="""You are a senior trading advisor for the Indian stock market.
    Your task is to analyze a given stock ticker and provide a clear, actionable **BUY, SELL, or HOLD** signal for intraday trading.
    Base your decision on a combination of technical trends and market sentiment.
    Provide a final confidence score (0-100) and a brief, bullet-pointed justification.
    """
)

# --- 4. Main Loop to Generate a Signal for a Stock ---
def get_daily_trading_signal(stock_symbol):
    """Main function that orchestrates the entire analysis and returns a signal."""
    print(f"\n{'='*60}")
    print(f"🤖 Generating Intraday Signal for: {stock_symbol}")
    print(f"⏰ Time: {datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')} IST")
    print(f"{'='*60}")

    # Run the orchestrator agent
    prompt = f"Analyze the stock {stock_symbol} for intraday trading. Provide a final BUY/SELL/HOLD signal."
    response = orchestrator(prompt)
    
    print("\n✨ Final Analysis & Recommendation:")
    print(response)
    
    # --- Optional: Print a summary table for your review ---
    print(f"\n📋 Summary for Manual Order on ICICI Direct:")
    print(f"1. Action: Based on the signal above.")
    print(f"2. Square-off: Before 3:20 PM IST (Intraday).")
    print("\n⚠️ DISCLAIMER: This is an AI-generated suggestion. You are responsible for your own trading decisions.")
    
    return response

# --- Run the system ---
if __name__ == "__main__":
    # List of stocks you want to analyze [citation:6]
    watchlist = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]
    for stock in watchlist:
        signal = get_daily_trading_signal(stock)
        # Add a small delay to be respectful of API rate limits [citation:4]
        # time.sleep(2)

