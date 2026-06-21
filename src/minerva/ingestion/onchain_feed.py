"""
Minerva AI — On-chain data feed.

Monitors blockchain activity via Arkham Intelligence REST API Scraper.
Detects whale transfers and large on-chain movements.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiohttp

from minerva.logger import get_logger

log = get_logger(__name__)


class OnChainFeed:
    """
    On-chain data stream via Arkham Intelligence REST API Scraper.

    Polls the Arkham transfers endpoint to detect large movements
    from whales, exchanges, and funds. Replaces previous WebSocket feed.
    """

    def __init__(
        self,
        cookie: str,
        x_payload: str,
        polling_interval: int,
        data_queue: asyncio.Queue,
        whale_threshold_usd: float = 500000.0,
    ) -> None:
        """
        Initialize on-chain feed scraper.

        Args:
            cookie: Arkham session cookie (ARKHAM_COOKIE).
            x_payload: Arkham x-payload header (ARKHAM_X_PAYLOAD).
            polling_interval: Seconds between polls.
            data_queue: Queue to publish on-chain events.
            whale_threshold_usd: Minimum USD value to consider a whale transfer.
        """
        self._cookie = cookie
        self._x_payload = x_payload
        self._polling_interval = polling_interval
        self._queue = data_queue
        self._whale_threshold_usd = whale_threshold_usd
        
        self._running = False
        self._task: asyncio.Task | None = None
        self._seen_txs: set[str] = set()
        self._seen_tx_list: list[str] = []

    async def start(self) -> None:
        """Start Arkham monitoring."""
        if not self._cookie or not self._x_payload:
            log.info("onchain_feed_disabled", reason="missing arkham credentials")
            return

        self._running = True
        self._task = asyncio.create_task(
            self._monitor_loop(),
            name="arkham_scraper",
        )
        log.info(
            "onchain_feed_started", 
            provider="arkham",
            threshold_usd=self._whale_threshold_usd,
            interval=self._polling_interval
        )

    async def stop(self) -> None:
        """Stop Arkham monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("onchain_feed_stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop doing periodic HTTP polling."""
        url = (
            "https://api.arkm.com/transfers"
            "?sortKey=time&sortDir=desc&flow=all&limit=16&offset=0"
            f"&usdGte={int(self._whale_threshold_usd)}"
            "&base=type%3Adex%2Ctype%3Acex%2Ctype%3Afund%2Ctype%3Aindividual"
            "&tokens=bitcoin%2Csolana%2Cethereum"
        )

        async with aiohttp.ClientSession() as session:
            while self._running:
                headers = {
                    "accept": "application/json, text/plain, */*",
                    "accept-language": "en-US,en;q=0.9,id;q=0.8",
                    "origin": "https://arkm.com",
                    "referer": "https://arkm.com/",
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-site",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
                    "cookie": self._cookie,
                    "x-payload": self._x_payload,
                    "x-timestamp": str(int(datetime.now(timezone.utc).timestamp())),
                }

                try:
                    async with session.get(url, headers=headers, timeout=10.0) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            await self._process_transfers(data.get("transfers", []))
                        elif resp.status in (401, 403):
                            log.warning(
                                "arkham_auth_error", 
                                status=resp.status, 
                                message="Cookie or x-payload may be expired"
                            )
                        else:
                            text = await resp.text()
                            log.warning("arkham_http_error", status=resp.status, body=text[:200])
                
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.error("arkham_poll_error", error=str(e))
                
                await asyncio.sleep(self._polling_interval)

    async def _process_transfers(self, transfers: list[dict]) -> None:
        """Process incoming transfers and publish new whales."""
        # Process oldest first to maintain chronological order
        for tx in reversed(transfers):
            tx_id = tx.get("transactionHash") or tx.get("id") or tx.get("txid")
            if not tx_id or tx_id in self._seen_txs:
                continue
                
            self._seen_txs.add(tx_id)
            self._seen_tx_list.append(tx_id)
            
            # Prevent memory leak by keeping max 1000 seen txs
            if len(self._seen_tx_list) > 1000:
                oldest = self._seen_tx_list.pop(0)
                self._seen_txs.discard(oldest)
                
            usd_value = tx.get("historicalUSD", 0)
            if usd_value < self._whale_threshold_usd:
                continue
                
            # Extract from/to entities
            from_addr = tx.get("fromAddress", {})
            from_entity = from_addr.get("arkhamEntity") or {}
            from_name = from_entity.get("name") or from_addr.get("address", "Unknown")
            
            to_addr = tx.get("toAddress", {})
            to_entity = to_addr.get("arkhamEntity") or {}
            to_name = to_entity.get("name") or to_addr.get("address", "Unknown")

            # Try to resolve token symbol natively or via chain
            chain = tx.get("chain", "")
            token_symbol = tx.get("tokenSymbol")
            if not token_symbol:
                if chain == "bitcoin":
                    token_symbol = "BTC"
                elif chain == "ethereum":
                    token_symbol = "ETH"
                elif chain == "solana":
                    token_symbol = "SOL"
                else:
                    token_symbol = chain.upper()

            event = {
                "type": "whale_transfer",
                "from": from_name,
                "to": to_name,
                "value_usd": usd_value,
                "value_eth": tx.get("unitValue", 0),  # Can be BTC/SOL/ETH amount depending on token
                "token": token_symbol,
                "tx_hash": tx_id,
                "timestamp": tx.get("blockTimestamp", datetime.now(timezone.utc).isoformat()),
            }
            
            await self._queue.put(("onchain", event))
            log.info(
                "whale_detected",
                token=event["token"],
                value_usd=round(usd_value, 2),
                from_entity=from_name,
                to_entity=to_name,
            )
