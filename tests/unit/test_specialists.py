import sys
import types


def install_fake_strands(monkeypatch):
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


def test_all_specialists_construct_without_memory_or_external_clients(monkeypatch):
    install_fake_strands(monkeypatch)

    for module_name in list(sys.modules):
        if module_name.startswith("agent.specialists."):
            monkeypatch.delitem(sys.modules, module_name, raising=False)

    from agent.specialists.derivatives import DerivativesAnalyst
    from agent.specialists.fundamentals import FundamentalAnalyst
    from agent.specialists.sentiment import SentimentAnalyst
    from agent.specialists.social import SocialAnalyst
    from agent.specialists.technical import TechnicalAnalyst

    specialists = [
        TechnicalAnalyst(model="fake-model"),
        SentimentAnalyst(model="fake-model"),
        FundamentalAnalyst(model="fake-model"),
        SocialAnalyst(model="fake-model"),
        DerivativesAnalyst(model="fake-model"),
    ]

    assert [item.kwargs["name"] for item in specialists] == [
        "TechnicalAnalyst",
        "SentimentAnalyst",
        "FundamentalAnalyst",
        "SocialAnalyst",
        "DerivativesAnalyst",
    ]
    assert all(item.kwargs["model"] == "fake-model" for item in specialists)
    assert all(item.kwargs["tools"] for item in specialists)
