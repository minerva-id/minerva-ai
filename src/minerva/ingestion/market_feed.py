"""
Minerva AI — Market data feed via ccxt WebSocket.

Real-time market data ingestion using ccxtpro (ccxt with WebSocket support).
Subscribes to OHLCV, order book, and trades for configured exchanges.
Auto-reconnects on disconnect.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import ccxt.pro as ccxtpro

from minerva.logger import get_logger
from minerva.models.market import OHLCV, OrderBookLevel, OrderBookSnapshot, TickData, TimeFrame

log = get_logger(__name__)


class MarketFeed:
    """
    Real-time market data feed using ccxtpro WebSockets.

    Subscribes to exchange WebSocket streams and publishes
    normalized data to asyncio queues for downstream processing.
    """

    # Reconnect delay with backoff
    INITIAL_RECONNECT_DELAY = 1.0
    MAX_RECONNECT_DELAY = 60.0

    def __init__(
        self,
        exchange_id: str,
        credentials: dict[str, str],
        symbols: list[str],
        data_queue: asyncio.Queue,
        timeframes: list[str] | None = None,
    ) -> None:
        """
        Initialize market feed.

        Args:
            exchange_id: Exchange identifier (binance, bybit, okx).
            credentials: API credentials dict with apiKey, secret, etc.
            symbols: List of trading pair symbols (e.g., ["BTC/USDT"]).
            data_queue: Async queue to publish normalized data.
            timeframes: OHLCV timeframes to subscribe (default: ["1m"]).
        """
        self._exchange_id = exchange_id
        self._credentials = credentials
        self._symbols = symbols
        self._queue = data_queue
        self._timeframes = timeframes or ["1m"]
        self._exchange: Any = None
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start all market data streams."""
        self._running = True
        exchange_class = getattr(ccxtpro, self._exchange_id, None)
        if exchange_class is None:
            log.error("exchange_not_found", exchange=self._exchange_id)
            return

        # Filter out empty credential values
        filtered_creds = {k: v for k, v in self._credentials.items() if v}

        self._exchange = exchange_class({
            **filtered_creds,
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
            },
        })

        log.info(
            "market_feed_starting",
            exchange=self._exchange_id,
            symbols=self._symbols,
        )

        # Start OHLCV streams
        for symbol in self._symbols:
            for tf in self._timeframes:
                task = asyncio.create_task(
                    self._watch_ohlcv(symbol, tf),
                    name=f"ohlcv_{self._exchange_id}_{symbol}_{tf}",
                )
                self._tasks.append(task)

        # Start order book streams
        for symbol in self._symbols:
            task = asyncio.create_task(
                self._watch_orderbook(symbol),
                name=f"orderbook_{self._exchange_id}_{symbol}",
            )
            self._tasks.append(task)

        # Start trade streams
        for symbol in self._symbols:
            task = asyncio.create_task(
                self._watch_trades(symbol),
                name=f"trades_{self._exchange_id}_{symbol}",
            )
            self._tasks.append(task)

    async def stop(self) -> None:
        """Stop all market data streams."""
        self._running = False
        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        if self._exchange:
            await self._exchange.close()
            self._exchange = None

        log.info("market_feed_stopped", exchange=self._exchange_id)

    async def _watch_ohlcv(self, symbol: str, timeframe: str) -> None:
        """Watch OHLCV candle stream with auto-reconnect."""
        delay = self.INITIAL_RECONNECT_DELAY

        while self._running:
            try:
                candles = await self._exchange.watch_ohlcv(symbol, timeframe)
                if candles:
                    latest = candles[-1]
                    ohlcv = OHLCV(
                        symbol=symbol,
                        exchange=self._exchange_id,
                        timeframe=TimeFrame(timeframe),
                        timestamp=datetime.fromtimestamp(
                            latest[0] / 1000, tz=timezone.utc
                        ),
                        open=float(latest[1]),
                        high=float(latest[2]),
                        low=float(latest[3]),
                        close=float(latest[4]),
                        volume=float(latest[5]),
                    )
                    await self._queue.put(("ohlcv", ohlcv))
                    delay = self.INITIAL_RECONNECT_DELAY  # Reset on success

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning(
                    "ohlcv_stream_error",
                    exchange=self._exchange_id,
                    symbol=symbol,
                    error=str(e),
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.MAX_RECONNECT_DELAY)

    async def _watch_orderbook(self, symbol: str) -> None:
        """Watch order book stream with auto-reconnect."""
        delay = self.INITIAL_RECONNECT_DELAY

        while self._running:
            try:
                ob = await self._exchange.watch_order_book(symbol, limit=20)

                snapshot = OrderBookSnapshot(
                    symbol=symbol,
                    exchange=self._exchange_id,
                    timestamp=datetime.now(tz=timezone.utc),
                    bids=[
                        OrderBookLevel(price=float(b[0]), amount=float(b[1]))
                        for b in ob.get("bids", [])[:20]
                    ],
                    asks=[
                        OrderBookLevel(price=float(a[0]), amount=float(a[1]))
                        for a in ob.get("asks", [])[:20]
                    ],
                )
                await self._queue.put(("orderbook", snapshot))
                delay = self.INITIAL_RECONNECT_DELAY

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning(
                    "orderbook_stream_error",
                    exchange=self._exchange_id,
                    symbol=symbol,
                    error=str(e),
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.MAX_RECONNECT_DELAY)

    async def _watch_trades(self, symbol: str) -> None:
        """Watch trade stream with auto-reconnect."""
        delay = self.INITIAL_RECONNECT_DELAY

        while self._running:
            try:
                trades = await self._exchange.watch_trades(symbol)

                for trade in trades:
                    tick = TickData(
                        symbol=symbol,
                        exchange=self._exchange_id,
                        timestamp=datetime.fromtimestamp(
                            trade["timestamp"] / 1000, tz=timezone.utc
                        ),
                        price=float(trade["price"]),
                        amount=float(trade["amount"]),
                        side=trade["side"],
                        trade_id=str(trade.get("id", "")),
                    )
                    await self._queue.put(("tick", tick))
                delay = self.INITIAL_RECONNECT_DELAY

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning(
                    "trades_stream_error",
                    exchange=self._exchange_id,
                    symbol=symbol,
                    error=str(e),
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.MAX_RECONNECT_DELAY)
