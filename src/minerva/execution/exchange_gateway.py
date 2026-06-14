"""
Minerva AI — Exchange Gateway.

Async order execution via ccxt REST + WebSocket user stream.
Supports Binance, Bybit, OKX with retry logic and error handling.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import ccxt.async_support as ccxt_async

from minerva.logger import get_logger
from minerva.models.orders import Fill, Order, OrderSide, OrderStatus, OrderType

log = get_logger(__name__)


class ExchangeGateway:
    """
    Exchange gateway for order execution.

    Handles async order submission, cancellation, and balance queries
    via ccxt REST API. Supports multiple exchanges.
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 1.0

    def __init__(
        self,
        exchange_id: str,
        credentials: dict[str, str],
        sandbox: bool = False,
    ) -> None:
        """
        Initialize exchange gateway.

        Args:
            exchange_id: Exchange identifier (binance, bybit, okx).
            credentials: API credentials.
            sandbox: If True, use exchange testnet.
        """
        self._exchange_id = exchange_id
        self._credentials = credentials
        self._sandbox = sandbox
        self._exchange: Any = None

    async def connect(self) -> None:
        """Initialize exchange connection."""
        exchange_class = getattr(ccxt_async, self._exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Exchange '{self._exchange_id}' not supported")

        filtered_creds = {k: v for k, v in self._credentials.items() if v}

        self._exchange = exchange_class({
            **filtered_creds,
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
            },
        })

        if self._sandbox:
            self._exchange.set_sandbox_mode(True)

        # Load markets
        await self._exchange.load_markets()
        log.info(
            "exchange_connected",
            exchange=self._exchange_id,
            sandbox=self._sandbox,
            markets=len(self._exchange.markets),
        )

    async def disconnect(self) -> None:
        """Close exchange connection."""
        if self._exchange:
            await self._exchange.close()
            self._exchange = None
        log.info("exchange_disconnected", exchange=self._exchange_id)

    async def submit_order(self, order: Order) -> Fill | None:
        """
        Submit an order to the exchange with retry logic.

        Args:
            order: The order to submit.

        Returns:
            Fill if order was executed, None on failure.
        """
        if not self._exchange:
            log.error("exchange_not_connected")
            return None

        for attempt in range(self.MAX_RETRIES):
            try:
                # Build ccxt order params
                params: dict[str, Any] = {}

                # Add stop loss / take profit as separate orders if supported
                if order.stop_loss:
                    params["stopLoss"] = {"triggerPrice": order.stop_loss}
                if order.take_profit:
                    params["takeProfit"] = {"triggerPrice": order.take_profit}

                if order.order_type == OrderType.MARKET:
                    result = await self._exchange.create_order(
                        symbol=order.symbol,
                        type="market",
                        side=order.side.value,
                        amount=order.amount,
                        params=params,
                    )
                elif order.order_type == OrderType.LIMIT:
                    if order.price is None:
                        log.error("limit_order_no_price", order_id=order.id)
                        return None
                    result = await self._exchange.create_order(
                        symbol=order.symbol,
                        type="limit",
                        side=order.side.value,
                        amount=order.amount,
                        price=order.price,
                        params=params,
                    )
                else:
                    log.warning("unsupported_order_type", type=order.order_type.value)
                    return None

                # Parse result into Fill
                fill = self._parse_fill(order, result)

                log.info(
                    "order_executed",
                    order_id=order.id,
                    exchange_order_id=result.get("id", ""),
                    symbol=order.symbol,
                    side=order.side.value,
                    filled=result.get("filled", 0),
                    avg_price=result.get("average", 0),
                )

                return fill

            except ccxt_async.NetworkError as e:
                log.warning(
                    "exchange_network_error",
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAY * (2 ** attempt))

            except ccxt_async.ExchangeError as e:
                log.error(
                    "exchange_order_error",
                    order_id=order.id,
                    error=str(e),
                )
                return None

            except Exception as e:
                log.error(
                    "exchange_unexpected_error",
                    order_id=order.id,
                    error=str(e),
                )
                return None

        log.error("order_max_retries_exceeded", order_id=order.id)
        return None

    async def cancel_order(
        self, exchange_order_id: str, symbol: str
    ) -> bool:
        """Cancel an order on the exchange."""
        if not self._exchange:
            return False

        try:
            await self._exchange.cancel_order(exchange_order_id, symbol)
            log.info(
                "order_cancelled",
                exchange_order_id=exchange_order_id,
                symbol=symbol,
            )
            return True
        except Exception as e:
            log.error("cancel_order_error", error=str(e))
            return False

    async def get_balance(self, currency: str = "USDT") -> float:
        """
        Get available balance for a currency.

        Args:
            currency: Currency code (default USDT).

        Returns:
            Available balance as float.
        """
        if not self._exchange:
            return 0.0

        try:
            balance = await self._exchange.fetch_balance()
            free = balance.get("free", {}).get(currency, 0.0)
            return float(free)
        except Exception as e:
            log.error("balance_fetch_error", error=str(e))
            return 0.0

    async def get_total_balance(self) -> dict[str, float]:
        """Get total balance across all currencies."""
        if not self._exchange:
            return {}

        try:
            balance = await self._exchange.fetch_balance()
            total = balance.get("total", {})
            return {k: float(v) for k, v in total.items() if float(v) > 0}
        except Exception as e:
            log.error("balance_fetch_error", error=str(e))
            return {}

    async def get_ticker(self, symbol: str) -> dict | None:
        """Get current ticker for a symbol."""
        if not self._exchange:
            return None

        try:
            return await self._exchange.fetch_ticker(symbol)
        except Exception as e:
            log.error("ticker_fetch_error", symbol=symbol, error=str(e))
            return None

    async def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        """Get open orders from exchange."""
        if not self._exchange:
            return []

        try:
            orders = await self._exchange.fetch_open_orders(symbol)
            return orders
        except Exception as e:
            log.error("fetch_orders_error", error=str(e))
            return []

    def _parse_fill(self, order: Order, result: dict) -> Fill:
        """Parse ccxt order result into Fill model."""
        filled_amount = float(result.get("filled", 0) or 0)
        avg_price = float(result.get("average", 0) or result.get("price", 0) or 0)

        fee_info = result.get("fee", {}) or {}
        fee_cost = float(fee_info.get("cost", 0) or 0)
        fee_currency = fee_info.get("currency", "USDT") or "USDT"

        return Fill(
            order_id=order.id,
            exchange_order_id=str(result.get("id", "")),
            symbol=order.symbol,
            exchange=self._exchange_id,
            side=order.side,
            price=avg_price if avg_price > 0 else (order.price or 0),
            amount=filled_amount if filled_amount > 0 else order.amount,
            fee=fee_cost,
            fee_currency=fee_currency,
            timestamp=datetime.now(tz=timezone.utc),
            trade_id=str(result.get("id", "")),
        )
