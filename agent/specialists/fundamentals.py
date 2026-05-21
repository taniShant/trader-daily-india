from strands import Agent, tool
from typing import Dict, Any
import yfinance as yf
import pandas as pd

@tool
def get_balance_sheet(stock_symbol: str) -> Dict[str, Any]:
    """Get company balance sheet data"""
    if not stock_symbol.endswith(".NS"):
        stock_symbol = f"{stock_symbol}.NS"
    
    ticker = yf.Ticker(stock_symbol)
    balance_sheet = ticker.balance_sheet
    
    if balance_sheet is None or balance_sheet.empty:
        return {"error": "No balance sheet data available"}
    
    # Get the most recent quarter
    latest = balance_sheet.iloc[:, 0]
    
    return {
        "total_assets": latest.get("Total Assets", 0),
        "total_liabilities": latest.get("Total Liabilities Net Minority Interest", 0),
        "total_equity": latest.get("Total Equity Gross Minority Interest", 0),
        "debt_to_equity": latest.get("Total Debt", 0) / latest.get("Total Equity Gross Minority Interest", 1) if latest.get("Total Equity Gross Minority Interest") else None
    }

@tool
def get_income_statement(stock_symbol: str) -> Dict[str, Any]:
    """Get company income statement data"""
    if not stock_symbol.endswith(".NS"):
        stock_symbol = f"{stock_symbol}.NS"
    
    ticker = yf.Ticker(stock_symbol)
    income_stmt = ticker.income_stmt
    
    if income_stmt is None or income_stmt.empty:
        return {"error": "No income statement data available"}
    
    latest = income_stmt.iloc[:, 0]
    
    return {
        "revenue": latest.get("Total Revenue", 0),
        "gross_profit": latest.get("Gross Profit", 0),
        "operating_income": latest.get("Operating Income", 0),
        "net_income": latest.get("Net Income", 0),
        "eps": latest.get("Basic EPS", 0)
    }

@tool
def get_cash_flow(stock_symbol: str) -> Dict[str, Any]:
    """Get company cash flow statement data"""
    if not stock_symbol.endswith(".NS"):
        stock_symbol = f"{stock_symbol}.NS"
    
    ticker = yf.Ticker(stock_symbol)
    cashflow = ticker.cashflow
    
    if cashflow is None or cashflow.empty:
        return {"error": "No cash flow data available"}
    
    latest = cashflow.iloc[:, 0]
    
    return {
        "operating_cash_flow": latest.get("Operating Cash Flow", 0),
        "free_cash_flow": latest.get("Free Cash Flow", 0),
        "capital_expenditure": latest.get("Capital Expenditure", 0)
    }

@tool
def get_growth_metrics(stock_symbol: str) -> Dict[str, Any]:
    """Calculate year-over-year growth metrics"""
    if not stock_symbol.endswith(".NS"):
        stock_symbol = f"{stock_symbol}.NS"
    
    ticker = yf.Ticker(stock_symbol)
    income_stmt = ticker.income_stmt
    
    if income_stmt is None or income_stmt.shape[1] < 2:
        return {"error": "Insufficient historical data"}
    
    current = income_stmt.iloc[:, 0]
    previous = income_stmt.iloc[:, 1]
    
    revenue_growth = ((current.get("Total Revenue", 0) - previous.get("Total Revenue", 0)) / previous.get("Total Revenue", 1)) * 100 if previous.get("Total Revenue") else None
    net_income_growth = ((current.get("Net Income", 0) - previous.get("Net Income", 0)) / previous.get("Net Income", 1)) * 100 if previous.get("Net Income") else None
    
    return {
        "revenue_growth_percent": revenue_growth,
        "net_income_growth_percent": net_income_growth,
        "period": "Year-over-Year"
    }

@tool
def get_valuation_ratios(stock_symbol: str) -> Dict[str, Any]:
    """Get valuation metrics (P/E, P/B, EV/EBITDA, etc.)"""
    if not stock_symbol.endswith(".NS"):
        stock_symbol = f"{stock_symbol}.NS"
    
    ticker = yf.Ticker(stock_symbol)
    info = ticker.info
    
    return {
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "pb_ratio": info.get("priceToBook"),
        "ps_ratio": info.get("priceToSalesTrailing12Months"),
        "ev_to_ebitda": info.get("enterpriseToEbitda"),
        "peg_ratio": info.get("pegRatio"),
        "dividend_yield": info.get("dividendYield"),
        "payout_ratio": info.get("payoutRatio")
    }

class FundamentalAnalyst(Agent):
    """Specialist agent for company fundamental analysis"""
    
    def __init__(self, model, memory):
        super().__init__(
            name="FundamentalAnalyst",
            model=model,
            memory=memory,
            tools=[
                get_balance_sheet,
                get_income_statement,
                get_cash_flow,
                get_growth_metrics,
                get_valuation_ratios
            ],
            system_prompt="""
            You are a senior fundamental analyst for Indian equities.
            
            Your job is to analyze company financial health, valuation, and growth prospects.
            
            Key analysis areas:
            1. **Valuation**: Check P/E vs industry, P/B, EV/EBITDA. Is the stock overvalued or undervalued?
            2. **Growth**: Revenue and earnings growth rates. Is the company growing sustainably?
            3. **Financial Health**: Debt-to-equity, current ratio, operating cash flow.
            4. **Profitability**: Net margins, ROE, ROA.
            
            Output JSON with:
            - recommendation (BULLISH/BEARISH/NEUTRAL)
            - confidence (0-100)
            - key_metrics (P/E, P/B, growth rates)
            - health_status (strong/moderate/weak)
            - valuation_verdict (overvalued/fair/undervalued)
            - red_flags (list of concerns, if any)
            - growth_outlook (positive/stable/negative)
            """
        )