import pytest

from agent.config import Settings
from agent.contracts.execution import OrderSide, OrderStatus, OrderType
from agent.execution.oracle_proxy_broker import OracleProxyBroker
from agent.execution.paper_broker import PaperBroker
from agent.execution.router import get_broker


def settings_for(*, paper_trading: bool, shared_secret: str | None = "secret") -> Settings:
    return Settings.model_validate(
        {
            "environment": "test",
            "trading": {"paper_trading": paper_trading},
            "oracle": {
                "execution_proxy_base_url": "http://oracle-proxy.test:8080",
                "execution_proxy_client_id": "aws-test-bot",
                "execution_proxy_shared_secret": shared_secret,
            },
        }
    )


def test_paper_mode_selects_paper_broker_without_proxy_secret():
    broker = get_broker(
        paper_trading=True,
        settings_obj=settings_for(paper_trading=True, shared_secret=None),
    )

    assert isinstance(broker, PaperBroker)


def test_live_mode_selects_oracle_proxy_broker():
    broker = get_broker(
        paper_trading=False,
        settings_obj=settings_for(paper_trading=False, shared_secret="live-secret"),
    )

    assert isinstance(broker, OracleProxyBroker)
    assert broker.client.base_url == "http://oracle-proxy.test:8080"
    assert broker.client.client_id == "aws-test-bot"
    assert broker.client.shared_secret == "live-secret"


def test_live_mode_requires_proxy_shared_secret():
    with pytest.raises(ValueError, match="ORACLE_PROXY_SHARED_SECRET"):
        get_broker(
            paper_trading=False,
            settings_obj=settings_for(paper_trading=False, shared_secret=None),
        )


def test_oracle_proxy_broker_delegates_square_off_to_proxy_client():
    calls = []

    class RecordingClient:
        def place_order(self, order):
            calls.append(order)
            return OrderStatus.ACCEPTED

    broker = OracleProxyBroker(RecordingClient())

    assert broker.square_off("RELIANCE", 3) == OrderStatus.ACCEPTED
    assert len(calls) == 1
    assert calls[0].symbol == "RELIANCE"
    assert calls[0].quantity == 3
    assert calls[0].side == OrderSide.SELL
    assert calls[0].order_type == OrderType.MARKET
    assert calls[0].client_order_id.startswith("square-off-RELIANCE-")


def test_trading_bot_source_uses_broker_routing_not_legacy_order_tool():
    import inspect
    import agent.main as main_module

    source = inspect.getsource(main_module)

    assert "self.broker.place_order" in source
    assert "self.broker.square_off" in source
    assert "from .tools.order_execution import place_order" not in source
    assert "from .tools.order_execution import square_off_position" not in source
