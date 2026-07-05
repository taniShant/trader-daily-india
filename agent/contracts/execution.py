from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class OrderRequest(BaseModel):
    """Order request sent to a broker implementation."""

    model_config = ConfigDict(extra="forbid")

    client_order_id: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    risk_decision_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    exchange: str = Field(default="NSE", min_length=1)
    side: OrderSide
    order_type: OrderType
    quantity: int = Field(gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    target_price: Decimal | None = Field(default=None, gt=0)
    product_type: str = Field(default="intraday")
    requested_at: datetime

    @model_validator(mode="after")
    def validate_order_price(self) -> "OrderRequest":
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("limit orders require price")
        return self


class Fill(BaseModel):
    """Execution fill received from paper broker, Oracle proxy, or Breeze."""

    model_config = ConfigDict(extra="forbid")

    fill_id: str = Field(min_length=1)
    client_order_id: str = Field(min_length=1)
    broker_order_id: str | None = None
    symbol: str = Field(min_length=1)
    side: OrderSide
    quantity: int = Field(gt=0)
    fill_price: Decimal = Field(gt=0)
    filled_at: datetime
    source: str = Field(min_length=1)
