"""
Multi-Agent Trading System for NSE India

Components:
- TradingBot: Main trading loop with market hours logic
- Specialist Agents: Technical, Sentiment, Fundamentals, Derivatives, Social
- Learning Module: Pattern analysis and confidence adjustment
- Overnight Module: Global macro, news aggregation, pre-market scanning
"""

from agent.main import TradingBot
from agent.learning.pattern_analyzer import PatternAnalyzer
from agent.learning.confidence_adjuster import ConfidenceAdjuster
from agent.overnight.pre_market_scanner import PreMarketScanner
from agent.overnight.global_macro import GlobalMacroCollector
from agent.overnight.news_aggregator import NewsAggregator

__all__ = [
    "TradingBot",
    "PatternAnalyzer",
    "ConfidenceAdjuster",
    "PreMarketScanner",
    "GlobalMacroCollector",
    "NewsAggregator",
]