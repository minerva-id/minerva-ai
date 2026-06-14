"""
Minerva AI — Order Management System.

Tracks order lifecycle, positions, and PnL.
State persisted in Redis for fast access.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from minerva.logger import get_logger
from minerva.memory.redis_store import RedisStore
from minerva.models.orders import (
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    TradeRecord,
)
from minerva.models.signals import AggregatedSignal, TradeAction

log = get_logger(__name__)


class OrderManagementSystem:
    """
    Order Management System (OMS).

    Manages the full order lifecycle from creation to completion.
    Tracks positions with average entry price and PnL.
    All state is persisted in Redis.
    """

    def __init__(self, redis: RedisStore) -> None:
        """
        Initialize OMS.

        Args:
            redis: Redis store for state persistence.
        """
        self._redis = redis
        self._active_orders: dict[str, Order] = {}
        self._positions: dict[str, Position] = {}

    async def initialize(self) -> None:
        """Load existing positions from Redis on startup."""
        positions_data = await self._redis.get_all_positions()
        for symbol, data in positions_data.items():
            try:
                self._positions[symbol] = Position(**data)
                log.info(
                    "position_loaded",
                    symbol=symbol,
                    side=data.get("side"),
                    amount=data.get("amount"),
                )
            except Exception as e:
                log.warning("position_load_error", symbol=symbol, error=str(e))

    def create_order_from_signal(
        self,
        signal: AggregatedSignal,
        exchange: str,
        current_price: float,
        available_balance: float,
    ) -> Order | None:
        """
        Create an order from an aggregated signal.

        Args:
            signal: The trading signal/decision.
            exchange: Target exchange.
            current_price: Current market price.
            available_balance: Available balance in USD.

        Returns:
            Order if signal warrants an order, None otherwise.
        """
        if signal.action == TradeAction.HOLD:
            return None

        # Determine side
        if signal.action == TradeAction.BUY:
            side = OrderSide.BUY
        elif signal.action in (TradeAction.SELL, TradeAction.CLOSE):
            side = OrderSide.SELL
        else:
            return None

        # Calculate amount
        if signal.action == TradeAction.CLOSE:
            # Close entire position
            position = self._positions.get(signal.symbol)
            if not position or position.amount <= 0:
                log.info("no_position_to_close", symbol=signal.symbol)
                return None
            amount = position.amount
        else:
            # New position or adding to existing
            if signal.position_size_pct > 0:
                position_usd = available_balance * (signal.position_size_pct / 100)
            else:
                # Default: use 5% of available balance
                position_usd = available_balance * 0.05

            if current_price <= 0:
                return None
            amount = position_usd / current_price

        if amount <= 0:
            return None

        order = Order(
            symbol=signal.symbol,
            exchange=exchange,
            side=side,
            order_type=OrderType.MARKET,
            price=current_price,
            amount=amount,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            signal_score=signal.combined_score,
            reasoning=signal.reasoning,
        )

        log.info(
            "order_created",
            order_id=order.id,
            symbol=order.symbol,
            side=order.side.value,
            amount=round(order.amount, 8),
            price=round(current_price, 2),
        )

        return order

    async def submit_order(self, order: Order) -> None:
        """
        Mark order as submitted and track it.

        Args:
            order: The order to submit.
        """
        order.status = OrderStatus.SUBMITTED
        order.updated_at = datetime.now(tz=timezone.utc)
        self._active_orders[order.id] = order

        await self._redis.set_order(order.id, order.model_dump(mode="json"))
        log.info("order_submitted", order_id=order.id, symbol=order.symbol)

    async def process_fill(self, fill: Fill) -> TradeRecord | None:
        """
        Process an execution fill from the exchange.

        Updates order status and position tracking.

        Args:
            fill: Fill/execution report from exchange.

        Returns:
            TradeRecord if a position was closed, None otherwise.
        """
        # Update order
        order = self._active_orders.get(fill.order_id)
        if order:
            order.filled_amount += fill.amount
            order.average_fill_price = fill.price
            order.updated_at = datetime.now(tz=timezone.utc)

            if order.filled_amount >= order.amount:
                order.status = OrderStatus.FILLED
                self._active_orders.pop(order.id, None)
                await self._redis.delete_order(order.id)
            else:
                order.status = OrderStatus.PARTIALLY_FILLED
                await self._redis.set_order(order.id, order.model_dump(mode="json"))

        # Update position
        trade_record = await self._update_position(fill)

        log.info(
            "fill_processed",
            order_id=fill.order_id,
            symbol=fill.symbol,
            side=fill.side.value,
            price=round(fill.price, 2),
            amount=round(fill.amount, 8),
        )

        return trade_record

    async def _update_position(self, fill: Fill) -> TradeRecord | None:
        """Update position based on fill. Returns TradeRecord if position closed."""
        position = self._positions.get(fill.symbol)

        if fill.side == OrderSide.BUY:
            if position and position.side == OrderSide.SELL:
                # Closing a short position
                return await self._close_position(fill, position)
            else:
                # Opening or adding to long position
                await self._open_or_add_position(fill, OrderSide.BUY)
                return None

        else:  # SELL
            if position and position.side == OrderSide.BUY:
                # Closing a long position
                return await self._close_position(fill, position)
            else:
                # Opening or adding to short position
                await self._open_or_add_position(fill, OrderSide.SELL)
                return None

    async def _open_or_add_position(self, fill: Fill, side: OrderSide) -> None:
        """Open a new position or add to existing."""
        position = self._positions.get(fill.symbol)

        if position and position.side == side:
            # Average in
            total_cost = (position.entry_price * position.amount) + (
                fill.price * fill.amount
            )
            position.amount += fill.amount
            position.entry_price = total_cost / position.amount if position.amount > 0 else 0
            position.updated_at = datetime.now(tz=timezone.utc)
        else:
            # New position
            position = Position(
                symbol=fill.symbol,
                exchange=fill.exchange,
                side=side,
                amount=fill.amount,
                entry_price=fill.price,
                current_price=fill.price,
            )

        self._positions[fill.symbol] = position
        await self._redis.set_position(
            fill.symbol, position.model_dump(mode="json")
        )

        log.info(
            "position_updated",
            symbol=fill.symbol,
            side=side.value,
            amount=round(position.amount, 8),
            entry_price=round(position.entry_price, 2),
        )

    async def _close_position(
        self, fill: Fill, position: Position
    ) -> TradeRecord:
        """Close a position and generate trade record."""
        # Calculate PnL
        if position.side == OrderSide.BUY:
            pnl = (fill.price - position.entry_price) * fill.amount
        else:
            pnl = (position.entry_price - fill.price) * fill.amount

        pnl_pct = 0.0
        if position.entry_price > 0:
            if position.side == OrderSide.BUY:
                pnl_pct = ((fill.price - position.entry_price) / position.entry_price) * 100
            else:
                pnl_pct = ((position.entry_price - fill.price) / position.entry_price) * 100

        entry_time = position.opened_at
        exit_time = datetime.now(tz=timezone.utc)
        duration = int((exit_time - entry_time).total_seconds())

        trade = TradeRecord(
            symbol=fill.symbol,
            exchange=fill.exchange,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=fill.price,
            amount=fill.amount,
            pnl=round(pnl, 4),
            pnl_pct=round(pnl_pct, 4),
            fees_total=fill.fee,
            entry_time=entry_time,
            exit_time=exit_time,
            duration_seconds=duration,
            signal_score=None,
        )

        # Remove position if fully closed
        remaining = position.amount - fill.amount
        if remaining <= 0.0001:  # Dust threshold
            self._positions.pop(fill.symbol, None)
            await self._redis.delete_position(fill.symbol)
        else:
            position.amount = remaining
            position.realized_pnl += pnl
            position.updated_at = exit_time
            self._positions[fill.symbol] = position
            await self._redis.set_position(
                fill.symbol, position.model_dump(mode="json")
            )

        log.info(
            "position_closed",
            symbol=fill.symbol,
            pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 2),
            duration_s=duration,
        )

        return trade

    def get_position(self, symbol: str) -> Position | None:
        """Get current position for a symbol."""
        return self._positions.get(symbol)

    def get_all_positions(self) -> dict[str, Position]:
        """Get all open positions."""
        return dict(self._positions)

    def get_active_orders(self) -> dict[str, Order]:
        """Get all active orders."""
        return dict(self._active_orders)

    def has_position(self, symbol: str) -> bool:
        """Check if there is an open position for a symbol."""
        pos = self._positions.get(symbol)
        return pos is not None and pos.amount > 0.0001

    def get_total_exposure(self) -> float:
        """Get total portfolio exposure in USD."""
        return sum(pos.notional_value for pos in self._positions.values())

    def update_prices(self, prices: dict[str, float]) -> None:
        """Update current prices for all positions."""
        for symbol, price in prices.items():
            if symbol in self._positions:
                self._positions[symbol].update_price(price)
