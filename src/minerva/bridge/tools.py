"""
Minerva AI — MCP Tool Schema Definitions.

Defines all tools exposed by the Minerva MCP Server for Hermes Agent.
Each tool has a name, description, and JSON Schema for input parameters.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Data Tools (Read-only)
# --------------------------------------------------------------------------

TOOL_GET_MARKET_SUMMARY = {
    "name": "minerva_get_market_summary",
    "description": (
        "Get real-time market summary for a crypto trading pair. "
        "Returns current price, 24h volume, high/low, bid/ask spread, "
        "order book imbalance, and technical indicators (RSI, MACD)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Trading pair symbol, e.g. BTC/USDT",
            },
        },
        "required": ["symbol"],
    },
}

TOOL_GET_ALL_MARKETS = {
    "name": "minerva_get_all_markets",
    "description": (
        "Get market summaries for all tracked trading pairs. "
        "Returns a dictionary of symbol -> market summary data."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
    },
}

TOOL_GET_SIGNALS = {
    "name": "minerva_get_signals",
    "description": (
        "Get the latest fast-path trading signal for a symbol. "
        "Returns signal score (-1 to 1), confidence, and metadata "
        "including RSI, MACD, Bollinger Bands, and order book imbalance."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Trading pair symbol, e.g. BTC/USDT",
            },
        },
        "required": ["symbol"],
    },
}

TOOL_GET_POSITIONS = {
    "name": "minerva_get_positions",
    "description": (
        "Get all currently open trading positions. "
        "Returns position details including symbol, side, amount, "
        "entry price, current price, unrealized PnL, and PnL percentage."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
    },
}

TOOL_GET_PORTFOLIO_STATUS = {
    "name": "minerva_get_portfolio_status",
    "description": (
        "Get overall portfolio and risk status. "
        "Returns available balance, total exposure, open positions count, "
        "risk engine status (circuit breaker, daily PnL, drawdown), "
        "and agent mode (paper/live)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
    },
}

TOOL_GET_NEWS = {
    "name": "minerva_get_news",
    "description": (
        "Get recent crypto news articles. "
        "Returns title, source, URL, matched currencies, "
        "sentiment score, and publication timestamp."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Max number of news items to return (default 10)",
                "default": 10,
            },
        },
    },
}

TOOL_GET_ONCHAIN_ALERTS = {
    "name": "minerva_get_onchain_alerts",
    "description": (
        "Get recent on-chain events and whale alerts. "
        "Returns large transfers, smart contract interactions, "
        "and whale wallet movements detected by Minerva."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Max number of events to return (default 10)",
                "default": 10,
            },
        },
    },
}

TOOL_GET_TRADE_HISTORY = {
    "name": "minerva_get_trade_history",
    "description": (
        "Get recent trade history. Returns completed trades "
        "with entry/exit prices, PnL, duration, and reasoning."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Max number of trades to return (default 20)",
                "default": 20,
            },
        },
    },
}

TOOL_GET_OHLCV = {
    "name": "minerva_get_ohlcv",
    "description": (
        "Get OHLCV (Open-High-Low-Close-Volume) candlestick data "
        "for a trading pair. Useful for technical analysis."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Trading pair symbol, e.g. BTC/USDT",
            },
            "timeframe": {
                "type": "string",
                "description": "Candle timeframe: 1m, 5m, 15m, 1h, 4h, 1d",
                "default": "1m",
            },
            "limit": {
                "type": "integer",
                "description": "Max number of candles (default 100)",
                "default": 100,
            },
        },
        "required": ["symbol"],
    },
}

# --------------------------------------------------------------------------
# All tools registry
# --------------------------------------------------------------------------

ALL_TOOLS: list[dict] = [
    # Data tools
    TOOL_GET_MARKET_SUMMARY,
    TOOL_GET_ALL_MARKETS,
    TOOL_GET_SIGNALS,
    TOOL_GET_POSITIONS,
    TOOL_GET_PORTFOLIO_STATUS,
    TOOL_GET_NEWS,
    TOOL_GET_ONCHAIN_ALERTS,
    TOOL_GET_TRADE_HISTORY,
    TOOL_GET_OHLCV,
]

# Tools that require user approval before execution
TOOLS_REQUIRE_APPROVAL: set[str] = set()
