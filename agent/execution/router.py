from __future__ import annotations

from agent.config import Settings, settings

from .broker import Broker
from .oracle_breeze_client import OracleBreezeClient
from .oracle_proxy_broker import OracleProxyBroker
from .paper_broker import PaperBroker


def get_broker(*, paper_trading: bool | None = None, settings_obj: Settings = settings) -> Broker:
    """Select the execution broker for the current runtime mode."""
    use_paper = settings_obj.trading.paper_trading if paper_trading is None else paper_trading
    if use_paper:
        return PaperBroker()

    shared_secret = settings_obj.oracle.execution_proxy_shared_secret
    if not shared_secret:
        raise ValueError("ORACLE_PROXY_SHARED_SECRET is required when PAPER_TRADING=false")

    client = OracleBreezeClient(
        base_url=settings_obj.oracle.execution_proxy_base_url,
        client_id=settings_obj.oracle.execution_proxy_client_id,
        shared_secret=shared_secret,
    )
    return OracleProxyBroker(client)
