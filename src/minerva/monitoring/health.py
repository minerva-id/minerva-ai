"""
Minerva AI — Health Check Endpoint.

Simple aiohttp health check server for Docker health checks
and monitoring. Listens on localhost only (127.0.0.1).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from aiohttp import web

from minerva.logger import get_logger

log = get_logger(__name__)


class HealthServer:
    """
    Health check HTTP server.

    Exposes a simple /health endpoint on localhost:8080
    for Docker health checks and monitoring probes.
    Listens ONLY on 127.0.0.1 — not exposed externally.
    """

    def __init__(self, port: int = 8080) -> None:
        """
        Initialize health server.

        Args:
            port: Port to listen on (default 8080).
        """
        self._port = port
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._status: dict[str, Any] = {
            "status": "starting",
            "started_at": datetime.now(tz=timezone.utc).isoformat(),
            "last_loop": None,
            "loop_count": 0,
            "components": {},
        }

    async def start(self) -> None:
        """Start the health check server on localhost only."""
        self._app.router.add_get("/health", self._health_handler)
        self._app.router.add_get("/ready", self._ready_handler)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        # SECURITY: Listen on localhost only
        site = web.TCPSite(self._runner, "127.0.0.1", self._port)
        await site.start()
        log.info("health_server_started", port=self._port, host="127.0.0.1")

    async def stop(self) -> None:
        """Stop the health check server."""
        if self._runner:
            await self._runner.cleanup()
        log.info("health_server_stopped")

    async def _health_handler(self, request: web.Request) -> web.Response:
        """Handle /health endpoint."""
        return web.json_response({
            "status": self._status["status"],
            "started_at": self._status["started_at"],
            "last_loop": self._status["last_loop"],
            "loop_count": self._status["loop_count"],
            "uptime_seconds": self._get_uptime(),
        })

    async def _ready_handler(self, request: web.Request) -> web.Response:
        """Handle /ready endpoint."""
        components = self._status.get("components", {})

        # Check critical components
        redis_ok = components.get("redis", False)
        exchange_ok = components.get("exchange", False)

        is_ready = redis_ok and exchange_ok and self._status["status"] == "running"

        status_code = 200 if is_ready else 503
        return web.json_response(
            {
                "ready": is_ready,
                "components": components,
            },
            status=status_code,
        )

    def update_status(self, status: str) -> None:
        """Update agent status."""
        self._status["status"] = status

    def update_loop(self) -> None:
        """Record a completed agent loop."""
        self._status["last_loop"] = datetime.now(tz=timezone.utc).isoformat()
        self._status["loop_count"] += 1

    def update_component(self, name: str, healthy: bool) -> None:
        """Update component health status."""
        self._status["components"][name] = healthy

    def _get_uptime(self) -> int:
        """Calculate uptime in seconds."""
        started = datetime.fromisoformat(self._status["started_at"])
        now = datetime.now(tz=timezone.utc)
        return int((now - started).total_seconds())
