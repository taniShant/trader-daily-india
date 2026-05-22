"""
Order Execution Tools - Places orders via ICICI Breeze API.
Supports paper trading mode for testing.
"""

import os
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import Breeze Connect
try:
    from breeze_connect import BreezeConnect
    BREEZE_AVAILABLE = True
except ImportError:
    BREEZE_AVAILABLE = False
    print("⚠️ breeze-connect not available. Using paper trading only.")

class OrderExecutor:
    """
    Executes orders via ICICI Breeze API.
    Supports limit orders, stop-loss, and square-off.
    """
    
    def __init__(self):
        self.breeze = None
        self.use_breeze = BREEZE_AVAILABLE and self._init_breeze()
        self.paper_trading = os.environ.get("PAPER_TRADING", "true").lower() == "true"
    
    def _init_breeze(self) -> bool:
        """Initialize Breeze Connect with credentials."""
        api_key = os.environ.get("ICICI_API_KEY")
        secret_key = os.environ.get("ICICI_SECRET_KEY")
        session_token = os.environ.get("ICICI_SESSION_TOKEN")
        
        if not all([api_key, secret_key, session_token]):
            print("⚠️ ICICI credentials not configured. Using paper trading.")
            return False
        
        try:
            self.breeze = BreezeConnect(api_key=api_key)
            self.breeze.generate_session(
                api_secret=secret_key,
                session_token=session_token
            )
            print("✅ Breeze Connect initialized for order execution")
            return True
        except Exception as e:
            print(f"⚠️ Failed to initialize Breeze Connect: {e}")
            return False
    
    def place_order(
        self,
        stock_code: str,
        action: str,
        quantity: int,
        price: float = None,
        stoploss: float = None,
        order_type: str = "limit"
    ) -> Dict[str, Any]:
        """
        Place an intraday order.
        
        Args:
            stock_code: Stock symbol (e.g., RELIANCE)
            action: 'buy' or 'sell'
            quantity: Number of shares
            price: Limit price (required for limit orders)
            stoploss: Stop loss price (optional)
            order_type: 'limit' or 'market'
            
        Returns:
            Order result with success flag and order_id
        """
        # Paper trading mode
        if self.paper_trading:
            return {
                "success": True,
                "order_id": f"PAPER_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                "stock_code": stock_code,
                "action": action,
                "quantity": quantity,
                "price": price,
                "status": "paper_trade",
                "message": f"[PAPER] Would have placed {action} order for {quantity} shares of {stock_code} @ ₹{price}"
            }
        
        # Live trading via Breeze API
        if not self.use_breeze or not self.breeze:
            return {
                "success": False,
                "error": "Breeze Connect not available. Check credentials.",
                "stock_code": stock_code
            }
        
        # Rate limiting (max 10 orders per second)
        time.sleep(0.1)
        
        try:
            order_params = {
                "stock_code": stock_code,
                "exchange_code": "NSE",
                "action": action.lower(),
                "order_type": order_type,
                "quantity": quantity,
                "validity": "day",
                "product_type": "intraday"
            }
            
            if order_type == "limit" and price:
                order_params["price"] = price
            elif order_type == "market":
                order_params["order_type"] = "market"
            else:
                return {
                    "success": False,
                    "error": f"Limit order requires price for {stock_code}"
                }
            
            if stoploss:
                order_params["stoploss"] = stoploss
            
            response = self.breeze.place_order(**order_params)
            
            if response and response.get("Success"):
                return {
                    "success": True,
                    "order_id": response["Success"].get("order_id"),
                    "stock_code": stock_code,
                    "action": action,
                    "quantity": quantity,
                    "price": price,
                    "status": "placed",
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": response.get("Error", "Order placement failed"),
                    "stock_code": stock_code
                }
                
        except Exception as e:
            logger.error(f"Order placement error for {stock_code}: {e}")
            return {
                "success": False,
                "error": str(e),
                "stock_code": stock_code
            }
    
    def square_off_position(self, stock_code: str, quantity: int) -> Dict[str, Any]:
        """
        Square off an open position (intraday).
        
        Args:
            stock_code: Stock symbol
            quantity: Number of shares to square off
            
        Returns:
            Square-off result
        """
        if self.paper_trading:
            return {
                "success": True,
                "message": f"[PAPER] Would have squared off {quantity} shares of {stock_code}",
                "stock_code": stock_code
            }
        
        if not self.use_breeze or not self.breeze:
            return {
                "success": False,
                "error": "Breeze Connect not available"
            }
        
        time.sleep(0.1)  # Rate limiting
        
        try:
            # For intraday, square off means selling (if bought) or buying (if sold)
            response = self.breeze.place_order(
                stock_code=stock_code,
                exchange_code="NSE",
                action="sell",
                order_type="market",
                quantity=quantity,
                validity="day",
                product_type="intraday"
            )
            
            if response and response.get("Success"):
                return {
                    "success": True,
                    "order_id": response["Success"].get("order_id"),
                    "stock_code": stock_code,
                    "quantity": quantity,
                    "status": "squared_off",
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": response.get("Error", "Square off failed"),
                    "stock_code": stock_code
                }
                
        except Exception as e:
            logger.error(f"Square off error for {stock_code}: {e}")
            return {
                "success": False,
                "error": str(e),
                "stock_code": stock_code
            }
    
    def get_positions(self) -> Dict[str, Any]:
        """Get current open positions."""
        if self.paper_trading:
            return {"success": True, "positions": [], "message": "Paper trading mode - no real positions"}
        
        if not self.use_breeze or not self.breeze:
            return {"success": False, "error": "Breeze Connect not available"}
        
        try:
            response = self.breeze.get_positions()
            if response and response.get("Success"):
                return {
                    "success": True,
                    "positions": response["Success"],
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {"success": False, "error": response.get("Error", "Failed to fetch positions")}
        except Exception as e:
            logger.error(f"Get positions error: {e}")
            return {"success": False, "error": str(e)}
    
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Get status of a specific order."""
        if self.paper_trading:
            return {"success": True, "status": "paper_trade", "order_id": order_id}
        
        if not self.use_breeze or not self.breeze:
            return {"success": False, "error": "Breeze Connect not available"}
        
        try:
            response = self.breeze.get_order_detail(order_id=order_id)
            if response and response.get("Success"):
                return {
                    "success": True,
                    "order_id": order_id,
                    "status": response["Success"].get("order_status"),
                    "filled_quantity": response["Success"].get("filled_quantity"),
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {"success": False, "error": response.get("Error", "Order not found")}
        except Exception as e:
            logger.error(f"Get order status error: {e}")
            return {"success": False, "error": str(e)}


# Singleton instance
_order_executor = None

def get_order_executor() -> OrderExecutor:
    """Get singleton order executor instance."""
    global _order_executor
    if _order_executor is None:
        _order_executor = OrderExecutor()
    return _order_executor


# ============================================================
# TOOL FUNCTIONS FOR STRANDS AGENT
# ============================================================

def place_order(
    stock_code: str,
    action: str,
    quantity: int,
    price: float = None,
    stoploss: float = None,
    order_type: str = "limit"
) -> Dict[str, Any]:
    """
    Place an intraday order.
    This is the main function called by the orchestrator.
    """
    executor = get_order_executor()
    return executor.place_order(stock_code, action, quantity, price, stoploss, order_type)


def get_positions() -> Dict[str, Any]:
    """Get current open positions."""
    executor = get_order_executor()
    return executor.get_positions()


def square_off_position(stock_code: str, quantity: int) -> Dict[str, Any]:
    """Square off an open position."""
    executor = get_order_executor()
    return executor.square_off_position(stock_code, quantity)