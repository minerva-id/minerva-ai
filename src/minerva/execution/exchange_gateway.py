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
        execution_queue: asyncio.Queue | None = None,
    ) -> None:
        """
        Initialize exchange gateway.

        Args:
            exchange_id: Exchange identifier (binance, bybit, okx).
            credentials: API credentials.
            sandbox: If True, use exchange testnet.
            execution_queue: Queue to push real-time fills.
        """
        self._exchange_id = exchange_id
        self._credentials = credentials
        self._sandbox = sandbox
        self._execution_queue = execution_queue
        self._exchange: Any = None
        self._watch_task: asyncio.Task | None = None
        self._running = False

    async def connect(self) -> None:
        """Initialize exchange connection."""
        import ccxt.pro as ccxt_pro
        exchange_class = getattr(ccxt_pro, self._exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Exchange '{self._exchange_id}' not supported")

        filtered_creds = {k: v for k, v in self._credentials.items() if v}

        self._exchange = exchange_class({
            **filtered_creds,
            "enableRateLimit": True,
            "verify": False,
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

        # Start execution stream
        self._running = True
        self._watch_task = asyncio.create_task(self._watch_execution_stream())

    async def _watch_execution_stream(self) -> None:
        """Background task to watch for real-time trade fills via WebSocket."""
        import ccxt.pro as ccxt_pro
        log.info("execution_stream_started", exchange=self._exchange_id)
        while self._running and self._exchange:
            try:
                # Some exchanges might require specific symbols, but watch_my_trades 
                # generally listens to all account trades if symbol is omitted.
                trades = await self._exchange.watch_my_trades()
                for trade in trades:
                    if self._execution_queue:
                        fill = self._parse_ws_trade(trade)
                        if fill:
                            await self._execution_queue.put(fill)
            except ccxt_pro.NetworkError as e:
                log.warning("ws_network_error", error=str(e))
                await asyncio.sleep(1.0)
            except Exception as e:
                if self._running:
                    log.error("ws_execution_stream_error", error=str(e))
                    await asyncio.sleep(2.0)

    def _parse_ws_trade(self, trade: dict) -> Fill | None:
        """Parse ccxt websocket trade event into Fill."""
        order_id = str(trade.get("order", ""))
        if not order_id:
            # Some exchanges might not include order id in generic trade
            # But ccxt tries to map it
            return None
            
        fee_info = trade.get("fee", {}) or {}
        
        return Fill(
            order_id=order_id, # This is the exchange's order ID. We will map this in OMS.
            exchange_order_id=order_id,
            symbol=trade.get("symbol", "UNKNOWN"),
            exchange=self._exchange_id,
            side=OrderSide(trade.get("side", "buy")),
            price=float(trade.get("price", 0)),
            amount=float(trade.get("amount", 0)),
            fee=float(fee_info.get("cost", 0)),
            fee_currency=fee_info.get("currency", "USDT"),
            timestamp=datetime.now(tz=timezone.utc),
            trade_id=str(trade.get("id", "")),
        )

    async def disconnect(self) -> None:
        """Close exchange connection."""
        self._running = False
        if self._watch_task:
            self._watch_task.cancel()
        if self._exchange:
            await self._exchange.close()
            self._exchange = None
        log.info("exchange_disconnected", exchange=self._exchange_id)

    async def submit_order(self, order: Order) -> str | None:
        """
        Submit an order to the exchange with retry logic.

        Args:
            order: The order to submit.

        Returns:
            Exchange order ID if successful, None on failure.
        """
        import ccxt.pro as ccxt_pro
        if not self._exchange:
            log.error("exchange_not_connected")
            return None

        for attempt in range(self.MAX_RETRIES):
            try:
                params: dict[str, Any] = {"clientOrderId": order.id}

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

                exchange_order_id = str(result.get("id", ""))
                # Track the minerva order ID using clientOrderId so process_fill can map it
                order.exchange_order_id = exchange_order_id
                
                # We ALSO push the initial filled part from REST response if any
                filled = float(result.get("filled", 0) or 0)
                if filled > 0 and self._execution_queue:
                    fill = self._parse_fill(order, result)
                    await self._execution_queue.put(fill)

                log.info(
                    "order_submitted_to_exchange",
                    order_id=order.id,
                    exchange_order_id=exchange_order_id,
                    symbol=order.symbol,
                )

                return exchange_order_id

            except ccxt_pro.NetworkError as e:
                log.warning(
                    "exchange_network_error",
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAY * (2 ** attempt))

            except ccxt_pro.ExchangeError as e:
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
