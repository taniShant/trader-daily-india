from agent.main import TradingBot


def _bot_stub():
    bot = TradingBot.__new__(TradingBot)
    bot.events = []
    bot.micro_engine = object()
    bot._check_circuit_breakers = lambda: True
    bot._should_square_off = lambda: False
    bot._is_new_trade_allowed = lambda: True
    bot._run_micro_trading_cycle = lambda: bot.events.append("micro")
    bot._monitor_positions = lambda: bot.events.append("monitor")
    bot._square_off_all = lambda: bot.events.append("square_off")
    return bot


def test_micro_market_cycle_runs_fast_lane_and_monitors_positions():
    bot = _bot_stub()

    bot._run_micro_market_cycle()

    assert bot.events == ["micro", "monitor"]


def test_micro_market_cycle_square_off_takes_priority():
    bot = _bot_stub()
    bot._should_square_off = lambda: True

    bot._run_micro_market_cycle()

    assert bot.events == ["square_off"]


def test_micro_market_cycle_only_monitors_after_new_trade_cutoff():
    bot = _bot_stub()
    bot._is_new_trade_allowed = lambda: False

    bot._run_micro_market_cycle()

    assert bot.events == ["monitor"]

