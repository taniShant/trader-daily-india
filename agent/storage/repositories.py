from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from agent.config import settings
from agent.contracts.execution import Fill, OrderRequest, OrderStatus
from agent.contracts.risk import RiskDecision
from agent.contracts.signals import TradeSignal
from agent.overnight.state_store import decimalize


@dataclass(frozen=True)
class BotHeartbeat:
    bot_id: str
    status: str
    mode: str
    environment: str
    cycle: int
    market_open: bool
    active_positions: int
    daily_pnl: Decimal
    updated_at: datetime

    def to_item(self) -> dict[str, Any]:
        updated_at = self.updated_at.astimezone(timezone.utc)
        return {
            "date": f"heartbeat#{self.bot_id}",
            "timestamp": updated_at.isoformat(),
            "record_type": "bot_heartbeat",
            "bot_id": self.bot_id,
            "status": self.status,
            "mode": self.mode,
            "environment": self.environment,
            "cycle": self.cycle,
            "market_open": self.market_open,
            "active_positions": self.active_positions,
            "daily_pnl": self.daily_pnl,
        }


class MarketStateRepository:
    def __init__(self, table):
        self.table = table

    def put_heartbeat(self, heartbeat: BotHeartbeat) -> None:
        self.table.put_item(Item=heartbeat.to_item())


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    session_id: str
    quantity: int
    average_price: Decimal
    last_price: Decimal
    unrealized_pnl: Decimal
    updated_at: datetime
    side: str = "LONG"
    status: str = "OPEN"

    def to_item(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "session_id": self.session_id,
            "quantity": self.quantity,
            "average_price": self.average_price,
            "last_price": self.last_price,
            "unrealized_pnl": self.unrealized_pnl,
            "updated_at": _utc_iso(self.updated_at),
            "side": self.side,
            "status": self.status,
        }


@dataclass(frozen=True)
class PnlRecord:
    trade_id: str
    date: str
    symbol: str
    realized_pnl: Decimal
    gross_pnl: Decimal
    costs: Decimal
    session_id: str
    closed_at: datetime

    def to_item(self) -> dict[str, Any]:
        return {
            "tradeId": self.trade_id,
            "date": self.date,
            "stock_symbol": self.symbol,
            "pnl": self.realized_pnl,
            "gross_pnl": self.gross_pnl,
            "costs": self.costs,
            "session_id": self.session_id,
            "closed_at": _utc_iso(self.closed_at),
        }


@dataclass(frozen=True)
class TradeEventRecord:
    trade_id: str
    date: str
    timestamp: datetime
    symbol: str
    action: str
    price: Decimal
    quantity: int
    pnl: Decimal
    session_id: str
    signal_id: str
    order_id: str
    status: str
    source: str
    confidence: int

    def to_item(self) -> dict[str, Any]:
        return {
            "tradeId": self.trade_id,
            "date": self.date,
            "timestamp": _utc_iso(self.timestamp),
            "stock_symbol": self.symbol,
            "action": self.action,
            "price": self.price,
            "quantity": self.quantity,
            "pnl": self.pnl,
            "session_id": self.session_id,
            "signal_id": self.signal_id,
            "order_id": self.order_id,
            "status": self.status,
            "source": self.source,
            "confidence": self.confidence,
        }


class SignalsRepository:
    def __init__(self, table):
        self.table = table

    def put_signal(self, signal: TradeSignal, *, session_id: str | None = None) -> None:
        item = _model_item(signal)
        item["created_at"] = _utc_iso(signal.generated_at)
        if session_id:
            item["session_id"] = session_id
        self.table.put_item(Item=item)


class RiskEventsRepository:
    def __init__(self, table):
        self.table = table

    def put_decision(self, decision: RiskDecision) -> None:
        item = _model_item(decision)
        item["risk_decision_id"] = decision.decision_id
        item["created_at"] = _utc_iso(decision.decided_at)
        self.table.put_item(Item=item)


class OrdersRepository:
    def __init__(self, table):
        self.table = table

    def put_order(self, order: OrderRequest, *, status: OrderStatus, broker_order_id: str | None = None) -> None:
        item = _model_item(order)
        item["status"] = status.value
        item["updated_at"] = _utc_iso(order.requested_at)
        if broker_order_id:
            item["broker_order_id"] = broker_order_id
        self.table.put_item(Item=item)


class FillsRepository:
    def __init__(self, table):
        self.table = table

    def put_fill(self, fill: Fill) -> None:
        item = _model_item(fill)
        item["filled_at"] = _utc_iso(fill.filled_at)
        self.table.put_item(Item=item)


class PositionsRepository:
    def __init__(self, table):
        self.table = table

    def put_snapshot(self, snapshot: PositionSnapshot) -> None:
        self.table.put_item(Item=snapshot.to_item())


class PnlRepository:
    def __init__(self, table):
        self.table = table

    def put_pnl(self, pnl: PnlRecord) -> None:
        self.table.put_item(Item=pnl.to_item())

    def put_trade_event(self, trade: TradeEventRecord) -> None:
        self.table.put_item(Item=decimalize(trade.to_item()))


@dataclass(frozen=True)
class TradingAuditRepositories:
    signals: SignalsRepository
    risk_events: RiskEventsRepository
    orders: OrdersRepository
    fills: FillsRepository
    positions: PositionsRepository
    pnl: PnlRepository


def _model_item(model) -> dict[str, Any]:
    return decimalize(_dynamo_value(model.model_dump(mode="python")))


def _dynamo_value(value):
    if isinstance(value, datetime):
        return _utc_iso(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _dynamo_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_dynamo_value(item) for item in value]
    return value


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def build_bot_heartbeat(
    *,
    bot_id: str,
    status: str,
    mode: str,
    environment: str,
    cycle: int,
    market_open: bool,
    active_positions: int,
    daily_pnl: Decimal,
    updated_at: datetime | None = None,
) -> BotHeartbeat:
    return BotHeartbeat(
        bot_id=bot_id,
        status=status,
        mode=mode,
        environment=environment,
        cycle=cycle,
        market_open=market_open,
        active_positions=active_positions,
        daily_pnl=daily_pnl,
        updated_at=updated_at or datetime.now(timezone.utc),
    )


def market_state_repository() -> MarketStateRepository:
    import boto3

    dynamodb = boto3.resource("dynamodb", region_name=settings.aws.region)
    return MarketStateRepository(dynamodb.Table(settings.dynamodb.market_state_table))


def trading_audit_repositories() -> TradingAuditRepositories:
    import boto3

    dynamodb = boto3.resource("dynamodb", region_name=settings.aws.region)
    return TradingAuditRepositories(
        signals=SignalsRepository(dynamodb.Table(settings.dynamodb.signals_table)),
        risk_events=RiskEventsRepository(dynamodb.Table(settings.dynamodb.risk_events_table)),
        orders=OrdersRepository(dynamodb.Table(settings.dynamodb.orders_table)),
        fills=FillsRepository(dynamodb.Table(settings.dynamodb.fills_table)),
        positions=PositionsRepository(dynamodb.Table(settings.dynamodb.positions_table)),
        pnl=PnlRepository(dynamodb.Table(settings.dynamodb.trades_table)),
    )
