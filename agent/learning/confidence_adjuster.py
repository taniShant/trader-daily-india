"""
Confidence Adjuster - Dynamically adjusts confidence thresholds based on pattern analysis.
"""

import os
from typing import Dict, Any, Optional
import boto3

class ConfidenceAdjuster:
    """Adjusts confidence thresholds based on historical performance."""
    
    def __init__(self):
        self.region = os.environ.get("AWS_REGION", "eu-west-2")
        self.learning_table = os.environ.get("LEARNING_TABLE", "svc-trd-learning-dev")
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.learning_db = self.dynamodb.Table(self.learning_table)
        
        # Default thresholds
        self.base_threshold = int(os.environ.get("MIN_CONFIDENCE_THRESHOLD", 70))
        self.adjustment = 0
    
    def update_from_patterns(self) -> int:
        """Update confidence adjustment based on latest pattern analysis."""
        patterns = self._get_latest_patterns()
        
        if not patterns:
            return self.base_threshold
        
        # Analyze RSI pattern performance
        rsi_patterns = patterns.get("rsi_buckets", {})
        best_rsi_win_rate = 0
        for bucket, data in rsi_patterns.items():
            if data.get("win_rate", 0) > best_rsi_win_rate and data.get("trades", 0) > 5:
                best_rsi_win_rate = data["win_rate"]
        
        # Analyze sentiment pattern performance
        sentiment_patterns = patterns.get("sentiment_buckets", {})
        best_sentiment_win_rate = 0
        for bucket, data in sentiment_patterns.items():
            if data.get("win_rate", 0) > best_sentiment_win_rate and data.get("trades", 0) > 5:
                best_sentiment_win_rate = data["win_rate"]
        
        # Calculate adjustment based on win rates
        avg_win_rate = (best_rsi_win_rate + best_sentiment_win_rate) / 2
        
        if avg_win_rate > 70:
            # Patterns are working well - lower threshold to take more trades
            self.adjustment = -5
        elif avg_win_rate < 50:
            # Patterns are not working - raise threshold to be more selective
            self.adjustment = +10
        else:
            self.adjustment = 0
        
        adjusted_threshold = self.base_threshold + self.adjustment
        adjusted_threshold = max(50, min(90, adjusted_threshold))  # Clamp between 50-90
        
        print(f"📊 Confidence Adjustment: base={self.base_threshold}%, adjustment={self.adjustment}%, new={adjusted_threshold}%")
        print(f"   Avg Win Rate from patterns: {avg_win_rate:.1f}%")
        
        return adjusted_threshold
    
    def _get_latest_patterns(self) -> Optional[Dict]:
        """Get the most recent pattern analysis."""
        import json
        response = self.learning_db.scan(Limit=1)
        items = response.get('Items', [])
        if items:
            return json.loads(items[0].get('patterns', '{}'))
        return None
    
    def get_adjustment_factor(self) -> float:
        """Get position size adjustment factor based on recent performance."""
        patterns = self._get_latest_patterns()
        
        if not patterns:
            return 1.0
        
        total_trades = patterns.get("total_trades", 0)
        winning_trades = patterns.get("winning_trades", 0)
        
        if total_trades == 0:
            return 1.0
        
        win_rate = (winning_trades / total_trades) * 100
        
        # Adjust position size based on win rate
        if win_rate > 65:
            return 1.2  # Increase position size by 20%
        elif win_rate < 45:
            return 0.7  # Decrease position size by 30%
        else:
            return 1.0