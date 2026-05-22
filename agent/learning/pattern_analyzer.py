"""
Pattern Analyzer - Learns from past trades to identify winning patterns.
Stores patterns in LearningTable (DynamoDB) for confidence adjustment.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import boto3

class PatternAnalyzer:
    """Analyzes historical trades to identify profitable patterns."""
    
    def __init__(self):
        self.region = os.environ.get("AWS_REGION", "eu-west-2")
        self.trades_table = os.environ.get("TRADES_TABLE", "svc-trd-trades-dev")
        self.learning_table = os.environ.get("LEARNING_TABLE", "svc-trd-learning-dev")
        
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.trades_db = self.dynamodb.Table(self.trades_table)
        self.learning_db = self.dynamodb.Table(self.learning_table)
    
    def analyze_patterns(self, days: int = 30) -> Dict[str, Any]:
        """
        Analyze trades from last N days to identify patterns.
        Returns pattern statistics for confidence adjustment.
        """
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Scan trades from last N days
        response = self.trades_db.scan()
        trades = response.get('Items', [])
        trades = [t for t in trades if t.get('timestamp', '') > cutoff_date]
        trades = [t for t in trades if t.get('tradeId') != 'bot_state']
        
        if not trades:
            return {"patterns": [], "total_trades": 0}
        
        patterns = {
            "rsi_buckets": self._analyze_rsi_patterns(trades),
            "sentiment_buckets": self._analyze_sentiment_patterns(trades),
            "confidence_buckets": self._analyze_confidence_patterns(trades),
            "stock_performance": self._analyze_stock_performance(trades),
            "total_trades": len(trades),
            "winning_trades": sum(1 for t in trades if float(t.get('pnl', 0)) > 0),
            "total_pnl": sum(float(t.get('pnl', 0)) for t in trades)
        }
        
        # Store patterns in learning table
        self._store_patterns(patterns)
        
        return patterns
    
    def _analyze_rsi_patterns(self, trades: List[Dict]) -> Dict[str, Any]:
        """Group trades by RSI range and calculate win rates."""
        rsi_ranges = {
            "0-30": {"trades": 0, "wins": 0, "total_pnl": 0},
            "30-40": {"trades": 0, "wins": 0, "total_pnl": 0},
            "40-50": {"trades": 0, "wins": 0, "total_pnl": 0},
            "50-60": {"trades": 0, "wins": 0, "total_pnl": 0},
            "60-70": {"trades": 0, "wins": 0, "total_pnl": 0},
            "70-100": {"trades": 0, "wins": 0, "total_pnl": 0},
        }
        
        for trade in trades:
            rsi = float(trade.get('rsi_at_entry', 50))
            pnl = float(trade.get('pnl', 0))
            is_win = pnl > 0
            
            if rsi <= 30:
                bucket = "0-30"
            elif rsi <= 40:
                bucket = "30-40"
            elif rsi <= 50:
                bucket = "40-50"
            elif rsi <= 60:
                bucket = "50-60"
            elif rsi <= 70:
                bucket = "60-70"
            else:
                bucket = "70-100"
            
            rsi_ranges[bucket]["trades"] += 1
            if is_win:
                rsi_ranges[bucket]["wins"] += 1
            rsi_ranges[bucket]["total_pnl"] += pnl
        
        # Calculate win rates
        for bucket in rsi_ranges:
            trades_count = rsi_ranges[bucket]["trades"]
            if trades_count > 0:
                rsi_ranges[bucket]["win_rate"] = (rsi_ranges[bucket]["wins"] / trades_count) * 100
                rsi_ranges[bucket]["avg_pnl"] = rsi_ranges[bucket]["total_pnl"] / trades_count
            else:
                rsi_ranges[bucket]["win_rate"] = 0
                rsi_ranges[bucket]["avg_pnl"] = 0
        
        return rsi_ranges
    
    def _analyze_sentiment_patterns(self, trades: List[Dict]) -> Dict[str, Any]:
        """Group trades by sentiment score and calculate win rates."""
        sentiment_buckets = {
            "very_bearish": {"trades": 0, "wins": 0, "total_pnl": 0, "range": [-1.0, -0.5]},
            "bearish": {"trades": 0, "wins": 0, "total_pnl": 0, "range": [-0.5, -0.2]},
            "neutral": {"trades": 0, "wins": 0, "total_pnl": 0, "range": [-0.2, 0.2]},
            "bullish": {"trades": 0, "wins": 0, "total_pnl": 0, "range": [0.2, 0.5]},
            "very_bullish": {"trades": 0, "wins": 0, "total_pnl": 0, "range": [0.5, 1.0]},
        }
        
        for trade in trades:
            sentiment = float(trade.get('sentiment_score', 0))
            pnl = float(trade.get('pnl', 0))
            is_win = pnl > 0
            
            if sentiment <= -0.5:
                bucket = "very_bearish"
            elif sentiment <= -0.2:
                bucket = "bearish"
            elif sentiment <= 0.2:
                bucket = "neutral"
            elif sentiment <= 0.5:
                bucket = "bullish"
            else:
                bucket = "very_bullish"
            
            sentiment_buckets[bucket]["trades"] += 1
            if is_win:
                sentiment_buckets[bucket]["wins"] += 1
            sentiment_buckets[bucket]["total_pnl"] += pnl
        
        for bucket in sentiment_buckets:
            trades_count = sentiment_buckets[bucket]["trades"]
            if trades_count > 0:
                sentiment_buckets[bucket]["win_rate"] = (sentiment_buckets[bucket]["wins"] / trades_count) * 100
                sentiment_buckets[bucket]["avg_pnl"] = sentiment_buckets[bucket]["total_pnl"] / trades_count
            else:
                sentiment_buckets[bucket]["win_rate"] = 0
                sentiment_buckets[bucket]["avg_pnl"] = 0
        
        return sentiment_buckets
    
    def _analyze_confidence_patterns(self, trades: List[Dict]) -> Dict[str, Any]:
        """Analyze how confidence scores correlate with outcomes."""
        confidence_ranges = {
            "60-70": {"trades": 0, "wins": 0, "total_pnl": 0},
            "70-80": {"trades": 0, "wins": 0, "total_pnl": 0},
            "80-90": {"trades": 0, "wins": 0, "total_pnl": 0},
            "90-100": {"trades": 0, "wins": 0, "total_pnl": 0},
        }
        
        for trade in trades:
            confidence = float(trade.get('confidence', 50))
            pnl = float(trade.get('pnl', 0))
            is_win = pnl > 0
            
            if confidence < 70:
                bucket = "60-70"
            elif confidence < 80:
                bucket = "70-80"
            elif confidence < 90:
                bucket = "80-90"
            else:
                bucket = "90-100"
            
            confidence_ranges[bucket]["trades"] += 1
            if is_win:
                confidence_ranges[bucket]["wins"] += 1
            confidence_ranges[bucket]["total_pnl"] += pnl
        
        for bucket in confidence_ranges:
            trades_count = confidence_ranges[bucket]["trades"]
            if trades_count > 0:
                confidence_ranges[bucket]["win_rate"] = (confidence_ranges[bucket]["wins"] / trades_count) * 100
                confidence_ranges[bucket]["avg_pnl"] = confidence_ranges[bucket]["total_pnl"] / trades_count
            else:
                confidence_ranges[bucket]["win_rate"] = 0
                confidence_ranges[bucket]["avg_pnl"] = 0
        
        return confidence_ranges
    
    def _analyze_stock_performance(self, trades: List[Dict]) -> Dict[str, Any]:
        """Calculate win rate per stock."""
        stock_performance = {}
        
        for trade in trades:
            symbol = trade.get('stock_symbol', 'UNKNOWN')
            pnl = float(trade.get('pnl', 0))
            is_win = pnl > 0
            
            if symbol not in stock_performance:
                stock_performance[symbol] = {"trades": 0, "wins": 0, "total_pnl": 0}
            
            stock_performance[symbol]["trades"] += 1
            if is_win:
                stock_performance[symbol]["wins"] += 1
            stock_performance[symbol]["total_pnl"] += pnl
        
        for symbol in stock_performance:
            trades_count = stock_performance[symbol]["trades"]
            if trades_count > 0:
                stock_performance[symbol]["win_rate"] = (stock_performance[symbol]["wins"] / trades_count) * 100
                stock_performance[symbol]["avg_pnl"] = stock_performance[symbol]["total_pnl"] / trades_count
        
        return stock_performance
    
    def _store_patterns(self, patterns: Dict[str, Any]):
        """Store pattern analysis results in LearningTable."""
        item = {
            "pattern_id": f"daily_pattern_{datetime.utcnow().strftime('%Y%m%d')}",
            "date": datetime.utcnow().isoformat(),
            "patterns": json.dumps(patterns),
            "total_trades": patterns.get("total_trades", 0),
            "winning_trades": patterns.get("winning_trades", 0),
            "total_pnl": patterns.get("total_pnl", 0),
            "win_rate": (patterns.get("winning_trades", 0) / patterns.get("total_trades", 1)) * 100
        }
        
        self.learning_db.put_item(Item=item)
        print(f"✅ Stored pattern analysis for {item['date']}")
    
    def get_best_rsi_range(self) -> tuple:
        """Get the RSI range with highest win rate."""
        patterns = self._get_latest_patterns()
        if not patterns:
            return (30, 40)  # Default
        
        rsi_patterns = patterns.get("rsi_buckets", {})
        best_range = None
        best_win_rate = 0
        
        for bucket, data in rsi_patterns.items():
            if data.get("win_rate", 0) > best_win_rate and data.get("trades", 0) > 5:
                best_win_rate = data["win_rate"]
                best_range = bucket
        
        if best_range == "0-30":
            return (0, 30)
        elif best_range == "30-40":
            return (30, 40)
        elif best_range == "40-50":
            return (40, 50)
        elif best_range == "50-60":
            return (50, 60)
        elif best_range == "60-70":
            return (60, 70)
        else:
            return (70, 100)
    
    def _get_latest_patterns(self) -> Optional[Dict]:
        """Get the most recent pattern analysis."""
        response = self.learning_db.scan(Limit=1)
        items = response.get('Items', [])
        if items:
            return json.loads(items[0].get('patterns', '{}'))
        return None