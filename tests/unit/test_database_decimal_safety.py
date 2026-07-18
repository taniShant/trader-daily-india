from dataclasses import dataclass
from decimal import Decimal

import agent.tools.database as database


@dataclass
class Signal:
    date: str = "2026-07-18"
    stock_symbol: str = "RELIANCE"
    action: str = "BUY"
    confidence: int = 75
    entry_price: float = 100.25
    stop_loss: float = 98.5
    target_price: float = 104.75
    reasoning: str = "test"
    technical_summary: str = "test"
    sentiment_score: float = 0.2
    risk_level: str = "LOW"


def test_save_trade_signal_converts_floats_to_decimal(monkeypatch):
    saved = {}

    class FakeTable:
        def put_item(self, Item):
            saved.update(Item)

    class FakeDynamo:
        def Table(self, name):
            return FakeTable()

    monkeypatch.setattr(database.boto3, "resource", lambda *args, **kwargs: FakeDynamo())

    database.save_trade_signal(Signal())

    assert saved["entry_price"] == Decimal("100.25")
    assert saved["stop_loss"] == Decimal("98.5")
    assert saved["target_price"] == Decimal("104.75")
    assert saved["sentiment_score"] == Decimal("0.2")
    assert saved["pnl"] == Decimal("0.0")
