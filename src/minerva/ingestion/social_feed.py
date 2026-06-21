"""
Minerva AI — Social media sentiment feed.

Monitors GMGN API for crypto sentiment signals, bypassing Twitter API limits.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiohttp

from minerva.logger import get_logger

log = get_logger(__name__)


class SocialFeed:
    """
    Social media sentiment aggregator.

    Monitors GMGN's internal API for real-time crypto sentiment.
    Replaces official Twitter API polling.
    """

    POLL_INTERVAL = 30  # seconds

    # Keywords for crypto sentiment
    CRYPTO_KEYWORDS = [
        "bitcoin", "BTC", "ethereum", "ETH", "crypto",
        "bullish", "bearish", "pump", "dump", "moon",
        "whale", "liquidation", "breakout", "support", "resistance",
        "solana", "SOL",
    ]

    def __init__(
        self,
        gmgn_url: str,
        data_queue: asyncio.Queue,
        keywords: list[str] | None = None,
    ) -> None:
        """
        Initialize social feed.

        Args:
            gmgn_url: GMGN API endpoint URL.
            data_queue: Queue to publish sentiment events.
            keywords: Custom keywords to track sentiment for.
        """
        self._gmgn_url = gmgn_url
        self._queue = data_queue
        self._keywords = keywords or self.CRYPTO_KEYWORDS
        self._running = False
        self._task: asyncio.Task | None = None
        self._seen_ids: set[str] = set()
        self._seen_ids_list: list[str] = []

    async def start(self) -> None:
        """Start social monitoring."""
        if not self._gmgn_url:
            log.info("social_feed_disabled", reason="no gmgn url configured")
            return

        self._running = True
        self._task = asyncio.create_task(
            self._poll_loop(),
            name="social_monitor",
        )
        log.info("social_feed_started", provider="gmgn")

    async def stop(self) -> None:
        """Stop social monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("social_feed_stopped")

    async def _poll_loop(self) -> None:
        """Polling loop for GMGN API."""
        async with aiohttp.ClientSession() as session:
            while self._running:
                try:
                    await self._fetch_tweets(session)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.warning("social_poll_error", error=str(e))

                await asyncio.sleep(self.POLL_INTERVAL)

    async def _fetch_tweets(self, session: aiohttp.ClientSession) -> None:
        """Fetch recent tweets from GMGN API."""
        headers = {
            "accept": "application/json, text/plain, */*",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        }

        async with session.get(
            self._gmgn_url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 429:
                log.warning("gmgn_rate_limited")
                await asyncio.sleep(60)
                return

            if resp.status != 200:
                log.warning("gmgn_api_error", status=resp.status)
                return

            data = await resp.json()
            
            # Extract tweets list robustly based on typical GMGN JSON structures
            tweets = []
            if isinstance(data, dict):
                inner_data = data.get("data", data)
                if isinstance(inner_data, dict):
                    # It might be data.tweets or data.messages
                    tweets = inner_data.get("tweets") or inner_data.get("messages") or inner_data.get("items", [])
                elif isinstance(inner_data, list):
                    tweets = inner_data
            elif isinstance(data, list):
                tweets = data

            if not tweets:
                return

            new_tweets = []
            for tweet in tweets:
                # Extract ID safely
                tweet_id = str(tweet.get("id", "") or tweet.get("tweet_id", "") or tweet.get("id_str", ""))
                if not tweet_id or tweet_id in self._seen_ids:
                    continue
                    
                self._seen_ids.add(tweet_id)
                self._seen_ids_list.append(tweet_id)
                
                if len(self._seen_ids_list) > 2000:
                    oldest = self._seen_ids_list.pop(0)
                    self._seen_ids.discard(oldest)
                    
                new_tweets.append(tweet)

            if not new_tweets:
                return

            sentiment = self._aggregate_sentiment(new_tweets)

            event = {
                "type": "social_sentiment",
                "source": "gmgn_twitter",
                "tweet_count": len(new_tweets),
                "sentiment_score": sentiment["score"],
                "bullish_count": sentiment["bullish"],
                "bearish_count": sentiment["bearish"],
                "neutral_count": sentiment["neutral"],
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            }
            await self._queue.put(("social", event))
            log.info(
                "social_sentiment_updated",
                score=round(sentiment["score"], 3),
                tweets=len(new_tweets),
            )

    def _aggregate_sentiment(self, tweets: list[dict]) -> dict:
        """
        Simple keyword-based sentiment aggregation for crypto.
        """
        bullish_words = {"bullish", "moon", "pump", "breakout", "long", "buy", "ath", "rally", "up"}
        bearish_words = {"bearish", "dump", "crash", "short", "sell", "liquidation", "rekt", "down"}

        bullish_count = 0
        bearish_count = 0
        neutral_count = 0
        weighted_score = 0.0
        total_weight = 0.0

        for tweet in tweets:
            text = str(tweet.get("text", "") or tweet.get("content", "")).lower()
            metrics = tweet.get("public_metrics", {})
            if not metrics and "metrics" in tweet:
                metrics = tweet["metrics"]
            elif not metrics and "stats" in tweet:
                metrics = tweet["stats"]

            # Engagement weight (fallback to 1.0 if missing)
            likes = int(metrics.get("like_count", 0) or metrics.get("likes", 0))
            retweets = int(metrics.get("retweet_count", 0) or metrics.get("retweets", 0))
            weight = 1.0 + (likes * 0.1) + (retweets * 0.5)

            # Simple sentiment
            bull_hits = sum(1 for w in bullish_words if w in text.split())
            bear_hits = sum(1 for w in bearish_words if w in text.split())

            if bull_hits > bear_hits:
                bullish_count += 1
                weighted_score += weight
            elif bear_hits > bull_hits:
                bearish_count += 1
                weighted_score -= weight
            else:
                neutral_count += 1

            total_weight += weight

        score = weighted_score / total_weight if total_weight > 0 else 0.0
        score = max(-1.0, min(1.0, score))

        return {
            "score": score,
            "bullish": bullish_count,
            "bearish": bearish_count,
            "neutral": neutral_count,
        }
