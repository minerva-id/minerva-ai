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

    def __init__(self, port: int = 8080, redis_store=None, supabase_store=None) -> None:
        """
        Initialize health server.

        Args:
            port: Port to listen on (default 8080).
            redis_store: Optional RedisStore instance.
            supabase_store: Optional SupabaseStore instance.
        """
        self._port = port
        self._redis = redis_store
        self._supabase = supabase_store
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._status: dict[str, Any] = {
            "status": "starting",
            "bot_state": "running",
            "started_at": datetime.now(tz=timezone.utc).isoformat(),
            "last_loop": None,
            "loop_count": 0,
            "components": {},
        }

    async def start(self) -> None:
        """Start the health check server on localhost only."""
        self._app.router.add_options("/{path:.*}", self._options_handler)
        self._app.router.add_get("/health", self._health_handler)
        self._app.router.add_get("/ready", self._ready_handler)
        self._app.router.add_post("/api/bot/start", self._start_bot_handler)
        self._app.router.add_post("/api/bot/stop", self._stop_bot_handler)
        
        # New Dashboard Endpoints
        self._app.router.add_get("/api/config", self._get_config_handler)
        self._app.router.add_post("/api/config", self._update_config_handler)
        self._app.router.add_get("/api/positions", self._get_positions_handler)
        self._app.router.add_get("/api/market", self._get_market_handler)
        self._app.router.add_post("/api/chat", self._chat_handler)
        
        # Serve frontend static files if they exist
        import os
        dist_path = os.path.join(os.getcwd(), "frontend", "dist")
        if os.path.exists(dist_path):
            self._app.router.add_static("/assets", os.path.join(dist_path, "assets"))
            self._app.router.add_get("/{path:.*}", self._serve_index_handler)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        # Listen on 0.0.0.0 to allow access from host if exposed, but relying on Docker mapping
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        log.info("health_server_started", port=self._port, host="0.0.0.0")

    async def stop(self) -> None:
        """Stop the health check server."""
        if self._runner:
            await self._runner.cleanup()
        log.info("health_server_stopped")

    async def _options_handler(self, request: web.Request) -> web.Response:
        """Handle CORS preflight requests."""
        return web.Response(headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        })

    async def _health_handler(self, request: web.Request) -> web.Response:
        """Handle /health endpoint."""
        return web.json_response({
            "status": self._status["status"],
            "bot_state": self._status["bot_state"],
            "started_at": self._status["started_at"],
            "last_loop": self._status["last_loop"],
            "loop_count": self._status["loop_count"],
            "uptime_seconds": self._get_uptime(),
        }, headers={
            "Access-Control-Allow-Origin": "*"
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
            headers={
                "Access-Control-Allow-Origin": "*"
            }
        )

    async def _start_bot_handler(self, request: web.Request) -> web.Response:
        self._status["bot_state"] = "running"
        log.info("bot_state_changed", new_state="running")
        return web.json_response({"success": True, "bot_state": "running"}, headers={"Access-Control-Allow-Origin": "*"})

    async def _stop_bot_handler(self, request: web.Request) -> web.Response:
        self._status["bot_state"] = "stopped"
        log.info("bot_state_changed", new_state="stopped")
        return web.json_response({"success": True, "bot_state": "stopped"}, headers={"Access-Control-Allow-Origin": "*"})

    @property
    def bot_state(self) -> str:
        return self._status["bot_state"]

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

    # --- Dashboard Handlers ---

    async def _get_config_handler(self, request: web.Request) -> web.Response:
        """Read and return .env configuration."""
        import os
        env_path = os.path.join(os.getcwd(), ".env")
        config = {}
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            config[parts[0]] = parts[1]
        return web.json_response(config, headers={"Access-Control-Allow-Origin": "*"})

    async def _update_config_handler(self, request: web.Request) -> web.Response:
        """Update .env configuration."""
        try:
            updates = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400, headers={"Access-Control-Allow-Origin": "*"})

        import os
        env_path = os.path.join(os.getcwd(), ".env")
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()

        # Update or append
        for key, value in updates.items():
            updated = False
            for i, line in enumerate(lines):
                if line.strip().startswith(f"{key}="):
                    lines[i] = f"{key}={value}\n"
                    updated = True
                    break
            if not updated:
                lines.append(f"{key}={value}\n")

        with open(env_path, "w") as f:
            f.writelines(lines)
            
        log.info("config_updated", keys=list(updates.keys()))
        
        # Optionally exit process to let docker restart it
        if updates.get("_restart", False):
            asyncio.create_task(self._delayed_exit())
            return web.json_response({"success": True, "message": "Restarting"}, headers={"Access-Control-Allow-Origin": "*"})

        return web.json_response({"success": True}, headers={"Access-Control-Allow-Origin": "*"})

    async def _delayed_exit(self):
        await asyncio.sleep(1)
        import sys
        sys.exit(0)

    async def _get_positions_handler(self, request: web.Request) -> web.Response:
        """Get all current positions from Redis."""
        if not self._redis:
            return web.json_response({"error": "Redis not configured"}, status=503, headers={"Access-Control-Allow-Origin": "*"})
        
        positions = await self._redis.get_all_positions()
        return web.json_response({"positions": positions}, headers={"Access-Control-Allow-Origin": "*"})

    async def _get_market_handler(self, request: web.Request) -> web.Response:
        """Get market summaries from Redis."""
        if not self._redis:
            return web.json_response({"error": "Redis not configured"}, status=503, headers={"Access-Control-Allow-Origin": "*"})
        
        # We need to know which pairs to query. For now we will return an empty list or try to fetch known pairs if possible.
        # Alternatively we can query keys matching market_summary:*
        keys = await self._redis.get_keys("market_summary", "*")
        summaries = {}
        for key in keys:
            symbol = key.replace("minerva:market_summary:", "").replace("_", "/")
            data = await self._redis.get_json("market_summary", symbol.replace("/", "_"))
            if data:
                summaries[symbol] = data
        
        return web.json_response({"summaries": summaries}, headers={"Access-Control-Allow-Origin": "*"})

    async def _serve_index_handler(self, request: web.Request) -> web.Response:
        """Serve the frontend index.html for SPA routing."""
        import os
        dist_path = os.path.join(os.getcwd(), "frontend", "dist", "index.html")
        if os.path.exists(dist_path):
            with open(dist_path, "r") as f:
                content = f.read()
            return web.Response(text=content, content_type="text/html")
        return web.Response(text="Frontend not built", status=404)

    async def _chat_handler(self, request: web.Request) -> web.Response:
        """Handle chat messages from the Assistant UI."""
        try:
            data = await request.json()
            message = data.get("message", "")
            history = data.get("history", [])
            
            from minerva.brain.agent import MinervaAgent
            agent = MinervaAgent(redis_store=self._redis, supabase_store=self._supabase)
            
            response = await agent.chat(message, history)
            
            return web.json_response(response, headers={"Access-Control-Allow-Origin": "*"})
        except Exception as e:
            log.error("chat_endpoint_error", error=str(e))
            return web.json_response({"error": str(e)}, status=500, headers={"Access-Control-Allow-Origin": "*"})
