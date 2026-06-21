"""
Minerva AI — Redis hot state cache.

Manages volatile state: positions, active orders, latest OHLCV, signals.
All data has TTL. Uses async redis client with connection pooling.
"""

from __future__ import annotations

import asyncio
from typing import Any

import orjson
import redis.asyncio as aioredis

from minerva.logger import get_logger

log = get_logger(__name__)


class RedisStore:
    """
    Async Redis client for hot state caching.

    Stores volatile trading data with automatic TTL expiration.
    Connection is pooled and shared across the application.
    """

    # Key prefixes for namespace isolation
    PREFIX_OHLCV = "ohlcv"
    PREFIX_ORDERBOOK = "orderbook"
    PREFIX_POSITION = "position"
    PREFIX_ORDER = "order"
    PREFIX_SIGNAL = "signal"
    PREFIX_MARKET = "market"
    PREFIX_META = "meta"
    PREFIX_PRINCIPLE = "principle"

    def __init__(self, redis_url: str, default_ttl: int = 300) -> None:
        """
        Initialize Redis store.

        Args:
            redis_url: Redis connection URL (redis:// or rediss:// for TLS).
            default_ttl: Default TTL in seconds (5 minutes).
        """
        self._url = redis_url
        self._default_ttl = default_ttl
        self._client: aioredis.Redis | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Establish connection to Redis."""
        async with self._lock:
            if self._client is not None:
                return
            self._client = aioredis.from_url(
                self._url,
                decode_responses=False,
                max_connections=20,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
            # Verify connection
            await self._client.ping()
            log.info("redis_connected", url=self._url.split("@")[-1])

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None
            log.info("redis_disconnected")

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._client

    def _key(self, prefix: str, *parts: str) -> str:
        """Build a namespaced Redis key."""
        return f"minerva:{prefix}:{':'.join(parts)}"

    # --- Generic operations ---

    async def set_json(
        self, prefix: str, key: str, data: Any, ttl: int | None = None
    ) -> None:
        """Store JSON-serializable data with TTL."""
        full_key = self._key(prefix, key)
        encoded = orjson.dumps(data)
        await self.client.set(full_key, encoded, ex=ttl or self._default_ttl)

    async def get_json(self, prefix: str, key: str) -> Any | None:
        """Retrieve JSON data by key."""
        full_key = self._key(prefix, key)
        raw = await self.client.get(full_key)
        if raw is None:
            return None
        return orjson.loads(raw)

    async def delete(self, prefix: str, key: str) -> None:
        """Delete a key."""
        full_key = self._key(prefix, key)
        await self.client.delete(full_key)

    async def get_keys(self, prefix: str, pattern: str = "*") -> list[str]:
        """Get all keys matching a pattern under a prefix."""
        full_pattern = self._key(prefix, pattern)
        keys: list[str] = []
        async for key in self.client.scan_iter(match=full_pattern, count=100):
            if isinstance(key, bytes):
                keys.append(key.decode())
            else:
                keys.append(key)
        return keys

    # --- OHLCV ---

    async def set_ohlcv(
        self, symbol: str, exchange: str, timeframe: str, data: dict
    ) -> None:
        """Cache latest OHLCV candle."""
        key = f"{exchange}:{symbol}:{timeframe}"
        await self.set_json(self.PREFIX_OHLCV, key, data, ttl=120)

    async def get_ohlcv(
        self, symbol: str, exchange: str, timeframe: str
    ) -> dict | None:
        """Get cached OHLCV candle."""
        key = f"{exchange}:{symbol}:{timeframe}"
        return await self.get_json(self.PREFIX_OHLCV, key)

    # --- Order Book ---

    async def set_orderbook(
        self, symbol: str, exchange: str, data: dict
    ) -> None:
        """Cache order book snapshot."""
        key = f"{exchange}:{symbol}"
        await self.set_json(self.PREFIX_ORDERBOOK, key, data, ttl=10)

    async def get_orderbook(
        self, symbol: str, exchange: str
    ) -> dict | None:
        """Get cached order book."""
        key = f"{exchange}:{symbol}"
        return await self.get_json(self.PREFIX_ORDERBOOK, key)

    # --- Positions ---

    async def set_position(self, symbol: str, data: dict) -> None:
        """Store position data (no TTL — persistent until closed)."""
        await self.set_json(self.PREFIX_POSITION, symbol, data, ttl=86400)

    async def get_position(self, symbol: str) -> dict | None:
        """Get position data."""
        return await self.get_json(self.PREFIX_POSITION, symbol)

    async def delete_position(self, symbol: str) -> None:
        """Remove position data."""
        await self.delete(self.PREFIX_POSITION, symbol)

    async def get_all_positions(self) -> dict[str, dict]:
        """Get all cached positions."""
        keys = await self.get_keys(self.PREFIX_POSITION)
        positions: dict[str, dict] = {}
        for key in keys:
            # Extract symbol from key: minerva:position:BTC/USDT
            parts = key.split(":")
            if len(parts) >= 3:
                symbol = ":".join(parts[2:])
                data = await self.get_json(self.PREFIX_POSITION, symbol)
                if data:
                    positions[symbol] = data
        return positions

    # --- Orders ---

    async def set_order(self, order_id: str, data: dict) -> None:
        """Store active order."""
        await self.set_json(self.PREFIX_ORDER, order_id, data, ttl=86400)

    async def get_order(self, order_id: str) -> dict | None:
        """Get order data."""
        return await self.get_json(self.PREFIX_ORDER, order_id)

    async def delete_order(self, order_id: str) -> None:
        """Remove order data."""
        await self.delete(self.PREFIX_ORDER, order_id)

    # --- Signals ---

    async def set_signal(self, symbol: str, data: dict) -> None:
        """Cache latest signal for a symbol."""
        await self.set_json(self.PREFIX_SIGNAL, symbol, data, ttl=300)

    async def get_signal(self, symbol: str) -> dict | None:
        """Get cached signal."""
        return await self.get_json(self.PREFIX_SIGNAL, symbol)

    # --- Market Summary ---

    async def set_market_summary(self, symbol: str, data: dict) -> None:
        """Cache market summary."""
        await self.set_json(self.PREFIX_MARKET, symbol, data, ttl=60)

    async def get_market_summary(self, symbol: str) -> dict | None:
        """Get cached market summary."""
        return await self.get_json(self.PREFIX_MARKET, symbol)

    # --- Agent Metadata ---

    async def set_meta(self, key: str, data: Any) -> None:
        """Store agent metadata (last loop time, health, etc.)."""
        await self.set_json(self.PREFIX_META, key, data, ttl=600)

    async def get_meta(self, key: str) -> Any | None:
        """Get agent metadata."""
        return await self.get_json(self.PREFIX_META, key)

    # --- Trading Principles ---

    async def add_trading_principle(self, principle: str) -> None:
        """Add a new user trading principle."""
        principles = await self.get_trading_principles()
        if principle not in principles:
            principles.append(principle)
            # Store with no TTL (persistent)
            await self.set_json(self.PREFIX_PRINCIPLE, "all", principles, ttl=86400 * 365)

    async def get_trading_principles(self) -> list[str]:
        """Get all stored user trading principles."""
        data = await self.get_json(self.PREFIX_PRINCIPLE, "all")
        return data if isinstance(data, list) else []

    async def delete_trading_principle(self, index: int) -> bool:
        """Delete a trading principle by its 0-based index."""
        principles = await self.get_trading_principles()
        if 0 <= index < len(principles):
            principles.pop(index)
            await self.set_json(self.PREFIX_PRINCIPLE, "all", principles, ttl=86400 * 365)
            return True
        return False

    # --- Health ---

    async def health_check(self) -> bool:
        """Check Redis connectivity."""
        try:
            result = await self.client.ping()
            return bool(result)
        except Exception:
            return False
