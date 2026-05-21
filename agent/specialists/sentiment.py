from strands import Agent, tool
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import requests
from datetime import datetime

# Initialize FinBERT model
FINBERT_MODEL = "ProsusAI/finbert"
tokenizer = AutoTokenizer.from_pretrained(FINBERT_MODEL)
finbert = AutoModelForSequenceClassification.from_pretrained(FINBERT_MODEL)

@tool
def get_finbert_sentiment(text: str) -> dict:
    """Analyze sentiment of a single text using FinBERT"""
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    outputs = finbert(**inputs)
    scores = torch.nn.functional.softmax(outputs.logits, dim=-1)
    
    sentiment_map = ["positive", "neutral", "negative"]
    sentiment = sentiment_map[torch.argmax(scores).item()]
    confidence = scores.max().item()
    
    return {"sentiment": sentiment, "confidence": confidence, "text": text[:200]}

@tool
def get_stock_news(stock_symbol: str) -> list:
    """Fetch latest news for a stock"""
    # Using NewsAPI (free tier)
    api_key = os.environ.get("NEWS_API_KEY", "")
    if not api_key:
        return [{"error": "NEWS_API_KEY not configured"}]
    
    url = f"https://newsapi.org/v2/everything?q={stock_symbol}&apiKey={api_key}"
    response = requests.get(url)
    
    if response.status_code == 200:
        articles = response.json().get("articles", [])[:10]
        return [{"title": a["title"], "url": a["url"], "published_at": a["publishedAt"]} for a in articles]
    return []

@tool
def aggregate_news_sentiment(stock_symbol: str) -> dict:
    """Aggregate sentiment across all news for a stock"""
    news_articles = get_stock_news(stock_symbol)
    
    if not news_articles or isinstance(news_articles[0], dict) and "error" in news_articles[0]:
        return {"error": "No news available"}
    
    sentiments = []
    for article in news_articles:
        sentiment = get_finbert_sentiment(article["title"])
        sentiments.append(sentiment)
    
    positive = sum(1 for s in sentiments if s["sentiment"] == "positive")
    negative = sum(1 for s in sentiments if s["sentiment"] == "negative")
    neutral = len(sentiments) - positive - negative
    
    total = len(sentiments)
    overall = "positive" if positive > negative else "negative" if negative > positive else "neutral"
    
    return {
        "overall_sentiment": overall,
        "positive_pct": (positive / total) * 100 if total > 0 else 0,
        "negative_pct": (negative / total) * 100 if total > 0 else 0,
        "neutral_pct": (neutral / total) * 100 if total > 0 else 0,
        "articles_analyzed": total,
        "sentiment_score": (positive - negative) / total if total > 0 else 0  # -1 to +1 scale
    }

class SentimentAnalyst(Agent):
    """Specialist agent for news and sentiment analysis"""
    
    def __init__(self, model, memory):
        super().__init__(
            name="SentimentAnalyst",
            model=model,
            memory=memory,
            tools=[get_finbert_sentiment, get_stock_news, aggregate_news_sentiment],
            system_prompt="""
            You are a sentiment analysis expert for financial markets.
            
            Your job:
            1. Analyze news sentiment for a given stock using FinBERT
            2. Detect market emotions (fear, greed, optimism, panic)
            3. Identify key narratives driving sentiment
            
            Output JSON with:
            - overall_sentiment (bullish/bearish/neutral)
            - sentiment_score (-1 to +1)
            - key_headlines (list of important news)
            - emotion_detected (fear/greed/optimism/panic)
            - recommendation_bias (helps technical analysis)
            """
        )