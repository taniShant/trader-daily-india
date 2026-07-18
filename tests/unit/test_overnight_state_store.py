from decimal import Decimal

from agent.overnight.state_store import daily_state_key, decimalize, get_daily_state, put_daily_state


class FakeTable:
    def __init__(self):
        self.items = {}
        self.puts = []

    def get_item(self, Key):
        return {"Item": self.items.get(tuple(sorted(Key.items())), {})}

    def put_item(self, Item):
        self.puts.append(Item)
        key = {"date": Item["date"], "timestamp": Item["timestamp"]}
        self.items[tuple(sorted(key.items()))] = Item


def test_daily_state_key_matches_market_state_table_schema():
    assert daily_state_key("2026-07-18", "watchlist") == {
        "date": "2026-07-18",
        "timestamp": "state#watchlist",
    }


def test_put_daily_state_converts_floats_to_decimal_recursively():
    table = FakeTable()

    put_daily_state(
        table,
        "2026-07-18",
        "global_macro",
        {"score": 0.25, "nested": {"change": -1.5}, "items": [{"price": 100.1}]},
    )

    item = table.puts[0]
    assert item["date"] == "2026-07-18"
    assert item["timestamp"] == "state#global_macro"
    assert item["record_type"] == "global_macro"
    assert item["score"] == Decimal("0.25")
    assert item["nested"]["change"] == Decimal("-1.5")
    assert item["items"][0]["price"] == Decimal("100.1")


def test_get_daily_state_uses_composite_key():
    table = FakeTable()
    put_daily_state(table, "2026-07-18", "news", {"latest_sentiment": 0.1})

    item = get_daily_state(table, "2026-07-18", "news")

    assert item["latest_sentiment"] == Decimal("0.1")
