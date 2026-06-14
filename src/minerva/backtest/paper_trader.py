"""
Minerva AI — Paper Trader.

Simulated order execution for paper trading mode.
Same interface as ExchangeGateway but executes against
virtual positions without sending real orders.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from minerva.logger import get_logger
from minerva.models.orders import Fill, Order, OrderSide

log = get_logger(__name__)


class PaperTrader:
    """
    Paper trading engine.

    Simulates order execution by filling orders at the current
    market price. Tracks a virtual balance and positions.
    Same interface as ExchangeGateway for seamless switching.
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        fee_rate: float = 0.001,  # 0.1% per trade
    ) -> None:
        """
        Initialize paper trader.

        Args:
            initial_balance: Starting virtual balance in USDT.
            fee_rate: Simulated fee rate per trade.
        """
        self._balance = initial_balance
        self._initial_balance = initial_balance
        self._fee_rate = fee_rate
        self._positions: dict[str, dict] = {}
        self._trade_history: list[dict] = []
        self._prices: dict[str, float] = {}

    async def connect(self) -> None:
        """No-op for paper trading."""
        log.info(
            "paper_trader_started",
            balance=self._initial_balance,
            fee_rate=self._fee_rate,
        )

    async def disconnect(self) -> None:
        """No-op for paper trading."""
        log.info("paper_trader_stopped", final_balance=round(self._balance, 2))

    def set_price(self, symbol: str, price: float) -> None:
        """Update current price for a symbol."""
        self._prices[symbol] = price

    async def submit_order(self, order: Order) -> Fill | None:
        """
        Simulate order execution at current market price.

        Args:
            order: The order to execute.

        Returns:
            Fill with simulated execution details.
        """
        price = self._prices.get(order.symbol, order.price or 0)
        if price <= 0:
            log.warning("paper_no_price", symbol=order.symbol)
            return None

        # Calculate trade value and fee
        trade_value = order.amount * price
        fee = trade_value * self._fee_rate

        # Check balance for buy orders
        if order.side == OrderSide.BUY:
            total_cost = trade_value + fee
            if total_cost > self._balance:
                log.warning(
                    "paper_insufficient_balance",
                    required=round(total_cost, 2),
                    available=round(self._balance, 2),
                )
                return None
            self._balance -= total_cost
        else:
            self._balance += trade_value - fee

        # Create fill
        fill = Fill(
            order_id=order.id,
            exchange_order_id=f"paper_{order.id}",
            symbol=order.symbol,
            exchange="paper",
            side=order.side,
            price=price,
            amount=order.amount,
            fee=fee,
            fee_currency="USDT",
            timestamp=datetime.now(tz=timezone.utc),
            trade_id=f"paper_trade_{order.id}",
        )

        self._trade_history.append({
            "order_id": order.id,
            "symbol": order.symbol,
            "side": order.side.value,
            "price": price,
            "amount": order.amount,
            "fee": fee,
            "balance_after": self._balance,
            "timestamp": fill.timestamp.isoformat(),
        })

        log.info(
            "paper_order_filled",
            symbol=order.symbol,
            side=order.side.value,
            price=round(price, 2),
            amount=round(order.amount, 8),
            fee=round(fee, 4),
            balance=round(self._balance, 2),
        )

        return fill

    async def cancel_order(
        self, exchange_order_id: str, symbol: str
    ) -> bool:
        """Paper orders are always filled immediately."""
        return True

    async def get_balance(self, currency: str = "USDT") -> float:
        """Get virtual balance."""
        if currency == "USDT":
            return self._balance
        return 0.0

    async def get_total_balance(self) -> dict[str, float]:
        """Get total virtual balance."""
        return {"USDT": self._balance}

    async def get_ticker(self, symbol: str) -> dict | None:
        """Get last known price as ticker."""
        price = self._prices.get(symbol)
        if price is None:
            return None
        return {
            "symbol": symbol,
            "last": price,
            "bid": price * 0.9999,
            "ask": price * 1.0001,
            "high": price * 1.01,
            "low": price * 0.99,
        }

    async def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        """Paper orders are filled immediately, no open orders."""
        return []

    def get_performance(self) -> dict:
        """Get paper trading performance summary."""
        total_pnl = self._balance - self._initial_balance
        pnl_pct = (total_pnl / self._initial_balance) * 100 if self._initial_balance > 0 else 0

        return {
            "initial_balance": self._initial_balance,
            "current_balance": round(self._balance, 2),
            "total_pnl": round(total_pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "total_trades": len(self._trade_history),
            "total_fees": round(
                sum(t.get("fee", 0) for t in self._trade_history), 4
            ),
        }
