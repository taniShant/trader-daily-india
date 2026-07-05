from agent.contracts.execution import OrderStatus
from agent.execution.square_off import square_off_positions


class FakeBroker:
    def __init__(self, status=OrderStatus.FILLED):
        self.status = status
        self.calls = []

    def square_off(self, symbol, quantity):
        self.calls.append((symbol, quantity))
        return self.status


def test_square_off_positions_squares_all_open_positions():
    broker = FakeBroker()
    positions = {
        "RELIANCE": {"quantity": 10},
        "TCS": {"quantity": -5},
    }

    results = square_off_positions(broker, positions)

    assert broker.calls == [("RELIANCE", 10), ("TCS", 5)]
    assert all(result.success for result in results)
    assert [result.status for result in results] == [OrderStatus.FILLED, OrderStatus.FILLED]


def test_square_off_positions_reports_zero_and_failed_positions():
    zero_results = square_off_positions(FakeBroker(), {"INFY": {"quantity": 0}})
    failed_results = square_off_positions(FakeBroker(OrderStatus.REJECTED), {"SBIN": {"quantity": 1}})

    assert zero_results[0].success is False
    assert zero_results[0].reason == "no open quantity"
    assert failed_results[0].success is False
    assert failed_results[0].status == OrderStatus.REJECTED
