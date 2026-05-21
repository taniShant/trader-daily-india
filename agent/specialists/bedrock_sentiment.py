"""
Sentiment Analyst using Amazon Bedrock (Claude 3 Haiku)
No PyTorch, no local models - just API calls.
"""

import boto3
import json
import os
from typing import Dict, List, Any
from datetime import datetime

from strands import Agent, tool

# Initialize Bedrock client
bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name=os.environ.get('AWS_REGION', 'eu-west-1')
)

# Model ID for Claude 3 Haiku (fastest, cheapest, great for sentiment)
# Available in eu-west-1 (Ireland) as confirmed [citation:1]
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

@tool
def analyze_sentiment_with_bedrock(news_headline: str) -> Dict[str, float]:
    """
    Analyze sentiment of a news headline using Claude 3 Haiku on Bedrock.
    Returns bullish/bearish/neutral scores.
    """
    prompt = f"""Analyze the sentiment of this financial news headline for stock trading.
    Return ONLY a JSON object with three scores: bullish, neutral, bearish.
    Scores must sum to 100.
    
    Headline: "{news_headline}"
    
    Example response: {{"bullish": 70, "neutral": 20, "bearish": 10}}
    """
    
    # Prepare the request
    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 200,
        "temperature": 0.2,  # Low temperature for consistent scoring
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
    
    # Call Bedrock
    response = bedrock_runtime.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(request_body)
    )
    
    # Parse response
    response_body = json.loads(response['body'].read())
    sentiment_text = response_body['content'][0]['text']
    
    # Extract JSON from response (Claude may add extra text)
    try:
        # Find JSON in the response
        import re
        json_match = re.search(r'\{[^{}]*\}', sentiment_text)
        if json_match:
            sentiment_scores = json.loads(json_match.group())
        else:
            sentiment_scores = {"bullish": 33, "neutral": 34, "bearish": 33}
    except:
        sentiment_scores = {"bullish": 33, "neutral": 34, "bearish": 33}
    
    return sentiment_scores

@tool
def get_stock_sentiment_bedrock(stock_symbol: str) -> Dict[str, Any]:
    """
    Get aggregate sentiment for a stock by analyzing recent news headlines.
    Uses Bedrock for all analysis - no local ML models.
    """
    # Fetch news headlines (using existing news function)
    from tools.news_fetcher import get_stock_news
    
    news_articles = get_stock_news(stock_symbol)
    
    if not news_articles:
        return {
            "stock_symbol": stock_symbol,
            "overall_sentiment": "neutral",
            "confidence": 0,
            "articles_analyzed": 0,
            "error": "No news found"
        }
    
    # Analyze each headline with Bedrock
    sentiments = []
    for article in news_articles[:10]:  # Limit to 10 headlines per call
        headline = article.get("title", "")
        if headline:
            sentiment = analyze_sentiment_with_bedrock(headline)
            sentiments.append(sentiment)
    
    # Aggregate results
    if sentiments:
        avg_bullish = sum(s.get("bullish", 0) for s in sentiments) / len(sentiments)
        avg_bearish = sum(s.get("bearish", 0) for s in sentiments) / len(sentiments)
        
        if avg_bullish > avg_bearish + 10:
            overall = "bullish"
        elif avg_bearish > avg_bullish + 10:
            overall = "bearish"
        else:
            overall = "neutral"
        
        sentiment_score = (avg_bullish - avg_bearish) / 100  # -1 to +1 scale
        
        return {
            "stock_symbol": stock_symbol,
            "overall_sentiment": overall,
            "sentiment_score": sentiment_score,
            "bullish_score": avg_bullish,
            "bearish_score": avg_bearish,
            "neutral_score": 100 - avg_bullish - avg_bearish,
            "articles_analyzed": len(sentiments),
            "method": "Amazon Bedrock Claude 3 Haiku"
        }
    
    return {
        "stock_symbol": stock_symbol,
        "overall_sentiment": "neutral",
        "sentiment_score": 0,
        "articles_analyzed": 0
    }

class BedrockSentimentAnalyst(Agent):
    """Specialist agent using Amazon Bedrock for sentiment analysis"""
    
    def __init__(self, model, memory):
        super().__init__(
            name="BedrockSentimentAnalyst",
            model=model,
            memory=memory,
            tools=[get_stock_sentiment_bedrock, analyze_sentiment_with_bedrock],
            system_prompt="""
            You are a sentiment analysis expert using Amazon Bedrock's Claude 3.
            
            Your job: Analyze news sentiment for stocks using Bedrock API calls.
            Benefits over local models:
            - No infrastructure to manage
            - 1-second response time [citation:3][citation:5]
            - Multi-language support (25+ languages) [citation:3][citation:5]
            - No PyTorch or GPU requirements
            
            For each stock, call get_stock_sentiment_bedrock to get sentiment scores.
            Return bullish/bearish/neutral with confidence.
            """
        )