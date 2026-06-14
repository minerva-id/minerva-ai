"""
Minerva AI — Order, position, and trade models.

Models for the full order lifecycle: creation, execution, fill, and journaling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Order(BaseModel):
    """Trading order with full lifecycle tracking."""

    id: str = Field(default_factory=lambda: uuid4().hex[:16])
    symbol: str
    exchange: str
    side: OrderSide
    order_type: OrderType
    price: float | None = None
    amount: float = Field(..., gt=0)
    filled_amount: float = Field(default=0.0, ge=0)
    average_fill_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    exchange_order_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    stop_loss: float | None = None
    take_profit: float | None = None

    # Agent decision context
    signal_score: float | None = None
    reasoning: str = ""

    @property
    def is_active(self) -> bool:
        return self.status in (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIALLY_FILLED,
        )

    @property
    def is_complete(self) -> bool:
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )

    @property
    def remaining_amount(self) -> float:
        return max(0.0, self.amount - self.filled_amount)


class Fill(BaseModel):
    """Execution report / fill from exchange."""

    order_id: str
    exchange_order_id: str
    symbol: str
    exchange: str
    side: OrderSide
    price: float = Field(..., gt=0)
    amount: float = Field(..., gt=0)
    fee: float = Field(default=0.0, ge=0)
    fee_currency: str = "USDT"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    trade_id: str = ""


class Position(BaseModel):
    """Open trading position."""

    symbol: str
    exchange: str
    side: OrderSide
    amount: float = Field(default=0.0, ge=0)
    entry_price: float = Field(default=0.0, ge=0)
    current_price: float = Field(default=0.0, ge=0)
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    opened_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    @property
    def notional_value(self) -> float:
        return self.amount * self.current_price

    @property
    def pnl_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        if self.side == OrderSide.BUY:
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - self.current_price) / self.entry_price) * 100

    def update_price(self, price: float) -> None:
        """Update current price and recalculate unrealized PnL."""
        self.current_price = price
        if self.side == OrderSide.BUY:
            self.unrealized_pnl = (price - self.entry_price) * self.amount
        else:
            self.unrealized_pnl = (self.entry_price - price) * self.amount
        self.updated_at = datetime.now(tz=timezone.utc)


class TradeRecord(BaseModel):
    """Completed trade record for journaling and analysis."""

    id: str = Field(default_factory=lambda: uuid4().hex[:16])
    symbol: str
    exchange: str
    side: OrderSide
    entry_price: float
    exit_price: float
    amount: float
    pnl: float
    pnl_pct: float
    fees_total: float = 0.0
    entry_time: datetime
    exit_time: datetime
    duration_seconds: int = 0
    signal_score: float | None = None
    reasoning: str = ""
    strategy: str = "minerva_v1"
