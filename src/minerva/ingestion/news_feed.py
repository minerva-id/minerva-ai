"""
Minerva AI — News feed from CryptoPanic.

Polls CryptoPanic API for crypto news with sentiment filtering.
30-second polling interval to stay within API rate limits.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiohttp

from minerva.logger import get_logger

log = get_logger(__name__)


class NewsFeed:
    """
    Crypto news feed from CryptoPanic API.

    Polls for latest news and assigns basic sentiment scores
    based on CryptoPanic's built-in sentiment classification.
    """

    BASE_URL = "https://cryptopanic.com/api/v1/posts/"
    POLL_INTERVAL = 30  # seconds

    def __init__(
        self,
        api_key: str,
        data_queue: asyncio.Queue,
        currencies: list[str] | None = None,
    ) -> None:
        """
        Initialize news feed.

        Args:
            api_key: CryptoPanic API key.
            data_queue: Queue to publish news events.
            currencies: Filter by currencies (e.g., ["BTC", "ETH"]).
        """
        self._api_key = api_key
        self._queue = data_queue
        self._currencies = currencies or ["BTC", "ETH"]
        self._running = False
        self._task: asyncio.Task | None = None
        self._seen_ids: set[int] = set()

    async def start(self) -> None:
        """Start news polling."""
        if not self._api_key:
            log.info("news_feed_disabled", reason="no API key configured")
            return

        self._running = True
        self._task = asyncio.create_task(
            self._poll_loop(),
            name="news_poller",
        )
        log.info("news_feed_started", currencies=self._currencies)

    async def stop(self) -> None:
        """Stop news polling."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("news_feed_stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._fetch_news()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("news_poll_error", error=str(e))

            await asyncio.sleep(self.POLL_INTERVAL)

    async def _fetch_news(self) -> None:
        """Fetch latest news from CryptoPanic."""
        params: dict[str, Any] = {
            "auth_token": self._api_key,
            "currencies": ",".join(self._currencies),
            "filter": "important",
            "public": "true",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                self.BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    log.warning("news_api_error", status=resp.status)
                    return

                data = await resp.json()
                results = data.get("results", [])

                for item in results:
                    item_id = item.get("id")
                    if item_id in self._seen_ids:
                        continue

                    self._seen_ids.add(item_id)

                    # Keep seen set bounded
                    if len(self._seen_ids) > 5000:
                        # Remove oldest entries (approximate)
                        excess = len(self._seen_ids) - 4000
                        self._seen_ids = set(list(self._seen_ids)[excess:])

                    sentiment = self._extract_sentiment(item)

                    event = {
                        "type": "news",
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "source": item.get("source", {}).get("title", ""),
                        "currencies": [
                            c.get("code", "") for c in item.get("currencies", [])
                        ],
                        "sentiment": sentiment,
                        "published_at": item.get("published_at", ""),
                        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                    }
                    await self._queue.put(("news", event))

                if results:
                    log.info("news_fetched", count=len(results))

    @staticmethod
    def _extract_sentiment(item: dict) -> float:
        """
        Extract sentiment score from CryptoPanic item.

        Returns a score from -1.0 (bearish) to 1.0 (bullish).
        """
        votes = item.get("votes", {})
        positive = votes.get("positive", 0)
        negative = votes.get("negative", 0)
        important = votes.get("important", 0)

        total_votes = positive + negative
        if total_votes == 0:
            # Use kind field as fallback
            kind = item.get("kind", "news")
            if kind == "bullish":
                return 0.3
            elif kind == "bearish":
                return -0.3
            return 0.0

        # Weighted sentiment
        raw_score = (positive - negative) / total_votes
        # Boost if marked important
        if important > 0:
            raw_score *= 1.2

        return max(-1.0, min(1.0, raw_score))
