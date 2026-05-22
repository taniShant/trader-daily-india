# agent/tools/database.py
import os
import boto3
from datetime import datetime
from typing import List, Dict, Any, Optional

def save_trade_signal(signal) -> None:
    """Save a trade signal to DynamoDB."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.environ.get("AWS_REGION", "eu-west-2"))
        table = dynamodb.Table(os.environ.get("TRADES_TABLE", "svc-trd-trades-dev"))
        item = {
            "tradeId": f"{signal.stock_symbol}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S%f')}",
            "date": signal.date,
            "timestamp": datetime.utcnow().isoformat(),
            "stock_symbol": signal.stock_symbol,
            "action": signal.action,
            "confidence": signal.confidence,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "target_price": signal.target_price,
            "reasoning": signal.reasoning,
            "technical_summary": signal.technical_summary,
            "sentiment_score": signal.sentiment_score,
            "risk_level": signal.risk_level,
            "pnl": 0.0  # Placeholder, will be updated on square-off
        }
        table.put_item(Item=item)
        print(f"✅ Saved trade signal for {signal.stock_symbol}")
    except Exception as e:
        print(f"❌ Failed to save trade signal: {e}")

def get_trade_history(stock_symbol: Optional[str] = None, days: int = 30) -> List[Dict[str, Any]]:
    """Retrieve trade history from DynamoDB."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.environ.get("AWS_REGION", "eu-west-2"))
        table = dynamodb.Table(os.environ.get("TRADES_TABLE", "svc-trd-trades-dev"))
        # Simple scan for demonstration; replace with query if you have a GSI on date
        response = table.scan()
        trades = response.get('Items', [])
        # Filter by date if needed
        return trades
    except Exception as e:
        print(f"❌ Failed to get trade history: {e}")
        return []