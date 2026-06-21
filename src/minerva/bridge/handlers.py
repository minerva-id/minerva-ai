"""
Minerva AI — MCP Tool Handlers.

Implements the business logic for each MCP tool. Each handler receives
validated parameters and interacts with Minerva's core components
(Redis, Aggregator, OMS, RiskEngine, Gateways) to fulfill requests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from minerva.logger import get_logger

log = get_logger(__name__)


class MinervaToolHandlers:
    """
    Handler implementations for all Minerva MCP tools.

    Each method corresponds to a tool defined in tools.py.
    Dependencies are injected via the constructor so handlers
    can access Minerva's live state without tight coupling.
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
    ) -> None:
        """
        Initialize tool handlers with Minerva component references.

        Args:
            redis: RedisStore instance for cached state.
            aggregator: DataAggregator instance for in-memory data.
            oms: OrderManagementSystem instance.
            risk_engine: RiskEngine instance for validation.
            gateways: Dict of exchange_id -> gateway instances.
            settings: Application Settings instance.
            health_server: Optional HealthServer for bot control.
        """
        self._redis = redis
        self._aggregator = aggregator
        self._oms = oms
        self._risk_engine = risk_engine
        self._gateways = gateways
        self._settings = settings
        self._health = health_server

    # ------------------------------------------------------------------
    # Data Tools (Read-only)
    # ------------------------------------------------------------------

    async def handle_get_market_summary(self, params: dict) -> dict:
        """Get real-time market summary for a trading pair."""
        symbol = params.get("symbol", "")
        if not symbol:
            return {"error": "symbol is required"}

        summary = await self._redis.get_market_summary(symbol)
        if summary is None:
            return {"error": f"No market data available for {symbol}"}

        return {"symbol": symbol, "data": summary}

    async def handle_get_all_markets(self, params: dict) -> dict:
        """Get market summaries for all tracked pairs."""
        pairs = self._settings.get_trading_pairs_list()
        summaries: dict[str, Any] = {}

        for symbol in pairs:
            data = await self._redis.get_market_summary(symbol)
            if data:
                summaries[symbol] = data

        return {"pairs_tracked": len(pairs), "summaries": summaries}

    async def handle_get_signals(self, params: dict) -> dict:
        """Get latest fast-path signal for a symbol."""
        symbol = params.get("symbol", "")
        if not symbol:
            return {"error": "symbol is required"}

        signal = await self._redis.get_signal(symbol)
        if signal is None:
            return {"error": f"No signal data available for {symbol}"}

        return {"symbol": symbol, "signal": signal}

    async def handle_get_positions(self, params: dict) -> dict:
        """Get all open positions."""
        if self._oms is None:
            return {"error": "OMS not initialized"}

        positions = self._oms.get_all_positions()
        result: dict[str, Any] = {}

        for symbol, pos in positions.items():
            result[symbol] = pos.model_dump(mode="json")

        return {
            "count": len(result),
            "total_exposure_usd": round(self._oms.get_total_exposure(), 2),
            "positions": result,
        }

    async def handle_get_portfolio_status(self, params: dict) -> dict:
        """Get portfolio overview and risk status."""
        # Balance from primary exchange
        primary = self._settings.primary_exchange
        gateway = self._gateways.get(primary)
        balance = 0.0
        if gateway:
            try:
                balance = await gateway.get_balance("USDT")
            except Exception as e:
                log.warning("portfolio_balance_error", error=str(e))

        # Positions
        positions_count = 0
        total_exposure = 0.0
        if self._oms:
            positions_count = len(self._oms.get_all_positions())
            total_exposure = self._oms.get_total_exposure()

        # Risk status
        risk_status: dict[str, Any] = {}
        if self._risk_engine:
            risk_status = self._risk_engine.get_risk_status()

        return {
            "agent_mode": self._settings.agent_mode,
            "primary_exchange": primary,
            "available_balance_usd": round(balance, 2),
            "open_positions": positions_count,
            "total_exposure_usd": round(total_exposure, 2),
            "risk": risk_status,
            "trading_pairs": self._settings.get_trading_pairs_list(),
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    async def handle_get_news(self, params: dict) -> dict:
        """Get recent crypto news."""
        limit = min(params.get("limit", 10), 50)

        if self._aggregator is None:
            return {"error": "Aggregator not initialized"}

        news = self._aggregator.get_recent_news(limit=limit)
        return {"count": len(news), "items": news}

    async def handle_get_onchain_alerts(self, params: dict) -> dict:
        """Get recent on-chain events."""
        limit = min(params.get("limit", 10), 50)

        if self._aggregator is None:
            return {"error": "Aggregator not initialized"}

        events = self._aggregator.get_onchain_events(limit=limit)
        return {"count": len(events), "events": events}

    async def handle_get_trade_history(self, params: dict) -> dict:
        """Get recent trade history from Supabase."""
        limit = min(params.get("limit", 20), 100)

        # Try Supabase first for persistent history
        # If not available, return empty with a note
        return {
            "count": 0,
            "trades": [],
            "note": "Trade history requires Supabase connection. "
            "Check active positions via minerva_get_positions.",
        }

    async def handle_get_ohlcv(self, params: dict) -> dict:
        """Get OHLCV candlestick data."""
        symbol = params.get("symbol", "")
        if not symbol:
            return {"error": "symbol is required"}

        timeframe = params.get("timeframe", "1m")
        limit = min(params.get("limit", 100), 500)
        exchange = self._settings.primary_exchange

        if self._aggregator is None:
            return {"error": "Aggregator not initialized"}

        history = self._aggregator.get_ohlcv_history(
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            limit=limit,
        )

        return {
            "symbol": symbol,
            "exchange": exchange,
            "timeframe": timeframe,
            "count": len(history),
            "candles": history,
        }

    # ------------------------------------------------------------------
    # Router
    # ------------------------------------------------------------------

    def get_handler(self, tool_name: str):
        """
        Get the handler function for a given tool name.

        Returns None if no handler exists for the tool.
        """
        handler_map = {
            "minerva_get_market_summary": self.handle_get_market_summary,
            "minerva_get_all_markets": self.handle_get_all_markets,
            "minerva_get_signals": self.handle_get_signals,
            "minerva_get_positions": self.handle_get_positions,
            "minerva_get_portfolio_status": self.handle_get_portfolio_status,
            "minerva_get_news": self.handle_get_news,
            "minerva_get_onchain_alerts": self.handle_get_onchain_alerts,
            "minerva_get_trade_history": self.handle_get_trade_history,
            "minerva_get_ohlcv": self.handle_get_ohlcv,
        }
        return handler_map.get(tool_name)
