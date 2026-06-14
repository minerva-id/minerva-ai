"""
Minerva AI — Telegram Notification Bot.

Real-time notifications for trade entries/exits, errors,
and daily performance reports via Telegram.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiohttp

from minerva.logger import get_logger

log = get_logger(__name__)


class TelegramNotifier:
    """
    Telegram notification service.

    Sends trade alerts, error notifications, and daily reports
    to a configured Telegram chat. Implements rate limiting
    to avoid Telegram API throttling.
    """

    API_BASE = "https://api.telegram.org/bot{token}"
    MAX_MESSAGE_LENGTH = 4096
    MIN_INTERVAL = 1.0  # Minimum seconds between messages

    def __init__(self, bot_token: str, chat_id: str) -> None:
        """
        Initialize Telegram notifier.

        Args:
            bot_token: Telegram bot token.
            chat_id: Target chat ID.
        """
        self._token = bot_token
        self._chat_id = chat_id
        self._base_url = self.API_BASE.format(token=bot_token)
        self._last_send_time = 0.0
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._sender_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the message sender background task."""
        self._sender_task = asyncio.create_task(
            self._sender_loop(),
            name="telegram_sender",
        )
        log.info("telegram_notifier_started")

    async def stop(self) -> None:
        """Stop the sender task."""
        if self._sender_task:
            self._sender_task.cancel()
            try:
                await self._sender_task
            except asyncio.CancelledError:
                pass
        log.info("telegram_notifier_stopped")

    async def _sender_loop(self) -> None:
        """Background loop that sends queued messages."""
        while True:
            try:
                message = await self._queue.get()
                await self._send_message(message)
                self._queue.task_done()
                await asyncio.sleep(self.MIN_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("telegram_send_error", error=str(e))
                await asyncio.sleep(5)

    async def _send_message(self, text: str) -> bool:
        """Send a message to Telegram."""
        # Truncate if too long
        if len(text) > self.MAX_MESSAGE_LENGTH:
            text = text[: self.MAX_MESSAGE_LENGTH - 20] + "\n\n... (truncated)"

        url = f"{self._base_url}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return True
                    elif resp.status == 429:
                        # Rate limited
                        data = await resp.json()
                        retry_after = data.get("parameters", {}).get("retry_after", 30)
                        log.warning("telegram_rate_limited", retry_after=retry_after)
                        await asyncio.sleep(retry_after)
                        return False
                    else:
                        log.warning("telegram_api_error", status=resp.status)
                        return False
        except Exception as e:
            log.warning("telegram_send_error", error=str(e))
            return False

    def _enqueue(self, message: str) -> None:
        """Add message to send queue."""
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            log.warning("telegram_queue_full")

    # --- Notification Methods ---

    def notify_trade_entry(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        reasoning: str = "",
    ) -> None:
        """Send trade entry notification."""
        emoji = "🟢" if side == "buy" else "🔴"
        message = (
            f"{emoji} <b>Trade Entry</b>\n\n"
            f"📊 <b>{symbol}</b>\n"
            f"Side: {side.upper()}\n"
            f"Amount: {amount:.6f}\n"
            f"Price: ${price:,.2f}\n"
            f"Value: ${amount * price:,.2f}\n"
        )
        if stop_loss:
            message += f"🛑 Stop Loss: ${stop_loss:,.2f}\n"
        if take_profit:
            message += f"🎯 Take Profit: ${take_profit:,.2f}\n"
        if reasoning:
            message += f"\n💭 <i>{reasoning[:200]}</i>"

        self._enqueue(message)

    def notify_trade_exit(
        self,
        symbol: str,
        side: str,
        pnl: float,
        pnl_pct: float,
        entry_price: float,
        exit_price: float,
        duration_str: str = "",
    ) -> None:
        """Send trade exit notification."""
        emoji = "💰" if pnl >= 0 else "💸"
        pnl_color = "+" if pnl >= 0 else ""
        message = (
            f"{emoji} <b>Trade Closed</b>\n\n"
            f"📊 <b>{symbol}</b>\n"
            f"Side: {side.upper()}\n"
            f"Entry: ${entry_price:,.2f}\n"
            f"Exit: ${exit_price:,.2f}\n"
            f"PnL: <b>{pnl_color}${pnl:,.2f} ({pnl_color}{pnl_pct:.2f}%)</b>\n"
        )
        if duration_str:
            message += f"⏱ Duration: {duration_str}"

        self._enqueue(message)

    def notify_error(self, component: str, error: str) -> None:
        """Send error notification."""
        message = (
            f"🚨 <b>Error Alert</b>\n\n"
            f"Component: {component}\n"
            f"Error: {error[:500]}"
        )
        self._enqueue(message)

    def notify_circuit_breaker(
        self, drawdown_pct: float, daily_pnl: float
    ) -> None:
        """Send circuit breaker activation notification."""
        message = (
            f"🛑 <b>CIRCUIT BREAKER ACTIVATED</b>\n\n"
            f"Trading has been halted!\n"
            f"Drawdown: {drawdown_pct:.2f}%\n"
            f"Daily PnL: ${daily_pnl:,.2f}\n\n"
            f"Manual intervention required to resume."
        )
        self._enqueue(message)

    def notify_daily_report(self, report: dict) -> None:
        """Send daily performance report."""
        total_trades = report.get("total_trades", 0)
        winning = report.get("winning_trades", 0)
        losing = report.get("losing_trades", 0)
        pnl = report.get("total_pnl", 0)
        win_rate = report.get("win_rate", 0)

        emoji = "📈" if pnl >= 0 else "📉"
        pnl_sign = "+" if pnl >= 0 else ""

        message = (
            f"{emoji} <b>Daily Report</b> - {report.get('date', 'N/A')}\n\n"
            f"Total Trades: {total_trades}\n"
            f"Winning: {winning} | Losing: {losing}\n"
            f"Win Rate: {win_rate:.1f}%\n"
            f"PnL: <b>{pnl_sign}${pnl:,.2f}</b>\n"
        )
        if "max_drawdown" in report:
            message += f"Max Drawdown: {report['max_drawdown']:.2f}%\n"

        self._enqueue(message)

    def notify_startup(self, mode: str, pairs: list[str]) -> None:
        """Send agent startup notification."""
        message = (
            f"🚀 <b>Minerva AI Started</b>\n\n"
            f"Mode: {mode.upper()}\n"
            f"Pairs: {', '.join(pairs)}\n"
            f"Time: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
        self._enqueue(message)
