from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .execution import OrderSide, OrderType


class RiskDecisionStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RiskDecision(BaseModel):
    """Decision emitted by deterministic risk checks before execution."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    status: RiskDecisionStatus
    decided_at: datetime
    reasons: list[str] = Field(default_factory=list)
    approved_quantity: int | None = Field(default=None, gt=0)
    approved_price: Decimal | None = Field(default=None, gt=0)
    side: OrderSide | None = None
    order_type: OrderType | None = None
    max_loss_amount: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_approved_fields(self) -> "RiskDecision":
        if self.status == RiskDecisionStatus.APPROVED:
            missing = [
                name
                for name in ("approved_quantity", "approved_price", "side", "order_type")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"approved decisions require: {', '.join(missing)}")
        elif not self.reasons:
            raise ValueError("rejected decisions require at least one reason")
        return self
