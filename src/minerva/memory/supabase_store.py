"""
Minerva AI — Supabase persistent store.

Trade journal, order history, reasoning logs, and performance metrics.
All queries use parameterized statements via the Supabase client.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from minerva.logger import get_logger

log = get_logger(__name__)


class SupabaseStore:
    """
    Async wrapper for Supabase (PostgreSQL) storage.

    Handles persistent storage for trade journal, order history,
    and agent reasoning logs. Uses fire-and-forget pattern for
    non-critical writes to avoid blocking the main loop.
    """

    def __init__(self, url: str, key: str) -> None:
        """
        Initialize Supabase store.

        Args:
            url: Supabase project URL.
            key: Supabase API key (anon or service role).
        """
        self._url = url
        self._key = key
        self._client: Any = None
        self._write_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)
        self._writer_task: asyncio.Task | None = None

    async def connect(self) -> None:
        """Initialize Supabase client."""
        try:
            from supabase import create_client

            self._client = create_client(self._url, self._key)
            log.info("supabase_connected")

            # Start background writer
            self._writer_task = asyncio.create_task(self._background_writer())
        except Exception as e:
            log.error("supabase_connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Shut down background writer and close connection."""
        if self._writer_task:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass
        log.info("supabase_disconnected")

    async def _background_writer(self) -> None:
        """Background task that processes write queue."""
        while True:
            try:
                item = await self._write_queue.get()
                table = item.pop("_table")
                await asyncio.to_thread(
                    lambda t=table, d=item: self._client.table(t).insert(d).execute()
                )
                self._write_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("supabase_write_error", error=str(e))
                await asyncio.sleep(1)

    def _enqueue_write(self, table: str, data: dict) -> None:
        """Enqueue a write operation (fire-and-forget)."""
        try:
            record = {**data, "_table": table}
            self._write_queue.put_nowait(record)
        except asyncio.QueueFull:
            log.warning("supabase_write_queue_full", table=table)

    # --- Trade Journal ---

    async def log_trade(self, trade: dict) -> None:
        """
        Log a completed trade to the journal.

        Args:
            trade: TradeRecord dict with entry/exit info and PnL.
        """
        self._enqueue_write("trades", {
            "id": trade.get("id"),
            "symbol": trade.get("symbol"),
            "exchange": trade.get("exchange"),
            "side": trade.get("side"),
            "entry_price": trade.get("entry_price"),
            "exit_price": trade.get("exit_price"),
            "amount": trade.get("amount"),
            "pnl": trade.get("pnl"),
            "pnl_pct": trade.get("pnl_pct"),
            "fees_total": trade.get("fees_total", 0),
            "entry_time": trade.get("entry_time"),
            "exit_time": trade.get("exit_time"),
            "duration_seconds": trade.get("duration_seconds", 0),
            "signal_score": trade.get("signal_score"),
            "reasoning": trade.get("reasoning", ""),
            "strategy": trade.get("strategy", "minerva_v1"),
        })
        log.info("trade_logged", symbol=trade.get("symbol"), pnl=trade.get("pnl"))

    # --- Order History ---

    async def log_order(self, order: dict) -> None:
        """Log an order event."""
        self._enqueue_write("orders", {
            "id": order.get("id"),
            "symbol": order.get("symbol"),
            "exchange": order.get("exchange"),
            "side": order.get("side"),
            "order_type": order.get("order_type"),
            "price": order.get("price"),
            "amount": order.get("amount"),
            "filled_amount": order.get("filled_amount", 0),
            "average_fill_price": order.get("average_fill_price"),
            "status": order.get("status"),
            "exchange_order_id": order.get("exchange_order_id", ""),
            "created_at": order.get("created_at"),
            "signal_score": order.get("signal_score"),
            "reasoning": order.get("reasoning", ""),
        })

    # --- Reasoning Logs ---

    async def log_reasoning(
        self,
        symbol: str,
        action: str,
        reasoning: str,
        signals: dict,
        confidence: float,
    ) -> None:
        """
        Log an AI reasoning decision for analysis and learning.

        Args:
            symbol: Trading pair.
            action: Action taken (buy/sell/hold).
            reasoning: LLM reasoning text.
            signals: Dict of signal scores.
            confidence: Decision confidence score.
        """
        self._enqueue_write("reasoning_logs", {
            "symbol": symbol,
            "action": action,
            "reasoning": reasoning,
            "signals": signals,
            "confidence": confidence,
            "timestamp": datetime.utcnow().isoformat(),
        })

    # --- Daily Reports ---

    async def log_daily_report(self, report: dict) -> None:
        """Log daily performance report."""
        self._enqueue_write("daily_reports", {
            "date": report.get("date"),
            "total_trades": report.get("total_trades", 0),
            "winning_trades": report.get("winning_trades", 0),
            "losing_trades": report.get("losing_trades", 0),
            "total_pnl": report.get("total_pnl", 0),
            "max_drawdown": report.get("max_drawdown", 0),
            "win_rate": report.get("win_rate", 0),
            "sharpe_ratio": report.get("sharpe_ratio"),
            "summary": report.get("summary", ""),
        })

    # --- Query Methods ---

    async def get_recent_trades(
        self, symbol: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Query recent trades from journal."""
        try:
            query = self._client.table("trades").select("*").order(
                "exit_time", desc=True
            ).limit(limit)

            if symbol:
                query = query.eq("symbol", symbol)

            result = await asyncio.to_thread(lambda: query.execute())
            return result.data if result.data else []
        except Exception as e:
            log.error("supabase_query_error", error=str(e))
            return []

    async def get_daily_pnl(self, days: int = 30) -> list[dict]:
        """Get daily PnL for the last N days."""
        try:
            result = await asyncio.to_thread(
                lambda: self._client.table("daily_reports")
                .select("date,total_pnl,total_trades,win_rate")
                .order("date", desc=True)
                .limit(days)
                .execute()
            )
            return result.data if result.data else []
        except Exception as e:
            log.error("supabase_query_error", error=str(e))
            return []

    async def health_check(self) -> bool:
        """Check Supabase connectivity."""
        try:
            await asyncio.to_thread(
                lambda: self._client.table("trades").select("id").limit(1).execute()
            )
            return True
        except Exception:
            return False
