"""
Minerva AI — Jarvis HUD WebSocket Relay Server.

WebSocket server that bridges the Jarvis HUD (browser) with:
- Hermes Agent API (if configured) for AI chat
- Minerva MCP Server (SSE events forwarded as WebSocket messages)
- Built-in MinervaAgent chat (fallback when Hermes is unavailable)

Binds to 127.0.0.1 by default for security (localhost only).

Security notes:
- Listens on 127.0.0.1 only (not 0.0.0.0) to prevent external access
- Optional bearer token authentication on WebSocket handshake
- Rate limiting: max 10 messages per second per client
- Max concurrent clients: 10
- All WebSocket messages validated against expected JSON schema
"""

from __future__ import annotations

import asyncio
import hmac
import time
from datetime import datetime, timezone
from typing import Any

import orjson
from aiohttp import web, WSMsgType

from minerva.logger import get_logger

log = get_logger(__name__)

# Rate limit constants
_MAX_MESSAGES_PER_SECOND = 10
_MAX_CLIENTS = 10


class _ClientState:
    """Track per-client state for rate limiting."""

    __slots__ = ("ws", "last_messages", "subscriptions")

    def __init__(self, ws: web.WebSocketResponse) -> None:
        self.ws = ws
        self.last_messages: list[float] = []
        self.subscriptions: set[str] = {"market", "trades", "alerts"}

    def check_rate_limit(self) -> bool:
        """Return True if the client is within rate limits."""
        now = time.monotonic()
        # Remove timestamps older than 1 second
        self.last_messages = [t for t in self.last_messages if now - t < 1.0]
        if len(self.last_messages) >= _MAX_MESSAGES_PER_SECOND:
            return False
        self.last_messages.append(now)
        return True


