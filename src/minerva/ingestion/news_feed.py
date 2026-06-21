"""
Minerva AI — News feed from RSS2JSON (Cointelegraph).

Polls RSS to JSON API for crypto news.
30-second polling interval to fetch latest articles.
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
    Crypto news feed via RSS2JSON (e.g. Cointelegraph).

    Polls for latest news from an RSS feed converted to JSON.
    """

    POLL_INTERVAL = 30  # seconds

    def __init__(
        self,
        rss_url: str,
        data_queue: asyncio.Queue,
        currencies: list[str] | None = None,
    ) -> None:
        """
        Initialize news feed.

        Args:
            rss_url: URL to the RSS2JSON API endpoint.
            data_queue: Queue to publish news events.
            currencies: Filter by currencies (e.g., ["BTC", "ETH"]).
        """
        self._rss_url = rss_url
        self._queue = data_queue
        self._currencies = currencies or ["BTC", "ETH"]
        self._running = False
        self._task: asyncio.Task | None = None
        self._seen_ids: set[str] = set()

    async def start(self) -> None:
        """Start news polling."""
        if not self._rss_url:
            log.info("news_feed_disabled", reason="no RSS URL configured")
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
        """Fetch latest news from RSS2JSON."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                self._rss_url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    log.warning("news_api_error", status=resp.status)
                    return

                data = await resp.json()
                items = data.get("items", [])
                
                new_items_count = 0

                for item in reversed(items):  # Oldest first
                    # RSS2JSON uses 'guid' or 'link' as unique identifier
                    item_id = item.get("guid") or item.get("link")
                    if not item_id or item_id in self._seen_ids:
                        continue

                    self._seen_ids.add(item_id)

                    # Keep seen set bounded
                    if len(self._seen_ids) > 5000:
                        # Convert to list to remove oldest, but since set is unordered,
                        # just clear partially. A simple approach is clear completely or use a list.
                        # For simplicity, we just clear and keep the latest item to avoid huge leaks.
                        self._seen_ids.clear()
                        self._seen_ids.add(item_id)

                    # Check if article mentions any of our tracked currencies
                    title = item.get("title", "")
                    content = item.get("content", "") + " " + item.get("description", "")
                    categories = item.get("categories", [])
                    
                    search_text = (title + " " + content + " " + " ".join(categories)).upper()
                    
                    matched_currencies = []
                    for currency in self._currencies:
                        if currency.upper() in search_text:
                            matched_currencies.append(currency)
                            
                    # If we have specific currencies, and it matches none, we skip it
                    if self._currencies and not matched_currencies:
                        # Cointelegraph has generic news, we might still want it, 
                        # but keeping old behavior of filtering by currencies.
                        # For broader news, we can assign it to "GLOBAL" or just pass all.
                        # Let's pass if it mentions Bitcoin/Ethereum or any tracked pair.
                        continue

                    # Basic sentiment based on title (naive fallback since RSS lacks it)
                    sentiment = self._extract_sentiment(title)

                    event = {
                        "type": "news",
                        "title": title,
                        "url": item.get("link", ""),
                        "source": "Cointelegraph",  # From feed
                        "currencies": matched_currencies,
                        "sentiment": sentiment,
                        "published_at": item.get("pubDate", ""),
                        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                    }
                    await self._queue.put(("news", event))
                    new_items_count += 1

                if new_items_count > 0:
                    log.info("news_fetched", count=new_items_count)

    @staticmethod
    def _extract_sentiment(text: str) -> float:
        """
        Extract naive sentiment score from text title.
        Returns a score from -1.0 (bearish) to 1.0 (bullish).
        """
        text = text.lower()
        bullish_words = {"surge", "soar", "jump", "bull", "high", "rally", "gain", "breakout", "up"}
        bearish_words = {"plunge", "crash", "drop", "bear", "low", "dump", "fall", "collapse", "down"}
        
        words = set(text.replace(".", "").replace(",", "").split())
        
        bull_count = len(words.intersection(bullish_words))
        bear_count = len(words.intersection(bearish_words))
        
        if bull_count > bear_count:
            return 0.3
        elif bear_count > bull_count:
            return -0.3
        return 0.0
