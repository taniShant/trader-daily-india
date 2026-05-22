#!/usr/bin/env python3
"""
Trading Bot Dashboard API Server
Serves static frontend files and provides REST endpoints
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import boto3
from datetime import datetime, timedelta
import os
import pandas as pd
from pathlib import Path

app = FastAPI(title="Trading Bot Dashboard")

# ============================================================
# CONFIGURATION FROM ENVIRONMENT VARIABLES
# ============================================================

AWS_REGION = os.environ.get("AWS_REGION", "eu-west-2")
TRADES_TABLE_NAME = os.environ.get("TRADES_TABLE", "svc-trd-trades-dev")
LEARNING_TABLE_NAME = os.environ.get("LEARNING_TABLE", "svc-trd-learning-dev")
MARKET_STATE_TABLE_NAME = os.environ.get("MARKET_STATE_TABLE", "svc-trd-market-state-dev")

# Enable CORS (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to your domain in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (HTML, CSS, JS)
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# ============================================================
# DYNAMODB CLIENTS
# ============================================================

dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
trades_table = dynamodb.Table(TRADES_TABLE_NAME)
learning_table = dynamodb.Table(LEARNING_TABLE_NAME)
market_state_table = dynamodb.Table(MARKET_STATE_TABLE_NAME)

# ============================================================
# FRONTEND
# ============================================================

@app.get("/")
async def serve_index():
    """Serve the main dashboard HTML"""
    index_path = static_path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": "Dashboard not found"}

# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/api/status")
async def get_status():
    """Get current bot status (real data from DynamoDB)"""
    now_utc = datetime.utcnow()
    market_open = now_utc.replace(hour=3, minute=45)   # 9:15 AM IST
    market_close = now_utc.replace(hour=10, minute=0)  # 3:30 PM IST
    is_market_hours = market_open <= now_utc <= market_close
    
    # Get today's trades from DynamoDB
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        # Scan trades from today
        response = trades_table.scan()
        trades = response.get('Items', [])
        today_trades = [t for t in trades if t.get('date', '').startswith(today_str)]
        
        today_pnl = sum(float(t.get('pnl', 0)) for t in today_trades)
        winning_trades = [t for t in today_trades if float(t.get('pnl', 0)) > 0]
        win_rate = (len(winning_trades) / len(today_trades) * 100) if today_trades else 0
        
        # Get active positions (trades without exit)
        active_positions = [t for t in today_trades if not t.get('exit_time')]
        
        return {
            "status": "active" if is_market_hours else "waiting",
            "active_positions": len(active_positions),
            "today_pnl": round(today_pnl, 2),
            "win_rate": round(win_rate, 1),
            "market_hours": "open" if is_market_hours else "closed",
            "last_analysis": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "active_positions": 0,
            "today_pnl": 0.0,
            "win_rate": 0.0,
            "market_hours": "open" if is_market_hours else "closed",
            "error": str(e)
        }

@app.get("/api/trades")
async def get_trades(limit: int = 50, stock: str = None, days: int = 30):
    """Get recent trades from TradesTable"""
    try:
        response = trades_table.scan(Limit=limit * 2)
        trades = response.get('Items', [])
        
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        trades = [t for t in trades if t.get('timestamp', '') > cutoff_date]
        
        if stock:
            trades = [t for t in trades if stock.upper() in t.get('stock_symbol', '').upper()]
        
        trades = [t for t in trades if t.get('tradeId') != 'bot_state']
        trades.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return {"trades": trades[:limit], "total": len(trades)}
    except Exception as e:
        return {"trades": [], "total": 0, "error": str(e)}

@app.get("/api/pnl")
async def get_pnl(days: int = 30):
    """Get P&L curve from TradesTable"""
    try:
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        response = trades_table.scan()
        trades = [t for t in response.get('Items', []) if t.get('timestamp', '') > cutoff_date]
        trades = [t for t in trades if t.get('tradeId') != 'bot_state' and 'pnl' in t]
        
        if not trades:
            return {"dates": [], "daily_pnl": [], "cumulative_pnl": []}
        
        df = pd.DataFrame(trades)
        df['date'] = pd.to_datetime(df['timestamp']).dt.date
        df['pnl'] = pd.to_numeric(df['pnl'], errors='coerce').fillna(0)
        
        daily_pnl = df.groupby('date')['pnl'].sum().reset_index()
        daily_pnl['cumulative'] = daily_pnl['pnl'].cumsum()
        
        return {
            "dates": daily_pnl['date'].astype(str).tolist(),
            "daily_pnl": daily_pnl['pnl'].round(2).tolist(),
            "cumulative_pnl": daily_pnl['cumulative'].round(2).tolist()
        }
    except Exception as e:
        return {"dates": [], "daily_pnl": [], "cumulative_pnl": [], "error": str(e)}

@app.get("/api/learning")
async def get_learning_patterns(limit: int = 20):
    """Get learning patterns from LearningTable"""
    try:
        response = learning_table.scan(Limit=limit)
        patterns = response.get('Items', [])
        patterns.sort(key=lambda x: x.get('date', ''), reverse=True)
        return {"patterns": patterns, "total": len(patterns)}
    except Exception as e:
        return {"patterns": [], "total": 0, "error": str(e)}

@app.get("/api/market-state")
async def get_market_state(days: int = 7):
    """Get market state (overnight analysis) from MarketStateTable"""
    try:
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        response = market_state_table.scan()
        states = response.get('Items', [])
        states = [s for s in states if s.get('date', '') >= cutoff_date]
        states.sort(key=lambda x: x.get('date', ''), reverse=True)
        return {"market_states": states, "total": len(states)}
    except Exception as e:
        return {"market_states": [], "total": 0, "error": str(e)}

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "trades_table": TRADES_TABLE_NAME,
        "learning_table": LEARNING_TABLE_NAME,
        "market_state_table": MARKET_STATE_TABLE_NAME
    }

# ============================================================
# MAIN ENTRY POINT
# ============================================================

def main():
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()