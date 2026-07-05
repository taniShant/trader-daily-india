from typing import Any, Dict

from strands import Agent, tool


@tool
def get_social_sentiment(stock_symbol: str) -> Dict[str, Any]:
    """Return a neutral placeholder until social data sources are configured."""
    return {
        "stock_symbol": stock_symbol,
        "overall_sentiment": "neutral",
        "sentiment_score": 0.0,
        "mentions_count": 0,
        "source": "not_configured",
    }


class SocialAnalyst(Agent):
    """Specialist agent for social sentiment analysis."""

    def __init__(self, model, memory=None):
        super().__init__(
            name="SocialAnalyst",
            model=model,
            tools=[get_social_sentiment],
            system_prompt="""
            You are a social sentiment analyst for Indian equities.

            Social data sources are optional. If reliable social data is unavailable,
            return neutral sentiment and clearly mark the source as not configured.

            Output JSON with:
            - overall_sentiment (bullish/bearish/neutral)
            - sentiment_score (-1 to +1)
            - mentions_count
            - source
            """,
        )
