from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SymbolMapping:
    canonical: str
    yahoo: str
    breeze: str
    exchange: str = "NSE"
    name: str | None = None


_DEFAULT_NIFTY_LARGE_CAPS = {
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


_DEFAULT_BREEZE_STOCK_CODES = {
    "ADANIPORTS": "ADAPOR",
    "RELIANCE": "RELIND",
    "HDFCBANK": "HDFBAN",
    "INFY": "INFTEC",
    "ICICIBANK": "ICIBAN",
    "BHARTIARTL": "BHAART",
    "KOTAKBANK": "KOTMAH",
    "AXISBANK": "AXIBAN",
    "BAJFINANCE": "BAFSL",
    "HINDUNILVR": "HINLEV",
    "LT": "LARTOU",
    "HEROMOTOCO": "HERHON",
    "TITAN": "TITIND",
    "TECHM": "TECMAH",
    "ASIANPAINT": "ASIPAI",
    "HCLTECH": "HCLTEC",
    "DIVISLAB": "DIVLAB",
    "BAJAJFINSV": "BAJFIN",
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
    "POWERGRID": "POWIND",
    "ULTRACEMCO": "ULTRAC",
    "GRASIM": "GRAIND",
    "NESTLEIND": "NESIND",
    "INDUSINDBK": "INDBAN",
    "SBILIFE": "SBILIF",
    "HDFCLIFE": "HDFLIF",
    "UPL": "UPL",
    "SHREECEM": "SHRCEM",
    "CIPLA": "CIPLA",
    "BPCL": "BPCL",
    "IOC": "IOC",
    "TATACONSUM": "TATGLO",
}


_ALIASES = {
    "NESTLE": "NESTLEIND",
    "TATAMOTORS": "TATAMOTORS",
    "TMCV": "TATAMOTORS",
    "TMPV": "TATAMOTORS",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_market_symbols_config() -> dict[str, Any]:
    inline = os.environ.get("MARKET_SYMBOLS_JSON")
    if inline:
        try:
            payload = json.loads(inline)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}

    environment = os.environ.get("CDK_DEPLOY_ENV") or os.environ.get("ENVIRONMENT") or "prod"
    config_path = _project_root() / "cicd" / "env" / f"{environment}.json"
    try:
        payload = json.loads(config_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    market_symbols = payload.get("market_symbols")
    return market_symbols if isinstance(market_symbols, dict) else {}


def _canonical_symbol_value(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if cleaned.endswith(".N"):
        cleaned = cleaned[:-2]
    if cleaned.endswith(".NS"):
        cleaned = cleaned[:-3]
    if cleaned.endswith(".BO"):
        cleaned = cleaned[:-3]
    return _ALIASES.get(cleaned, cleaned)


def _build_symbol_master() -> dict[str, SymbolMapping]:
    configured = _load_market_symbols_config()
    symbols = configured.get("symbols") if isinstance(configured, dict) else None
    if not isinstance(symbols, dict) or not symbols:
        return {
            symbol: SymbolMapping(
                canonical=symbol,
                yahoo=f"{symbol}.NS",
                breeze=_DEFAULT_BREEZE_STOCK_CODES.get(symbol, symbol),
                name=name,
            )
            for symbol, name in _DEFAULT_NIFTY_LARGE_CAPS.items()
        }

    default_exchange = str(configured.get("exchange") or "NSE").upper()
    master: dict[str, SymbolMapping] = {}
    for raw_symbol, raw_mapping in symbols.items():
        canonical = _canonical_symbol_value(str(raw_symbol))
        if not canonical:
            continue
        if isinstance(raw_mapping, str):
            mapping = {"breeze": raw_mapping}
        elif isinstance(raw_mapping, dict):
            mapping = raw_mapping
        else:
            continue
        breeze = str(mapping.get("breeze") or canonical).strip().upper()
        yahoo = str(mapping.get("yahoo") or f"{canonical}.NS").strip().upper()
        exchange = str(mapping.get("exchange") or default_exchange or "NSE").strip().upper()
        name = mapping.get("name") or _DEFAULT_NIFTY_LARGE_CAPS.get(canonical)
        master[canonical] = SymbolMapping(
            canonical=canonical,
            yahoo=yahoo,
            breeze=breeze,
            exchange=exchange,
            name=str(name) if name else None,
        )
    return master


SYMBOL_MASTER: dict[str, SymbolMapping] = _build_symbol_master()


def canonical_symbol(symbol: str) -> str:
    return _canonical_symbol_value(symbol)


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
