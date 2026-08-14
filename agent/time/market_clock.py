from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class MarketSession:
    open_time: time = time(9, 15)
    new_trade_cutoff: time = time(15, 0)
    square_off_time: time = time(15, 20)
    close_time: time = time(15, 30)


@dataclass
class MarketClock:
    session: MarketSession = field(default_factory=MarketSession)
    holidays: set[date] = field(default_factory=set)
    manually_closed_dates: set[date] = field(default_factory=set)

    def to_ist(self, moment: datetime | None = None) -> datetime:
        if moment is None:
            moment = datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(IST)

    def is_market_day(self, moment: datetime | None = None) -> bool:
        now_ist = self.to_ist(moment)
        today = now_ist.date()
        if now_ist.weekday() >= 5:
            return False
        if today in self.holidays or today in self.manually_closed_dates:
            return False
        return True

    def is_market_open(self, moment: datetime | None = None) -> bool:
        if not self.is_market_day(moment):
            return False
        now_ist = self.to_ist(moment)
        return self.session.open_time <= now_ist.time() <= self.session.close_time

    def is_new_trade_allowed(self, moment: datetime | None = None) -> bool:
        if not self.is_market_day(moment):
            return False
        now_ist = self.to_ist(moment)
        return self.session.open_time <= now_ist.time() < self.session.new_trade_cutoff

    def should_square_off(self, moment: datetime | None = None) -> bool:
        if not self.is_market_day(moment):
            return False
        now_ist = self.to_ist(moment)
        return self.session.square_off_time <= now_ist.time() <= self.session.close_time

    def seconds_until_next_open(self, moment: datetime | None = None) -> int:
        now_ist = self.to_ist(moment)
        candidate_day = now_ist.date()
        if self.is_market_day(now_ist) and now_ist.time() < self.session.open_time:
            next_open = datetime.combine(candidate_day, self.session.open_time, tzinfo=IST)
        else:
            next_day = candidate_day + timedelta(days=1)
            while not self.is_market_day(datetime.combine(next_day, self.session.open_time, tzinfo=IST)):
                next_day += timedelta(days=1)
            next_open = datetime.combine(next_day, self.session.open_time, tzinfo=IST)

        return max(0, int((next_open - now_ist).total_seconds()))
