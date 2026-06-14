"""
Minerva AI — On-chain data feed.

Monitors blockchain activity via Alchemy/QuickNode WebSocket.
Detects whale transfers and large on-chain movements.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import aiohttp

from minerva.logger import get_logger

log = get_logger(__name__)


class OnChainFeed:
    """
    On-chain data stream via Alchemy WebSocket.

    Subscribes to pending transactions and new blocks to detect
    whale movements and large transfers on Ethereum.
    """

    def __init__(
        self,
        ws_url: str,
        data_queue: asyncio.Queue,
        whale_threshold_eth: float = 100.0,
    ) -> None:
        """
        Initialize on-chain feed.

        Args:
            ws_url: Alchemy/QuickNode WebSocket URL.
            data_queue: Queue to publish on-chain events.
            whale_threshold_eth: Minimum ETH value to consider a whale transfer.
        """
        self._ws_url = ws_url
        self._queue = data_queue
        self._whale_threshold = whale_threshold_eth
        self._running = False
        self._task: asyncio.Task | None = None
        self._ws: Any = None

    async def start(self) -> None:
        """Start on-chain monitoring."""
        if not self._ws_url:
            log.info("onchain_feed_disabled", reason="no WS URL configured")
            return

        self._running = True
        self._task = asyncio.create_task(
            self._monitor_loop(),
            name="onchain_monitor",
        )
        log.info("onchain_feed_started")

    async def stop(self) -> None:
        """Stop on-chain monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("onchain_feed_stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop with reconnection."""
        reconnect_delay = 1.0

        while self._running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(
                        self._ws_url,
                        timeout=aiohttp.ClientWSMsgType(30),
                    ) as ws:
                        self._ws = ws
                        reconnect_delay = 1.0

                        # Subscribe to new pending transactions
                        subscribe_msg = {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "eth_subscribe",
                            "params": ["alchemy_minedTransactions"],
                        }
                        await ws.send_json(subscribe_msg)
                        log.info("onchain_subscribed")

                        async for msg in ws:
                            if not self._running:
                                break

                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._process_message(msg.data)
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                log.warning("onchain_ws_error")
                                break

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning(
                    "onchain_connection_error",
                    error=str(e),
                    reconnect_delay=reconnect_delay,
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60.0)

    async def _process_message(self, raw_data: str) -> None:
        """Process incoming WebSocket message."""
        try:
            data = json.loads(raw_data)

            # Handle subscription result
            if "result" in data and "params" not in data:
                return

            params = data.get("params", {})
            result = params.get("result", {})

            if not result:
                return

            # Extract transaction details
            transactions = result.get("transactions", [])
            for tx in transactions:
                value_wei = int(tx.get("value", "0x0"), 16)
                value_eth = value_wei / 1e18

                if value_eth >= self._whale_threshold:
                    event = {
                        "type": "whale_transfer",
                        "from": tx.get("from", ""),
                        "to": tx.get("to", ""),
                        "value_eth": value_eth,
                        "tx_hash": tx.get("hash", ""),
                        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                    }
                    await self._queue.put(("onchain", event))
                    log.info(
                        "whale_detected",
                        value_eth=round(value_eth, 2),
                        tx_hash=tx.get("hash", "")[:16],
                    )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            log.debug("onchain_parse_error", error=str(e))
