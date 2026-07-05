from datetime import date, datetime, timezone

from agent.time.market_clock import MarketClock


def utc_at(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def test_market_open_window_uses_ist_trading_hours():
    clock = MarketClock()

    assert clock.is_market_open(utc_at(2026, 7, 6, 3, 44)) is False
    assert clock.is_market_open(utc_at(2026, 7, 6, 3, 45)) is True
    assert clock.is_market_open(utc_at(2026, 7, 6, 10, 0)) is True
    assert clock.is_market_open(utc_at(2026, 7, 6, 10, 1)) is False


def test_new_trade_cutoff_blocks_fresh_entries_before_square_off():
    clock = MarketClock()

    assert clock.is_new_trade_allowed(utc_at(2026, 7, 6, 9, 29)) is True
    assert clock.is_new_trade_allowed(utc_at(2026, 7, 6, 9, 30)) is False
    assert clock.is_market_open(utc_at(2026, 7, 6, 9, 30)) is True


def test_square_off_window_starts_at_three_twenty_pm_ist():
    clock = MarketClock()

    assert clock.should_square_off(utc_at(2026, 7, 6, 9, 49)) is False
    assert clock.should_square_off(utc_at(2026, 7, 6, 9, 50)) is True
    assert clock.should_square_off(utc_at(2026, 7, 6, 10, 0)) is True
    assert clock.should_square_off(utc_at(2026, 7, 6, 10, 1)) is False


def test_weekends_are_not_market_days():
    clock = MarketClock()

    assert clock.is_market_day(utc_at(2026, 7, 4, 4, 0)) is False
    assert clock.is_market_open(utc_at(2026, 7, 4, 4, 0)) is False


def test_holidays_and_manual_closed_dates_block_trading():
    closed_day = date(2026, 7, 6)
    holiday_clock = MarketClock(holidays={closed_day})
    manual_clock = MarketClock(manually_closed_dates={closed_day})
    moment = utc_at(2026, 7, 6, 4, 0)

    assert holiday_clock.is_market_day(moment) is False
    assert holiday_clock.is_market_open(moment) is False
    assert manual_clock.is_market_day(moment) is False
    assert manual_clock.is_new_trade_allowed(moment) is False


def test_naive_datetimes_are_treated_as_utc():
    clock = MarketClock()
    naive_utc = datetime(2026, 7, 6, 3, 45)

    assert clock.is_market_open(naive_utc) is True
