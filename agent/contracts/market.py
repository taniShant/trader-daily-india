from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Quote(BaseModel):
    """Normalized live quote used by signal, risk, and execution code."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    exchange: str = Field(default="NSE", min_length=1)
    ltp: Decimal = Field(gt=0)
    open: Decimal | None = Field(default=None, gt=0)
    high: Decimal | None = Field(default=None, gt=0)
    low: Decimal | None = Field(default=None, gt=0)
    previous_close: Decimal | None = Field(default=None, gt=0)
    volume: int | None = Field(default=None, ge=0)
    source: str = Field(min_length=1)
    timestamp: datetime

    @model_validator(mode="after")
    def validate_day_range(self) -> "Quote":
        if self.high is not None and self.low is not None and self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        if self.high is not None and self.ltp > self.high:
            raise ValueError("ltp cannot be greater than high")
        if self.low is not None and self.ltp < self.low:
            raise ValueError("ltp cannot be lower than low")
        return self


class OHLCVBar(BaseModel):
    """Normalized OHLCV candle."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    exchange: str = Field(default="NSE", min_length=1)
    timestamp: datetime
    interval: Literal["1m", "3m", "5m", "15m", "30m", "1h", "1d"]
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: int = Field(ge=0)
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_ohlc_range(self) -> "OHLCVBar":
        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        for name in ("open", "close"):
            value = getattr(self, name)
            if value > self.high or value < self.low:
                raise ValueError(f"{name} must be within low/high range")
        return self
