from datetime import datetime, timezone
from decimal import Decimal

from agent.contracts.execution import OrderRequest, OrderSide, OrderType
from agent.data.symbols import (
    breeze_stock_code,
    canonical_symbol,
    is_supported_intraday_symbol,
    resolve_symbol,
    yahoo_symbol,
)
from agent.execution.oracle_breeze_client import _order_to_proxy_payload
from agent.tools.market_data import MarketDataProvider


def test_symbol_mapping_normalizes_common_forms():
    assert canonical_symbol(" reliance ") == "RELIANCE"
    assert canonical_symbol("RELIANCE.NS") == "RELIANCE"
    assert canonical_symbol("INFY.N") == "INFY"
    assert canonical_symbol("INFY.BO") == "INFY"
    assert yahoo_symbol("INFY.N") == "INFY.NS"
    assert yahoo_symbol("RELIANCE") == "RELIANCE.NS"
    assert breeze_stock_code("RELIANCE.NS") == "RELIND"


def test_symbol_mapping_handles_known_aliases_and_unknowns():
    nestle = resolve_symbol("NESTLE.NS")
    unknown = resolve_symbol("ABCDEF")

    assert nestle.canonical == "NESTLEIND"
    assert nestle.yahoo == "NESTLEIND.NS"
    assert nestle.breeze == "NESTLEIND"
    assert unknown.canonical == "ABCDEF"
    assert unknown.yahoo == "ABCDEF.NS"
    assert unknown.breeze == "ABCDEF"


def test_symbol_mapping_uses_verified_breeze_stock_codes_for_watchlist():
    assert breeze_stock_code("ADANIPORTS") == "ADAPOR"
    assert breeze_stock_code("RELIANCE") == "RELIND"
    assert breeze_stock_code("INFY") == "INFTEC"
    assert breeze_stock_code("HDFCBANK") == "HDFBAN"
    assert breeze_stock_code("ICICIBANK") == "ICICIBANK"
    assert breeze_stock_code("BHARTIARTL") == "BHAAIR"
    assert breeze_stock_code("KOTAKBANK") == "KOTMAH"
    assert breeze_stock_code("AXISBANK") == "AXIBAN"
    assert breeze_stock_code("LT") == "LARTOU"
    assert breeze_stock_code("HEROMOTOCO") == "HERHON"
    assert breeze_stock_code("TITAN") == "TITIND"
    assert breeze_stock_code("TECHM") == "TECMAH"
    assert breeze_stock_code("ASIANPAINT") == "ASIPAI"
    assert breeze_stock_code("HCLTECH") == "HCLTEC"
    assert breeze_stock_code("DIVISLAB") == "DIVLAB"
    assert breeze_stock_code("BAJFINANCE") == "BAJFI"
    assert breeze_stock_code("BAJAJFINSV") == "BAFINS"
    assert breeze_stock_code("EICHERMOT") == "EICMOT"
    assert breeze_stock_code("SUNPHARMA") == "SUNPHA"
    assert breeze_stock_code("JSWSTEEL") == "JSWSTE"
    assert breeze_stock_code("M&M") == "MAHMAH"
    assert breeze_stock_code("TATAMOTORS") == "TATMOT"
    assert breeze_stock_code("TMCV") == "TATMOT"
    assert breeze_stock_code("TMPV") == "TATMOT"
    assert breeze_stock_code("TATASTEEL") == "TATSTE"
    assert breeze_stock_code("HINDALCO") == "HINDAL"
    assert breeze_stock_code("BRITANNIA") == "BRIIND"
    assert breeze_stock_code("DRREDDY") == "DRREDD"
    assert breeze_stock_code("COALINDIA") == "COALIN"
    assert breeze_stock_code("BAJAJ-AUTO") == "BAAUTO"
    assert breeze_stock_code("MARUTI") == "MARUTI"
    assert breeze_stock_code("ONGC") == "ONGC"


def test_tata_motors_legacy_symbols_map_to_icici_tata_motors_code():
    tata = resolve_symbol("TATAMOTORS")
    tmc = resolve_symbol("TMCV")
    tmp = resolve_symbol("TMPV")

    assert tata.canonical == "TATAMOTORS"
    assert tata.yahoo == "TATAMOTORS.NS"
    assert tata.breeze == "TATMOT"
    assert tmc.canonical == "TATAMOTORS"
    assert tmp.canonical == "TATAMOTORS"
    assert is_supported_intraday_symbol("TATAMOTORS") is True
    assert is_supported_intraday_symbol("TMCV") is True
    assert is_supported_intraday_symbol("TMPV") is True
    assert is_supported_intraday_symbol("M&M") is True
    assert is_supported_intraday_symbol("MARUTI") is True


def test_market_data_uses_canonical_symbol_for_breeze_quote():
    calls = []

    class FakeBreeze:
        def get_quotes(self, **kwargs):
            calls.append(kwargs)
            return {
                "Success": {
                    "ltp": "100",
                    "open": "99",
                    "high": "101",
                    "low": "98",
                    "close": "97",
                    "volume": "123",
                }
            }

    provider = MarketDataProvider.__new__(MarketDataProvider)
    provider.use_breeze = True
    provider.breeze = FakeBreeze()

    payload = provider.get_live_quote("RELIANCE.NS")

    assert calls == [{"stock_code": "RELIND", "exchange_code": "NSE"}]
    assert payload["symbol"] == "RELIANCE"


def test_oracle_order_payload_sends_breeze_stock_code():
    order = OrderRequest(
        client_order_id="order-1",
        signal_id="signal-1",
        risk_decision_id="risk-1",
        symbol="RELIANCE.NS",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=1,
        price=Decimal("100"),
        requested_at=datetime(2026, 7, 4, tzinfo=timezone.utc),
    )

    payload = _order_to_proxy_payload(order)

    assert payload["symbol"] == "RELIND"
    assert payload["exchange"] == "NSE"
