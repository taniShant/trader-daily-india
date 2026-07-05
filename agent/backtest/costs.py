from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TradeCosts:
    brokerage: Decimal
    taxes: Decimal
    slippage: Decimal

    @property
    def total(self) -> Decimal:
        return self.brokerage + self.taxes + self.slippage


@dataclass(frozen=True)
class CostModel:
    brokerage_bps: Decimal = Decimal("3")
    taxes_bps: Decimal = Decimal("6")
    slippage_bps: Decimal = Decimal("5")

    def estimate(self, *, entry_price: Decimal, exit_price: Decimal, quantity: int) -> TradeCosts:
        turnover = (entry_price + exit_price) * Decimal(quantity)
        return TradeCosts(
            brokerage=self._bps_cost(turnover, self.brokerage_bps),
            taxes=self._bps_cost(turnover, self.taxes_bps),
            slippage=self._bps_cost(turnover, self.slippage_bps),
        )

    def net_pnl(self, *, gross_pnl: Decimal, entry_price: Decimal, exit_price: Decimal, quantity: int) -> Decimal:
        return gross_pnl - self.estimate(entry_price=entry_price, exit_price=exit_price, quantity=quantity).total

    @staticmethod
    def _bps_cost(turnover: Decimal, bps: Decimal) -> Decimal:
        return turnover * bps / Decimal("10000")
