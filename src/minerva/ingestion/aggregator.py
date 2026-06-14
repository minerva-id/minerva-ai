"""
Minerva AI — Data aggregator.

Consumes data from all feed queues, normalizes to Pydantic models,
and updates Redis cache. Serves as the single data access point for
the AI brain.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from minerva.logger import get_logger
from minerva.memory.redis_store import RedisStore
from minerva.models.market import OHLCV, MarketSummary, OrderBookSnapshot

log = get_logger(__name__)


class DataAggregator:
    """
    Central data aggregator for all market data feeds.

    Consumes from asyncio queues, normalizes data, updates Redis cache,
    and maintains in-memory state for fast access.
    """

    def __init__(
        self,
        data_queue: asyncio.Queue,
        redis: RedisStore,
    ) -> None:
        """
        Initialize data aggregator.

        Args:
            data_queue: Shared queue that all feeds write to.
            redis: Redis store for caching.
        """
        self._queue = data_queue
        self._redis = redis
        self._running = False
        self._task: asyncio.Task | None = None

        # In-memory state for fast path access
        self._latest_ohlcv: dict[str, OHLCV] = {}
        self._latest_orderbooks: dict[str, OrderBookSnapshot] = {}
        self._ohlcv_history: dict[str, list[dict]] = defaultdict(list)
        self._sentiment_scores: dict[str, float] = {}
        self._onchain_events: list[dict] = []
        self._news_items: list[dict] = []

        # Callbacks for real-time event notification
        self._ohlcv_callbacks: list[Any] = []
        self._event_callbacks: list[Any] = []

    async def start(self) -> None:
        """Start consuming from data queue."""
        self._running = True
        self._task = asyncio.create_task(
            self._consume_loop(),
            name="data_aggregator",
        )
        log.info("data_aggregator_started")

    async def stop(self) -> None:
        """Stop aggregator."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("data_aggregator_stopped")

    def on_ohlcv(self, callback: Any) -> None:
        """Register callback for new OHLCV data."""
        self._ohlcv_callbacks.append(callback)

    def on_event(self, callback: Any) -> None:
        """Register callback for any event."""
        self._event_callbacks.append(callback)

    async def _consume_loop(self) -> None:
        """Main consume loop processing queue items."""
        while self._running:
            try:
                event_type, data = await asyncio.wait_for(
                    self._queue.get(), timeout=5.0
                )
                await self._process_event(event_type, data)
                self._queue.task_done()

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("aggregator_error", error=str(e))

    async def _process_event(self, event_type: str, data: Any) -> None:
        """Route and process a data event."""
        if event_type == "ohlcv":
            await self._handle_ohlcv(data)
        elif event_type == "orderbook":
            await self._handle_orderbook(data)
        elif event_type == "tick":
            await self._handle_tick(data)
        elif event_type == "onchain":
            await self._handle_onchain(data)
        elif event_type == "news":
            await self._handle_news(data)
        elif event_type == "social":
            await self._handle_social(data)

        # Notify event callbacks
        for cb in self._event_callbacks:
            try:
                await cb(event_type, data)
            except Exception as e:
                log.debug("event_callback_error", error=str(e))

    async def _handle_ohlcv(self, ohlcv: OHLCV) -> None:
        """Process OHLCV candle data."""
        key = f"{ohlcv.exchange}:{ohlcv.symbol}:{ohlcv.timeframe.value}"
        self._latest_ohlcv[key] = ohlcv

        # Store in history (keep last 500 candles per key)
        candle_dict = ohlcv.model_dump(mode="json")
        history = self._ohlcv_history[key]
        history.append(candle_dict)
        if len(history) > 500:
            self._ohlcv_history[key] = history[-500:]

        # Update Redis
        await self._redis.set_ohlcv(
            ohlcv.symbol, ohlcv.exchange, ohlcv.timeframe.value, candle_dict
        )

        # Update market summary
        await self._update_market_summary(ohlcv)

        # Notify OHLCV callbacks
        for cb in self._ohlcv_callbacks:
            try:
                await cb(ohlcv)
            except Exception as e:
                log.debug("ohlcv_callback_error", error=str(e))

    async def _handle_orderbook(self, ob: OrderBookSnapshot) -> None:
        """Process order book snapshot."""
        key = f"{ob.exchange}:{ob.symbol}"
        self._latest_orderbooks[key] = ob

        await self._redis.set_orderbook(
            ob.symbol, ob.exchange, ob.model_dump(mode="json")
        )

    async def _handle_tick(self, tick: Any) -> None:
        """Process trade tick — used for last price updates."""
        # Ticks are high-frequency; only update Redis market summary
        pass

    async def _handle_onchain(self, event: dict) -> None:
        """Process on-chain event."""
        self._onchain_events.append(event)
        # Keep last 100 events
        if len(self._onchain_events) > 100:
            self._onchain_events = self._onchain_events[-100:]

    async def _handle_news(self, news: dict) -> None:
        """Process news event."""
        self._news_items.append(news)
        # Keep last 50 items
        if len(self._news_items) > 50:
            self._news_items = self._news_items[-50:]

        # Update sentiment for related currencies
        for currency in news.get("currencies", []):
            symbol = f"{currency}/USDT"
            current = self._sentiment_scores.get(symbol, 0.0)
            news_sentiment = news.get("sentiment", 0.0)
            # Exponential moving average
            self._sentiment_scores[symbol] = current * 0.8 + news_sentiment * 0.2

    async def _handle_social(self, social: dict) -> None:
        """Process social sentiment event."""
        score = social.get("sentiment_score", 0.0)
        # Apply to all tracked symbols as general market sentiment
        for symbol in list(self._sentiment_scores.keys()):
            current = self._sentiment_scores.get(symbol, 0.0)
            self._sentiment_scores[symbol] = current * 0.7 + score * 0.3

    async def _update_market_summary(self, ohlcv: OHLCV) -> None:
        """Update aggregated market summary for a symbol."""
        key = f"{ohlcv.exchange}:{ohlcv.symbol}:{ohlcv.timeframe.value}"
        history = self._ohlcv_history.get(key, [])
        ob_key = f"{ohlcv.exchange}:{ohlcv.symbol}"
        ob = self._latest_orderbooks.get(ob_key)

        summary = MarketSummary(
            symbol=ohlcv.symbol,
            exchange=ohlcv.exchange,
            timestamp=datetime.now(tz=timezone.utc),
            last_price=ohlcv.close,
            volume_24h=ohlcv.volume,
            high_24h=ohlcv.high,
            low_24h=ohlcv.low,
            bid=ob.best_bid if ob and ob.best_bid else ohlcv.close,
            ask=ob.best_ask if ob and ob.best_ask else ohlcv.close,
            order_book_imbalance=ob.imbalance if ob else 0.0,
        )

        # Calculate 24h price change if we have enough history
        if len(history) >= 2:
            first_close = history[0].get("close", ohlcv.close)
            if first_close > 0:
                summary.price_change_24h_pct = (
                    (ohlcv.close - first_close) / first_close
                ) * 100

        # Calculate spread
        if summary.bid > 0 and summary.ask > 0:
            mid = (summary.bid + summary.ask) / 2
            summary.spread_pct = ((summary.ask - summary.bid) / mid) * 100

        await self._redis.set_market_summary(
            ohlcv.symbol, summary.model_dump(mode="json")
        )

    # --- Public data access methods ---

    def get_latest_ohlcv(
        self, symbol: str, exchange: str, timeframe: str = "1m"
    ) -> OHLCV | None:
        """Get latest OHLCV candle from memory."""
        key = f"{exchange}:{symbol}:{timeframe}"
        return self._latest_ohlcv.get(key)

    def get_ohlcv_history(
        self, symbol: str, exchange: str, timeframe: str = "1m", limit: int = 100
    ) -> list[dict]:
        """Get OHLCV history from memory."""
        key = f"{exchange}:{symbol}:{timeframe}"
        history = self._ohlcv_history.get(key, [])
        return history[-limit:]

    def get_orderbook(
        self, symbol: str, exchange: str
    ) -> OrderBookSnapshot | None:
        """Get latest order book from memory."""
        key = f"{exchange}:{symbol}"
        return self._latest_orderbooks.get(key)

    def get_sentiment(self, symbol: str) -> float:
        """Get sentiment score for a symbol (-1 to 1)."""
        return self._sentiment_scores.get(symbol, 0.0)

    def get_recent_news(self, limit: int = 10) -> list[dict]:
        """Get recent news items."""
        return self._news_items[-limit:]

    def get_onchain_events(self, limit: int = 10) -> list[dict]:
        """Get recent on-chain events."""
        return self._onchain_events[-limit:]
