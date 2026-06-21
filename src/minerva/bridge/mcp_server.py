"""
Minerva AI — MCP (Model Context Protocol) Server.

HTTP + SSE server that implements the MCP protocol, exposing Minerva's
data and execution capabilities as tools callable by Hermes Agent.

Binds to 127.0.0.1 by default for security (localhost only).
Uses aiohttp for async HTTP handling.

Security notes:
- Listens on 127.0.0.1 only (not 0.0.0.0) to prevent external access
- Optional bearer token authentication via MCP_AUTH_TOKEN env var
- All tool inputs are validated before processing
- Execution tools go through RiskEngine validation
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import orjson
from aiohttp import web

from minerva.bridge.handlers import MinervaToolHandlers
from minerva.bridge.tools import ALL_TOOLS
from minerva.logger import get_logger

log = get_logger(__name__)


class MinervaAPIBridge:
    """
    MCP-compatible HTTP server for Hermes Agent integration.

    Implements a subset of the MCP protocol over HTTP + SSE:
    - GET  /mcp/tools          → List available tools
    - POST /mcp/tools/call     → Invoke a tool
    - GET  /mcp/health         → Health check
    - GET  /mcp/sse            → SSE stream for real-time updates

    All responses use JSON. CORS is restricted to localhost origins.
    """

    def __init__(
        self,
        redis: Any,
        aggregator: Any,
        oms: Any,
        risk_engine: Any,
        gateways: dict[str, Any],
        settings: Any,
        health_server: Any | None = None,
        host: str = "127.0.0.1",
        port: int = 9100,
        auth_token: str = "",
    ) -> None:
        """
        Initialize the MCP bridge server.

        Args:
            redis: RedisStore instance.
            aggregator: DataAggregator instance.
            oms: OrderManagementSystem instance.
            risk_engine: RiskEngine instance.
            gateways: Dict of exchange gateways.
            settings: Application settings.
            health_server: Optional HealthServer reference.
            host: Bind address (default 127.0.0.1 for security).
            port: Listen port (default 9100).
            auth_token: Optional bearer token for authentication.
        """
        self._host = host
        self._port = port
        self._auth_token = auth_token
        self._app = web.Application()
        self._runner: web.AppRunner | None = None

        # SSE subscribers for real-time updates
        self._sse_clients: list[web.StreamResponse] = []

        # Internal event queue for WebSocket relay bridge
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

        # Initialize tool handlers with Minerva components
        self._handlers = MinervaToolHandlers(
            redis=redis,
            aggregator=aggregator,
            oms=oms,
            risk_engine=risk_engine,
            gateways=gateways,
            settings=settings,
            health_server=health_server,
        )

    def get_event_queue(self) -> asyncio.Queue:
        """Get a queue that receives copies of all SSE broadcast events.

        Used by the WebSocket relay to forward events to browser clients
        without making a loopback HTTP/SSE connection.
        """
        return self._event_queue

    async def start(self) -> None:
        """Start the MCP server."""
        # Register routes
        self._app.router.add_options("/{path:.*}", self._cors_preflight)
        self._app.router.add_get("/mcp/health", self._handle_health)
        self._app.router.add_get("/mcp/tools", self._handle_list_tools)
        self._app.router.add_post("/mcp/tools/call", self._handle_call_tool)
        self._app.router.add_get("/mcp/sse", self._handle_sse)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()

        log.info(
            "mcp_server_started",
            host=self._host,
            port=self._port,
            tools_count=len(ALL_TOOLS),
        )

    async def stop(self) -> None:
        """Stop the MCP server and close SSE connections."""
        # Close SSE clients
        for client in self._sse_clients:
            try:
                await client.write_eof()
            except Exception:
                pass
        self._sse_clients.clear()

        if self._runner:
            await self._runner.cleanup()

        log.info("mcp_server_stopped")

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _check_auth(self, request: web.Request) -> bool:
        """
        Validate bearer token authentication if configured.

        Returns True if auth passes or no token is configured.
        """
        if not self._auth_token:
            return True  # No auth configured — localhost-only is acceptable

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False

        token = auth_header[7:]  # Strip "Bearer " prefix
        # Use constant-time comparison to prevent timing attacks
        import hmac
        return hmac.compare_digest(token, self._auth_token)

    def _cors_headers(self) -> dict[str, str]:
        """Return restrictive CORS headers for localhost access."""
        return {
            "Access-Control-Allow-Origin": "http://127.0.0.1",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Cache-Control": "no-store",
        }

    # ------------------------------------------------------------------
    # Route Handlers
    # ------------------------------------------------------------------

    async def _cors_preflight(self, request: web.Request) -> web.Response:
        """Handle CORS preflight OPTIONS request."""
        return web.Response(headers=self._cors_headers())

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint for the MCP server."""
        return web.json_response(
            {
                "status": "ok",
                "service": "minerva-mcp-bridge",
                "tools_available": len(ALL_TOOLS),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
            headers=self._cors_headers(),
        )

    async def _handle_list_tools(self, request: web.Request) -> web.Response:
        """
        List all available MCP tools.

        Response format follows MCP tools/list convention.
        """
        if not self._check_auth(request):
            return web.json_response(
                {"error": "Unauthorized"},
                status=401,
                headers=self._cors_headers(),
            )

        return web.json_response(
            {"tools": ALL_TOOLS},
            headers=self._cors_headers(),
        )

    async def _handle_call_tool(self, request: web.Request) -> web.Response:
        """
        Invoke a tool by name with given parameters.

        Expected JSON body:
        {
            "name": "minerva_get_market_summary",
            "arguments": {"symbol": "BTC/USDT"}
        }
        """
        if not self._check_auth(request):
            return web.json_response(
                {"error": "Unauthorized"},
                status=401,
                headers=self._cors_headers(),
            )

        try:
            body = await request.json()
        except Exception:
            return web.json_response(
                {"error": "Invalid JSON body"},
                status=400,
                headers=self._cors_headers(),
            )

        tool_name = body.get("name", "")
        arguments = body.get("arguments", {})

        if not tool_name:
            return web.json_response(
                {"error": "Tool 'name' is required"},
                status=400,
                headers=self._cors_headers(),
            )

        # Validate tool name against known tools to prevent injection
        known_names = {t["name"] for t in ALL_TOOLS}
        if tool_name not in known_names:
            return web.json_response(
                {"error": f"Unknown tool: {tool_name}"},
                status=404,
                headers=self._cors_headers(),
            )

        # Get handler
        handler = self._handlers.get_handler(tool_name)
        if handler is None:
            return web.json_response(
                {"error": f"No handler for tool: {tool_name}"},
                status=501,
                headers=self._cors_headers(),
            )

        # Execute handler
        try:
            result = await handler(arguments)

            log.info(
                "mcp_tool_called",
                tool=tool_name,
                success=True,
            )

            # Broadcast to SSE clients
            await self._broadcast_sse({
                "type": "tool_result",
                "tool": tool_name,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            })

            # Format as MCP content response
            return web.json_response(
                {
                    "content": [
                        {
                            "type": "text",
                            "text": orjson.dumps(
                                result, option=orjson.OPT_INDENT_2
                            ).decode(),
                        }
                    ],
                    "isError": "error" in result,
                },
                headers=self._cors_headers(),
            )

        except Exception as e:
            log.error(
                "mcp_tool_error",
                tool=tool_name,
                error=str(e),
            )
            return web.json_response(
                {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Tool execution error: {e}",
                        }
                    ],
                    "isError": True,
                },
                status=500,
                headers=self._cors_headers(),
            )

    # ------------------------------------------------------------------
    # SSE (Server-Sent Events) for Real-Time Updates
    # ------------------------------------------------------------------

    async def _handle_sse(self, request: web.Request) -> web.StreamResponse:
        """
        SSE endpoint for streaming real-time updates to Hermes Agent.

        Events include: tool invocations, market alerts, trade executions.
        """
        if not self._check_auth(request):
            return web.json_response(
                {"error": "Unauthorized"},
                status=401,
                headers=self._cors_headers(),
            )

        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Content-Type-Options": "nosniff",
            },
        )
        await response.prepare(request)

        self._sse_clients.append(response)

        # Send initial connection event
        await self._send_sse_event(response, {
            "type": "connected",
            "service": "minerva-mcp-bridge",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })

        try:
            # Keep connection alive with periodic heartbeats
            while True:
                await asyncio.sleep(30)
                try:
                    await response.write(b": heartbeat\n\n")
                except (ConnectionError, ConnectionResetError):
                    break
        except asyncio.CancelledError:
            pass
        finally:
            if response in self._sse_clients:
                self._sse_clients.remove(response)

        return response

    async def _send_sse_event(
        self, response: web.StreamResponse, data: dict
    ) -> None:
        """Send a single SSE event to a client."""
        encoded = orjson.dumps(data).decode()
        message = f"data: {encoded}\n\n"
        try:
            await response.write(message.encode())
        except (ConnectionError, ConnectionResetError):
            if response in self._sse_clients:
                self._sse_clients.remove(response)

    async def _broadcast_sse(self, data: dict) -> None:
        """Broadcast an SSE event to all connected clients."""
        dead_clients: list[web.StreamResponse] = []

        for client in self._sse_clients:
            try:
                await self._send_sse_event(client, data)
            except Exception:
                dead_clients.append(client)

        # Clean up disconnected clients
        for client in dead_clients:
            if client in self._sse_clients:
                self._sse_clients.remove(client)

        # Push to internal event queue for WebSocket relay
        try:
            self._event_queue.put_nowait(data)
        except asyncio.QueueFull:
            pass  # Drop if queue is full

    async def notify_trade(self, trade_data: dict) -> None:
        """
        Public method to broadcast trade events to SSE clients.

        Called by MinervaAgent when a trade is executed.
        """
        await self._broadcast_sse({
            "type": "trade_executed",
            "data": trade_data,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })

    async def notify_alert(self, alert_type: str, data: dict) -> None:
        """
        Public method to broadcast alerts to SSE clients.

        Types: whale_transfer, price_alert, circuit_breaker, etc.
        """
        await self._broadcast_sse({
            "type": "alert",
            "alert_type": alert_type,
            "data": data,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })
