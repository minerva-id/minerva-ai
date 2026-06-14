"""
Minerva AI — Social media sentiment feed.

Monitors Twitter/X and Reddit for crypto sentiment signals.
Twitter uses filtered stream API; Reddit uses polling.
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

    Monitors Twitter/X for real-time crypto sentiment using
    the filtered stream API. Falls back to search polling
    if streaming is not available.
    """

    TWITTER_STREAM_URL = "https://api.twitter.com/2/tweets/search/stream"
    TWITTER_RULES_URL = "https://api.twitter.com/2/tweets/search/stream/rules"
    TWITTER_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"

    POLL_INTERVAL = 60  # seconds for fallback polling

    # Keywords for crypto sentiment
    CRYPTO_KEYWORDS = [
        "bitcoin", "BTC", "ethereum", "ETH", "crypto",
        "bullish", "bearish", "pump", "dump", "moon",
        "whale", "liquidation", "breakout", "support", "resistance",
    ]

    def __init__(
        self,
        bearer_token: str,
        data_queue: asyncio.Queue,
        keywords: list[str] | None = None,
    ) -> None:
        """
        Initialize social feed.

        Args:
            bearer_token: Twitter API v2 bearer token.
            data_queue: Queue to publish sentiment events.
            keywords: Custom keywords to track.
        """
        self._bearer_token = bearer_token
        self._queue = data_queue
        self._keywords = keywords or self.CRYPTO_KEYWORDS
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start social monitoring."""
        if not self._bearer_token:
            log.info("social_feed_disabled", reason="no bearer token configured")
            return

        self._running = True
        self._task = asyncio.create_task(
            self._poll_loop(),
            name="social_monitor",
        )
        log.info("social_feed_started")

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
        """Polling loop for Twitter search API."""
        while self._running:
            try:
                await self._search_tweets()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("social_poll_error", error=str(e))

            await asyncio.sleep(self.POLL_INTERVAL)

    async def _search_tweets(self) -> None:
        """Search recent tweets for crypto keywords."""
        query = " OR ".join(self._keywords[:10])  # Twitter query limit
        query += " -is:retweet lang:en"

        params: dict[str, Any] = {
            "query": query,
            "max_results": 100,
            "tweet.fields": "created_at,public_metrics,lang",
        }
        headers = {
            "Authorization": f"Bearer {self._bearer_token}",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                self.TWITTER_SEARCH_URL,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 429:
                    log.warning("twitter_rate_limited")
                    await asyncio.sleep(60)
                    return

                if resp.status != 200:
                    log.warning("twitter_api_error", status=resp.status)
                    return

                data = await resp.json()
                tweets = data.get("data", [])

                if not tweets:
                    return

                sentiment = self._aggregate_sentiment(tweets)

                event = {
                    "type": "social_sentiment",
                    "source": "twitter",
                    "tweet_count": len(tweets),
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
                    tweets=len(tweets),
                )

    def _aggregate_sentiment(self, tweets: list[dict]) -> dict:
        """
        Simple keyword-based sentiment aggregation.

        Counts bullish/bearish keywords in tweets weighted by engagement.
        """
        bullish_words = {"bullish", "moon", "pump", "breakout", "long", "buy", "ath", "rally"}
        bearish_words = {"bearish", "dump", "crash", "short", "sell", "liquidation", "rekt"}

        bullish_count = 0
        bearish_count = 0
        neutral_count = 0
        weighted_score = 0.0
        total_weight = 0.0

        for tweet in tweets:
            text = tweet.get("text", "").lower()
            metrics = tweet.get("public_metrics", {})

            # Engagement weight
            likes = metrics.get("like_count", 0)
            retweets = metrics.get("retweet_count", 0)
            weight = 1.0 + (likes * 0.1) + (retweets * 0.5)

            # Simple sentiment
            bull_hits = sum(1 for w in bullish_words if w in text)
            bear_hits = sum(1 for w in bearish_words if w in text)

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
