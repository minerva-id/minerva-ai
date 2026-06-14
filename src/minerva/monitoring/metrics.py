"""
Minerva AI — Prometheus Metrics.

Exposes trading metrics for Grafana dashboards via prometheus_client.
Supports push gateway for cloud monitoring.
"""

from __future__ import annotations

import asyncio
from typing import Any

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    push_to_gateway,
)

from minerva.logger import get_logger

log = get_logger(__name__)


class MetricsCollector:
    """
    Prometheus metrics collector for trading agent.

    Tracks key performance indicators: PnL, trade counts,
    latency, signal accuracy, and error rates.
    """

    def __init__(self, pushgateway_url: str = "") -> None:
        """
        Initialize metrics collector.

        Args:
            pushgateway_url: Prometheus Push Gateway URL for cloud push.
        """
        self._pushgateway_url = pushgateway_url
        self._registry = CollectorRegistry()
        self._push_task: asyncio.Task | None = None

        # --- Counters ---
        self.trades_total = Counter(
            "minerva_trades_total",
            "Total number of trades executed",
            ["symbol", "side", "result"],
            registry=self._registry,
        )

        self.orders_total = Counter(
            "minerva_orders_total",
            "Total number of orders submitted",
            ["symbol", "side", "status"],
            registry=self._registry,
        )

        self.signals_total = Counter(
            "minerva_signals_total",
            "Total number of signals generated",
            ["symbol", "source", "action"],
            registry=self._registry,
        )

        self.errors_total = Counter(
            "minerva_errors_total",
            "Total number of errors",
            ["component", "type"],
            registry=self._registry,
        )

        # --- Gauges ---
        self.pnl_total = Gauge(
            "minerva_pnl_total_usd",
            "Total realized PnL in USD",
            registry=self._registry,
        )

        self.pnl_daily = Gauge(
            "minerva_pnl_daily_usd",
            "Daily realized PnL in USD",
            registry=self._registry,
        )

        self.open_positions = Gauge(
            "minerva_open_positions",
            "Number of open positions",
            registry=self._registry,
        )

        self.total_exposure = Gauge(
            "minerva_total_exposure_usd",
            "Total portfolio exposure in USD",
            registry=self._registry,
        )

        self.drawdown_pct = Gauge(
            "minerva_drawdown_pct",
            "Current drawdown percentage from peak",
            registry=self._registry,
        )

        self.win_rate = Gauge(
            "minerva_win_rate",
            "Win rate of closed trades",
            registry=self._registry,
        )

        # --- Histograms ---
        self.loop_duration = Histogram(
            "minerva_loop_duration_seconds",
            "Duration of main agent loop",
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
            registry=self._registry,
        )

        self.trade_latency = Histogram(
            "minerva_trade_latency_seconds",
            "Time from signal to order execution",
            buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5],
            registry=self._registry,
        )

        self.llm_latency = Histogram(
            "minerva_llm_latency_seconds",
            "LLM API response time",
            buckets=[0.5, 1, 2, 3, 5, 10],
            registry=self._registry,
        )

    async def start_push_loop(self, interval: int = 30) -> None:
        """Start periodic metric push to Prometheus Push Gateway."""
        if not self._pushgateway_url:
            log.info("metrics_push_disabled", reason="no pushgateway URL")
            return

        self._push_task = asyncio.create_task(
            self._push_loop(interval),
            name="metrics_pusher",
        )
        log.info("metrics_push_started", interval=interval)

    async def stop(self) -> None:
        """Stop metrics push loop."""
        if self._push_task:
            self._push_task.cancel()
            try:
                await self._push_task
            except asyncio.CancelledError:
                pass

    async def _push_loop(self, interval: int) -> None:
        """Periodically push metrics to gateway."""
        while True:
            try:
                await asyncio.to_thread(
                    push_to_gateway,
                    self._pushgateway_url,
                    job="minerva_agent",
                    registry=self._registry,
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("metrics_push_error", error=str(e))

            await asyncio.sleep(interval)

    # --- Convenience methods ---

    def record_trade(
        self, symbol: str, side: str, pnl: float
    ) -> None:
        """Record a completed trade."""
        result = "win" if pnl >= 0 else "loss"
        self.trades_total.labels(symbol=symbol, side=side, result=result).inc()

    def record_order(
        self, symbol: str, side: str, status: str
    ) -> None:
        """Record an order event."""
        self.orders_total.labels(symbol=symbol, side=side, status=status).inc()

    def record_signal(
        self, symbol: str, source: str, action: str
    ) -> None:
        """Record a signal generation."""
        self.signals_total.labels(symbol=symbol, source=source, action=action).inc()

    def record_error(self, component: str, error_type: str) -> None:
        """Record an error."""
        self.errors_total.labels(component=component, type=error_type).inc()
