"""
Minerva AI — Smart Router.

Finds the best execution venue across multiple exchanges
by comparing prices and spreads from Redis cache.
"""

from __future__ import annotations

from typing import Any

from minerva.logger import get_logger
from minerva.memory.redis_store import RedisStore

log = get_logger(__name__)


class SmartRouter:
    """
    Multi-exchange smart order router.

    Compares prices and spreads across exchanges from Redis cache
    to select the best execution venue for a given order.
    """

    def __init__(
        self,
        redis: RedisStore,
        exchanges: list[str],
    ) -> None:
        """
        Initialize smart router.

        Args:
            redis: Redis store for cached market data.
            exchanges: List of exchange IDs to route across.
        """
        self._redis = redis
        self._exchanges = exchanges

    async def find_best_venue(
        self,
        symbol: str,
        side: str,
    ) -> str | None:
        """
        Find the best exchange for an order.

        Args:
            symbol: Trading pair.
            side: "buy" or "sell".

        Returns:
            Best exchange ID, or None if no data available.
        """
        best_exchange: str | None = None
        best_price: float | None = None

        for exchange in self._exchanges:
            ob_data = await self._redis.get_orderbook(symbol, exchange)
            if not ob_data:
                continue

            if side == "buy":
                # For buy, we want the lowest ask
                asks = ob_data.get("asks", [])
                if asks:
                    price = asks[0].get("price", 0) if isinstance(asks[0], dict) else asks[0][0]
                    if best_price is None or price < best_price:
                        best_price = price
                        best_exchange = exchange

            elif side == "sell":
                # For sell, we want the highest bid
                bids = ob_data.get("bids", [])
                if bids:
                    price = bids[0].get("price", 0) if isinstance(bids[0], dict) else bids[0][0]
                    if best_price is None or price > best_price:
                        best_price = price
                        best_exchange = exchange

        if best_exchange:
            log.info(
                "best_venue_found",
                symbol=symbol,
                side=side,
                exchange=best_exchange,
                price=best_price,
            )

        return best_exchange

    async def get_spread_analysis(
        self, symbol: str
    ) -> list[dict[str, Any]]:
        """
        Analyze spreads across all exchanges for a symbol.

        Returns:
            List of exchange spread analyses.
        """
        analyses: list[dict[str, Any]] = []

        for exchange in self._exchanges:
            ob_data = await self._redis.get_orderbook(symbol, exchange)
            if not ob_data:
                continue

            bids = ob_data.get("bids", [])
            asks = ob_data.get("asks", [])

            if not bids or not asks:
                continue

            best_bid = bids[0].get("price", 0) if isinstance(bids[0], dict) else bids[0][0]
            best_ask = asks[0].get("price", 0) if isinstance(asks[0], dict) else asks[0][0]

            mid = (best_bid + best_ask) / 2 if (best_bid + best_ask) > 0 else 0
            spread = best_ask - best_bid
            spread_pct = (spread / mid * 100) if mid > 0 else 0

            analyses.append({
                "exchange": exchange,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": spread,
                "spread_pct": round(spread_pct, 6),
                "mid_price": mid,
            })

        # Sort by spread (tightest first)
        analyses.sort(key=lambda x: x["spread_pct"])
        return analyses
