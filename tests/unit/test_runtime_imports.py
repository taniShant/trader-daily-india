import importlib
import sys
import types
from pathlib import Path


def test_agent_main_imports_trading_bot_runtime():
    main = importlib.import_module("agent.main")

    assert hasattr(main, "TradingBot")
    assert main.TradingBot.__name__ == "TradingBot"
    assert main.models == {}
    assert main.orchestrator is None
    assert main.technical_agent is None


def test_specialist_constructors_are_ecs_compatible_without_memory(monkeypatch):
    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def fake_tool(fn=None, **kwargs):
        if fn is None:
            return lambda wrapped: wrapped
        return fn

    fake_strands = types.ModuleType("strands")
    fake_strands.Agent = FakeAgent
    fake_strands.tool = fake_tool
    monkeypatch.setitem(sys.modules, "strands", fake_strands)

    for module_name in list(sys.modules):
        if module_name.startswith("agent.specialists.") or module_name.startswith("agent.tools."):
            monkeypatch.delitem(sys.modules, module_name, raising=False)

    from agent.specialists.derivatives import DerivativesAnalyst
    from agent.specialists.fundamentals import FundamentalAnalyst
    from agent.specialists.sentiment import SentimentAnalyst
    from agent.specialists.social import SocialAnalyst
    from agent.specialists.technical import TechnicalAnalyst

    assert type(TechnicalAnalyst(model=None)).__name__ == "TechnicalAnalyst"
    assert type(SentimentAnalyst(model=None)).__name__ == "SentimentAnalyst"
    assert type(FundamentalAnalyst(model=None)).__name__ == "FundamentalAnalyst"
    assert type(SocialAnalyst(model=None)).__name__ == "SocialAnalyst"
    assert type(DerivativesAnalyst(model=None)).__name__ == "DerivativesAnalyst"


def test_trading_bot_entrypoint_imports_existing_bot_class():
    entrypoint = Path("containers/trading-bot/entrypoint.sh").read_text()

    assert "from agent.main import TradingBot" in entrypoint
    assert "from agent.main import ECSCompatibleBot" not in entrypoint


def test_trading_bot_fallback_watchlist_includes_maruti():
    source = Path("agent/main.py").read_text()

    assert '"MARUTI"' in source
    assert '"RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "MARUTI"' in source