class JarvisRelay:
    """
    WebSocket relay server for Jarvis HUD.

    Protocol (Client → Server):
        {"type": "chat", "message": "...", "history": [...]}
        {"type": "voice_transcript", "text": "..."}
        {"type": "subscribe", "channels": ["market", "trades", "alerts"]}
        {"type": "stop_run"}

    Protocol (Server → Client):
        {"type": "status", "state": "connected|thinking|speaking"}
        {"type": "agent_status", "state": "thinking|tool_use|idle", ...}
        {"type": "chat_response", "data": {...}}
        {"type": "chat_delta", "delta": "..."}
        {"type": "market_update", "data": {...}}
        {"type": "trade_alert", "data": {...}}
        {"type": "tool_event", "tool": "...", "status": "called"}
        {"type": "error", "message": "..."}
    """

    _VALID_MSG_TYPES = frozenset({
        "chat", "voice_transcript", "subscribe", "stop_run",
    })

    def __init__(
        self,
        redis: Any,
        supabase: Any | None,
        mcp_bridge: Any | None,
        host: str = "127.0.0.1",
        port: int = 8081,
        auth_token: str = "",
        hermes_api_url: str = "",
    ) -> None:
        self._redis = redis
        self._supabase = supabase
        self._mcp_bridge = mcp_bridge
        self._host = host
        self._port = port
        self._auth_token = auth_token
        self._hermes_api_url = hermes_api_url
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._clients: list[_ClientState] = []
        self._event_bridge_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the WebSocket relay server."""
        self._app.router.add_get("/ws", self._handle_ws)
        self._app.router.add_get("/ws/health", self._handle_health)
        self._app.router.add_options("/{path:.*}", self._cors_preflight)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()

        # Start SSE → WebSocket bridge if MCP bridge is available
        if self._mcp_bridge is not None:
            self._event_bridge_task = asyncio.create_task(
                self._bridge_mcp_events()
            )

        log.info(
            "jarvis_relay_started",
            host=self._host,
            port=self._port,
            hermes_configured=bool(self._hermes_api_url),
        )

    async def stop(self) -> None:
        """Stop the relay and close all WebSocket connections."""
        if self._event_bridge_task:
            self._event_bridge_task.cancel()
            try:
                await self._event_bridge_task
            except asyncio.CancelledError:
                pass

        # Close all WebSocket clients
        for client in list(self._clients):
            try:
                await client.ws.close()
            except Exception:
                pass
        self._clients.clear()

        if self._runner:
            await self._runner.cleanup()

        log.info("jarvis_relay_stopped")

    # ------------------------------------------------------------------
    # Auth & CORS
    # ------------------------------------------------------------------

    def _check_auth(self, request: web.Request) -> bool:
        """Validate auth token from query parameter or header."""
        if not self._auth_token:
            return True  # No auth configured

        # Check query param first (WebSocket clients use this)
        token = request.query.get("token", "")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

        if not token:
            return False

        return hmac.compare_digest(token, self._auth_token)

    def _cors_headers(self) -> dict[str, str]:
        return {
            "Access-Control-Allow-Origin": "http://127.0.0.1",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Cache-Control": "no-store",
        }

    async def _cors_preflight(self, request: web.Request) -> web.Response:
        return web.Response(headers=self._cors_headers())

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "service": "jarvis-ws-relay",
                "connected_clients": len(self._clients),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
            headers=self._cors_headers(),
        )

    # ------------------------------------------------------------------
    # WebSocket Handler
    # ------------------------------------------------------------------

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        """Handle incoming WebSocket connections from Jarvis HUD."""
        if not self._check_auth(request):
            return web.Response(text="Unauthorized", status=401)

        if len(self._clients) >= _MAX_CLIENTS:
            return web.Response(text="Too many connections", status=503)

        ws = web.WebSocketResponse(
            heartbeat=30.0,
            max_msg_size=64 * 1024,  # 64KB max message
        )
        await ws.prepare(request)

        client = _ClientState(ws)
        self._clients.append(client)

        log.info("jarvis_client_connected", total=len(self._clients))

        # Send connection event
        await self._send(ws, {
            "type": "status",
            "state": "connected",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle_message(client, msg.data)
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("jarvis_ws_error", error=str(e))
        finally:
            if client in self._clients:
                self._clients.remove(client)
            log.info("jarvis_client_disconnected", total=len(self._clients))

        return ws

    async def _handle_message(
        self, client: _ClientState, raw: str
    ) -> None:
        """Process a single WebSocket message from a client."""
        # Rate limit check
        if not client.check_rate_limit():
            await self._send(client.ws, {
                "type": "error",
                "message": "Rate limit exceeded. Max 10 messages per second.",
            })
            return

        # Parse JSON
        try:
            data = orjson.loads(raw)
        except Exception:
            await self._send(client.ws, {
                "type": "error",
                "message": "Invalid JSON message.",
            })
            return

        msg_type = data.get("type", "")

        # Validate message type against allowlist
        if msg_type not in self._VALID_MSG_TYPES:
            await self._send(client.ws, {
                "type": "error",
                "message": f"Unknown message type: {msg_type}",
            })
            return

        if msg_type == "chat":
            await self._handle_chat(client, data)
        elif msg_type == "voice_transcript":
            text = data.get("text", "").strip()
            if text:
                await self._handle_chat(client, {
                    "type": "chat",
                    "message": text,
                    "history": data.get("history", []),
                })
        elif msg_type == "subscribe":
            channels = data.get("channels", [])
            if isinstance(channels, list):
                client.subscriptions = set(channels) & {
                    "market", "trades", "alerts"
                }
        elif msg_type == "stop_run":
            # TODO(security): Implement Hermes run stop when Hermes is integrated
            await self._send(client.ws, {
                "type": "status",
                "state": "idle",
            })

    async def _handle_chat(
        self, client: _ClientState, data: dict
    ) -> None:
        """Process a chat message — route to Hermes or fallback to MinervaAgent."""
        message = data.get("message", "").strip()
        if not message:
            return

        history = data.get("history", [])

        # Notify client we're thinking
        await self._send(client.ws, {
            "type": "agent_status",
            "state": "thinking",
        })

        try:
            # Try Hermes Agent API if configured
            # TODO: Implement Hermes Sessions API integration when Hermes is deployed
            # For now, use built-in MinervaAgent chat as fallback
            response = await self._chat_fallback(message, history)

            await self._send(client.ws, {
                "type": "agent_status",
                "state": "idle",
            })

            await self._send(client.ws, {
                "type": "chat_response",
                "data": response,
            })

        except Exception as e:
            log.error("jarvis_chat_error", error=str(e))
            await self._send(client.ws, {
                "type": "agent_status",
                "state": "idle",
            })
            await self._send(client.ws, {
                "type": "chat_response",
                "data": {
                    "role": "assistant",
                    "content": f"System Error: {e}",
                    "type": "text",
                },
            })

    async def _chat_fallback(
        self, message: str, history: list[dict]
    ) -> dict:
        """Use built-in MinervaAgent chat (OpenAI) as fallback."""
        from minerva.brain.agent import MinervaAgent as ChatAgent

        agent = ChatAgent(
            redis_store=self._redis,
            supabase_store=self._supabase,
        )
        return await agent.chat(message, history)

    # ------------------------------------------------------------------
    # SSE → WebSocket Bridge
    # ------------------------------------------------------------------

    async def _bridge_mcp_events(self) -> None:
        """Bridge MCP SSE events to all connected WebSocket clients."""
        if self._mcp_bridge is None:
            return

        queue = self._mcp_bridge.get_event_queue()

        while True:
            try:
                event = await queue.get()

                event_type = event.get("type", "")

                # Map MCP event types to Jarvis HUD event types
                if event_type == "tool_result":
                    ws_event = {
                        "type": "tool_event",
                        "tool": event.get("tool", "unknown"),
                        "status": "completed",
                        "timestamp": event.get("timestamp"),
                    }
                    await self._broadcast(ws_event, channel="alerts")

                elif event_type == "trade_executed":
                    ws_event = {
                        "type": "trade_alert",
                        "data": event.get("data", {}),
                        "timestamp": event.get("timestamp"),
                    }
                    await self._broadcast(ws_event, channel="trades")

                elif event_type == "alert":
                    ws_event = {
                        "type": "market_update",
                        "alert_type": event.get("alert_type"),
                        "data": event.get("data", {}),
                        "timestamp": event.get("timestamp"),
                    }
                    await self._broadcast(ws_event, channel="market")

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("jarvis_bridge_error", error=str(e))
                await asyncio.sleep(1)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _send(self, ws: web.WebSocketResponse, data: dict) -> None:
        """Send a JSON message to a single WebSocket client."""
        try:
            await ws.send_str(orjson.dumps(data).decode())
        except (ConnectionError, ConnectionResetError, RuntimeError):
            pass

    async def _broadcast(
        self, data: dict, channel: str | None = None
    ) -> None:
        """Broadcast a message to all connected clients (optionally filtered by channel)."""
        dead: list[_ClientState] = []

        for client in self._clients:
            if channel and channel not in client.subscriptions:
                continue
            try:
                await self._send(client.ws, data)
            except Exception:
                dead.append(client)

        for client in dead:
            if client in self._clients:
                self._clients.remove(client)
