# tools/database.py
import os
import json
from datetime import datetime
import boto3

def save_trade_signal(signal):
    """Save trade signal to DynamoDB."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.environ.get("AWS_REGION", "eu-west-2"))
        table = dynamodb.Table(os.environ.get("TRADES_TABLE", "svc-trd-trades-dev"))
        
        item = {
            "tradeId": f"{signal.stock_symbol}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            "date": signal.date,
            "timestamp": datetime.utcnow().isoformat(),
            "stock_symbol": signal.stock_symbol,
            "action": signal.action,
            "confidence": signal.confidence,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "target_price": signal.target_price,
            "reasoning": signal.reasoning,
            "sentiment_score": signal.sentiment_score,
            "risk_level": signal.risk_level,
            "pnl": 0  # Will be updated when squared off
        }
        table.put_item(Item=item)
        print(f"✅ Saved trade signal for {signal.stock_symbol}")
    except Exception as e:
        print(f"⚠️ Failed to save trade signal: {e}")

def get_trade_history(stock_symbol=None, days=30):
    """Get trade history from DynamoDB."""
    # Implementation for retrieving trade history
    return []