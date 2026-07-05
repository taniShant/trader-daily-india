from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SignalAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TradeSignal(BaseModel):
    """Validated signal emitted before risk checks."""

    model_config = ConfigDict(extra="forbid")

    signal_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    exchange: str = Field(default="NSE", min_length=1)
    action: SignalAction
    confidence: int = Field(ge=0, le=100)
    generated_at: datetime
    entry_price: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    target_price: Decimal | None = Field(default=None, gt=0)
    holding_window_minutes: int | None = Field(default=None, gt=0)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    raw_features: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_trade_prices(self) -> "TradeSignal":
        if self.action == SignalAction.HOLD:
            return self

        missing = [
            name
            for name in ("entry_price", "stop_loss", "target_price", "holding_window_minutes")
            if getattr(self, name) is None
        ]
        if missing:
            raise ValueError(f"actionable signals require: {', '.join(missing)}")

        if self.action == SignalAction.BUY:
            if not self.stop_loss < self.entry_price < self.target_price:
                raise ValueError("BUY requires stop_loss < entry_price < target_price")
        elif self.action == SignalAction.SELL:
            if not self.target_price < self.entry_price < self.stop_loss:
                raise ValueError("SELL requires target_price < entry_price < stop_loss")

        return self
