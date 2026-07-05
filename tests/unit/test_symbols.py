from datetime import datetime, timezone
from decimal import Decimal

from agent.contracts.execution import OrderRequest, OrderSide, OrderType
from agent.data.symbols import breeze_stock_code, canonical_symbol, resolve_symbol, yahoo_symbol
from agent.execution.oracle_breeze_client import _order_to_proxy_payload
from agent.tools.market_data import MarketDataProvider


def test_symbol_mapping_normalizes_common_forms():
    assert canonical_symbol(" reliance ") == "RELIANCE"
    assert canonical_symbol("RELIANCE.NS") == "RELIANCE"
    assert yahoo_symbol("RELIANCE") == "RELIANCE.NS"
    assert breeze_stock_code("RELIANCE.NS") == "RELIANCE"


def test_symbol_mapping_handles_known_aliases_and_unknowns():
    nestle = resolve_symbol("NESTLE.NS")
    unknown = resolve_symbol("ABCDEF")

    assert nestle.canonical == "NESTLEIND"
    assert nestle.yahoo == "NESTLEIND.NS"
    assert nestle.breeze == "NESTLEIND"
    assert unknown.canonical == "ABCDEF"
    assert unknown.yahoo == "ABCDEF.NS"
    assert unknown.breeze == "ABCDEF"


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

    assert calls == [{"stock_code": "RELIANCE", "exchange_code": "NSE"}]
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

    assert payload["symbol"] == "RELIANCE"
    assert payload["exchange"] == "NSE"
