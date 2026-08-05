from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolMapping:
    canonical: str
    yahoo: str
    breeze: str
    exchange: str = "NSE"
    name: str | None = None


_NIFTY_LARGE_CAPS = {
    "RELIANCE": "Reliance Industries",
    "TCS": "Tata Consultancy Services",
    "HDFCBANK": "HDFC Bank",
    "INFY": "Infosys",
    "ICICIBANK": "ICICI Bank",
    "SBIN": "State Bank of India",
    "BHARTIARTL": "Bharti Airtel",
    "KOTAKBANK": "Kotak Mahindra Bank",
    "BAJFINANCE": "Bajaj Finance",
    "ITC": "ITC",
    "HINDUNILVR": "Hindustan Unilever",
    "AXISBANK": "Axis Bank",
    "LT": "Larsen and Toubro",
    "SUNPHARMA": "Sun Pharmaceutical",
    "TITAN": "Titan",
    "MARUTI": "Maruti Suzuki",
    "WIPRO": "Wipro",
    "ONGC": "Oil and Natural Gas Corporation",
    "NTPC": "NTPC",
    "POWERGRID": "Power Grid Corporation",
    "ULTRACEMCO": "UltraTech Cement",
    "HCLTECH": "HCL Technologies",
    "BAJAJFINSV": "Bajaj Finserv",
    "ADANIPORTS": "Adani Ports",
    "ASIANPAINT": "Asian Paints",
    "GRASIM": "Grasim",
    "NESTLEIND": "Nestle India",
    "JSWSTEEL": "JSW Steel",
    "TECHM": "Tech Mahindra",
    "INDUSINDBK": "IndusInd Bank",
    "DRREDDY": "Dr Reddy's Laboratories",
    "BRITANNIA": "Britannia",
    "EICHERMOT": "Eicher Motors",
    "COALINDIA": "Coal India",
    "DIVISLAB": "Divi's Laboratories",
    "SBILIFE": "SBI Life Insurance",
    "HDFCLIFE": "HDFC Life Insurance",
    "UPL": "UPL",
    "BAJAJ-AUTO": "Bajaj Auto",
    "SHREECEM": "Shree Cement",
    "CIPLA": "Cipla",
    "HEROMOTOCO": "Hero MotoCorp",
    "TATASTEEL": "Tata Steel",
    "HINDALCO": "Hindalco",
    "BPCL": "Bharat Petroleum",
    "IOC": "Indian Oil Corporation",
    "M&M": "Mahindra and Mahindra",
    "TATAMOTORS": "Tata Motors",
    "TATACONSUM": "Tata Consumer Products",
}


_BREEZE_STOCK_CODES = {
    "ADANIPORTS": "ADAPOR",
    "RELIANCE": "RELIANCE",
    "HDFCBANK": "HDFBAN",
    "INFY": "INFY",
    "ICICIBANK": "ICICIBAN",
    "BHARTIARTL": "BHAART",
    "KOTAKBANK": "KOTMAH",
    "AXISBANK": "AXIBAN",
    "BAJFINANCE": "BAJFIN",
    "HINDUNILVR": "HINLEV",
    "LT": "LARTOU",
    "HEROMOTOCO": "HERHON",
    "TITAN": "TITAN",
    "TECHM": "TECMAH",
    "ASIANPAINT": "ASIPAI",
    "HCLTECH": "HCLTEC",
    "DIVISLAB": "DIVLAB",
    "BAJAJFINSV": "BAJFSV",
    "EICHERMOT": "EICMOT",
    "SUNPHARMA": "SUNPHA",
    "JSWSTEEL": "JSWSTE",
    "M&M": "MAHMAH",
    "TATAMOTORS": "TATMOT",
    "TATASTEEL": "TATSTE",
    "HINDALCO": "HINDAL",
    "BRITANNIA": "BRITAN",
    "DRREDDY": "DRREDD",
    "COALINDIA": "COALIN",
    "BAJAJ-AUTO": "BAAUTO",
    "MARUTI": "MARUTI",
    "WIPRO": "WIPRO",
    "ONGC": "ONGC",
    "NTPC": "NTPC",
    "POWERGRID": "POWGRID",
    "ULTRACEMCO": "ULTECO",
    "GRASIM": "GRAIND",
    "NESTLEIND": "NESIND",
    "INDUSINDBK": "INDBAN",
    "SBILIFE": "SBILIF",
    "HDFCLIFE": "HDFLIF",
    "UPL": "UPLLTD",
    "SHREECEM": "SHRCEM",
    "CIPLA": "CIPLA",
    "BPCL": "BPCL",
    "IOC": "IOC",
    "TATACONSUM": "TATGLO",
}


SYMBOL_MASTER: dict[str, SymbolMapping] = {
    symbol: SymbolMapping(
        canonical=symbol,
        yahoo=f"{symbol}.NS",
        breeze=_BREEZE_STOCK_CODES.get(symbol, symbol),
        name=name,
    )
    for symbol, name in _NIFTY_LARGE_CAPS.items()
}


def canonical_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if cleaned.endswith(".N"):
        cleaned = cleaned[:-2]
    if cleaned.endswith(".NS"):
        cleaned = cleaned[:-3]
    if cleaned.endswith(".BO"):
        cleaned = cleaned[:-3]
    return _ALIASES.get(cleaned, cleaned)


def resolve_symbol(symbol: str) -> SymbolMapping:
    canonical = canonical_symbol(symbol)
    if canonical in SYMBOL_MASTER:
        return SYMBOL_MASTER[canonical]
    return SymbolMapping(
        canonical=canonical,
        yahoo=f"{canonical}.NS",
        breeze=canonical,
    )


def yahoo_symbol(symbol: str) -> str:
    return resolve_symbol(symbol).yahoo


def breeze_stock_code(symbol: str) -> str:
    return resolve_symbol(symbol).breeze


def is_supported_intraday_symbol(symbol: str) -> bool:
    return canonical_symbol(symbol) in SYMBOL_MASTER


_ALIASES = {
    "NESTLE": "NESTLEIND",
    "TATAMOTORS": "TATAMOTORS",
    "TMCV": "TATAMOTORS",
    "TMPV": "TATAMOTORS",
}
