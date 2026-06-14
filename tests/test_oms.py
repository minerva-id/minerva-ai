"""
Tests for the Order Management System.

Validates order creation, fill processing, position tracking,
and PnL calculation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from minerva.execution.oms import OrderManagementSystem
from minerva.models.orders import Fill, Order, OrderSide, OrderType, Position
from minerva.models.signals import AggregatedSignal, TradeAction


@pytest.fixture
def mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get_all_positions = AsyncMock(return_value={})
    redis.set_position = AsyncMock()
    redis.delete_position = AsyncMock()
    redis.set_order = AsyncMock()
    redis.delete_order = AsyncMock()
    return redis


@pytest.fixture
async def oms(mock_redis: AsyncMock) -> OrderManagementSystem:
    o = OrderManagementSystem(mock_redis)
    await o.initialize()
    return o


class TestOrderCreation:
    """Test order creation from signals."""

    @pytest.mark.asyncio
    async def test_create_buy_order(self, oms: OrderManagementSystem) -> None:
        """Buy signal should create a buy order."""
        signal = AggregatedSignal(
            symbol="BTC/USDT",
            action=TradeAction.BUY,
            combined_score=0.7,
            confidence=0.8,
            position_size_pct=10.0,
        )
        order = oms.create_order_from_signal(
            signal=signal,
            exchange="binance",
            current_price=50000.0,
            available_balance=10000.0,
        )
        assert order is not None
        assert order.side == OrderSide.BUY
        assert order.symbol == "BTC/USDT"
        assert order.amount > 0

    @pytest.mark.asyncio
    async def test_hold_creates_no_order(self, oms: OrderManagementSystem) -> None:
        """HOLD signal should not create an order."""
        signal = AggregatedSignal(
            symbol="BTC/USDT",
            action=TradeAction.HOLD,
            combined_score=0.0,
        )
        order = oms.create_order_from_signal(
            signal=signal,
            exchange="binance",
            current_price=50000.0,
            available_balance=10000.0,
        )
        assert order is None

    @pytest.mark.asyncio
    async def test_position_size_calculation(
        self, oms: OrderManagementSystem
    ) -> None:
        """Order amount should match position size percentage."""
        signal = AggregatedSignal(
            symbol="ETH/USDT",
            action=TradeAction.BUY,
            combined_score=0.5,
            confidence=0.7,
            position_size_pct=20.0,  # 20% of $10,000 = $2,000
        )
        order = oms.create_order_from_signal(
            signal=signal,
            exchange="binance",
            current_price=2000.0,
            available_balance=10000.0,
        )
        assert order is not None
        # $2,000 / $2,000 = 1.0 ETH
        assert abs(order.amount - 1.0) < 0.001


class TestFillProcessing:
    """Test fill processing and position tracking."""

    @pytest.mark.asyncio
    async def test_process_buy_fill_opens_position(
        self, oms: OrderManagementSystem
    ) -> None:
        """Buy fill should open a new position."""
        # Submit an order first
        order = Order(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=0.1,
        )
        await oms.submit_order(order)

        fill = Fill(
            order_id=order.id,
            exchange_order_id="ex_123",
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.BUY,
            price=50000.0,
            amount=0.1,
        )

        result = await oms.process_fill(fill)
        assert result is None  # No trade record for open
        assert oms.has_position("BTC/USDT")

        pos = oms.get_position("BTC/USDT")
        assert pos is not None
        assert pos.amount == 0.1
        assert pos.entry_price == 50000.0

    @pytest.mark.asyncio
    async def test_process_sell_fill_closes_position(
        self, oms: OrderManagementSystem, mock_redis: AsyncMock
    ) -> None:
        """Sell fill should close position and return trade record."""
        # Open position manually
        buy_order = Order(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=0.1,
        )
        await oms.submit_order(buy_order)
        buy_fill = Fill(
            order_id=buy_order.id,
            exchange_order_id="ex_buy",
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.BUY,
            price=50000.0,
            amount=0.1,
        )
        await oms.process_fill(buy_fill)

        # Now sell to close
        sell_order = Order(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=0.1,
        )
        await oms.submit_order(sell_order)
        sell_fill = Fill(
            order_id=sell_order.id,
            exchange_order_id="ex_sell",
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.SELL,
            price=55000.0,
            amount=0.1,
        )

        trade_record = await oms.process_fill(sell_fill)
        assert trade_record is not None
        assert trade_record.pnl > 0  # Profit: (55000-50000) * 0.1 = 500
        assert abs(trade_record.pnl - 500.0) < 0.01
        assert not oms.has_position("BTC/USDT")

    @pytest.mark.asyncio
    async def test_pnl_calculation_profit(
        self, oms: OrderManagementSystem
    ) -> None:
        """PnL should be positive for profitable trade."""
        # Buy at 50000, sell at 52000
        buy_order = Order(
            symbol="ETH/USDT", exchange="binance",
            side=OrderSide.BUY, order_type=OrderType.MARKET, amount=1.0,
        )
        await oms.submit_order(buy_order)
        await oms.process_fill(Fill(
            order_id=buy_order.id, exchange_order_id="b1",
            symbol="ETH/USDT", exchange="binance",
            side=OrderSide.BUY, price=2000.0, amount=1.0,
        ))

        sell_order = Order(
            symbol="ETH/USDT", exchange="binance",
            side=OrderSide.SELL, order_type=OrderType.MARKET, amount=1.0,
        )
        await oms.submit_order(sell_order)
        record = await oms.process_fill(Fill(
            order_id=sell_order.id, exchange_order_id="s1",
            symbol="ETH/USDT", exchange="binance",
            side=OrderSide.SELL, price=2200.0, amount=1.0,
        ))

        assert record is not None
        assert record.pnl == 200.0
        assert record.pnl_pct == 10.0

    @pytest.mark.asyncio
    async def test_pnl_calculation_loss(
        self, oms: OrderManagementSystem
    ) -> None:
        """PnL should be negative for losing trade."""
        buy_order = Order(
            symbol="SOL/USDT", exchange="binance",
            side=OrderSide.BUY, order_type=OrderType.MARKET, amount=10.0,
        )
        await oms.submit_order(buy_order)
        await oms.process_fill(Fill(
            order_id=buy_order.id, exchange_order_id="b1",
            symbol="SOL/USDT", exchange="binance",
            side=OrderSide.BUY, price=100.0, amount=10.0,
        ))

        sell_order = Order(
            symbol="SOL/USDT", exchange="binance",
            side=OrderSide.SELL, order_type=OrderType.MARKET, amount=10.0,
        )
        await oms.submit_order(sell_order)
        record = await oms.process_fill(Fill(
            order_id=sell_order.id, exchange_order_id="s1",
            symbol="SOL/USDT", exchange="binance",
            side=OrderSide.SELL, price=90.0, amount=10.0,
        ))

        assert record is not None
        assert record.pnl == -100.0
        assert record.pnl_pct == -10.0


class TestPositionTracking:
    """Test position tracking functionality."""

    @pytest.mark.asyncio
    async def test_total_exposure(self, oms: OrderManagementSystem) -> None:
        """Total exposure should sum all position notional values."""
        # Open two positions
        for symbol, price, amount in [("BTC/USDT", 50000, 0.1), ("ETH/USDT", 2000, 1.0)]:
            order = Order(
                symbol=symbol, exchange="binance",
                side=OrderSide.BUY, order_type=OrderType.MARKET, amount=amount,
            )
            await oms.submit_order(order)
            await oms.process_fill(Fill(
                order_id=order.id, exchange_order_id=f"ex_{symbol}",
                symbol=symbol, exchange="binance",
                side=OrderSide.BUY, price=float(price), amount=float(amount),
            ))

        # Update prices
        oms.update_prices({"BTC/USDT": 50000.0, "ETH/USDT": 2000.0})

        exposure = oms.get_total_exposure()
        # BTC: 0.1 * 50000 = 5000, ETH: 1.0 * 2000 = 2000
        assert abs(exposure - 7000.0) < 0.01
