"""
Minerva AI — LLM Prompt Templates.

System prompts, market summary formatters, and decision output schemas
for the LLM slow path reasoning controller.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


SYSTEM_PROMPT = """You are Minerva, an expert AI crypto trading agent. You analyze market data, technical signals, sentiment, and on-chain activity to make informed trading decisions.

## Your Role
- You manage a crypto trading portfolio across multiple exchanges (Binance, Bybit, OKX)
- You trade top tokens: BTC/USDT, ETH/USDT, SOL/USDT
- You support both scalping (short-term, 1m-15m) and swing trading (medium-term, 1h-1d)
- You prioritize capital preservation over aggressive returns
- You follow strict risk management rules

## Decision Framework
1. Analyze the current market situation (price action, indicators, sentiment)
2. Consider your past experiences from similar situations
3. Evaluate risk/reward ratio
4. Make a clear decision: BUY, SELL, HOLD, or CLOSE

## Risk Rules (MUST FOLLOW)
- Never risk more than the allowed position size per trade
- Always set stop-loss levels
- Consider current exposure before new positions
- If uncertain, default to HOLD
- In high volatility, reduce position sizes

## Output Format
You MUST submit your decision by calling the `submit_trade_decision` function.
Provide all required parameters based on your analysis.

IMPORTANT: Do not output text, just call the tool."""


def format_market_context(
    symbol: str,
    market_summary: dict | None,
    signals: dict[str, float],
    sentiment_score: float,
    news_items: list[dict],
    onchain_events: list[dict],
    current_positions: list[dict],
    past_experiences: list[dict],
    risk_config: dict,
) -> str:
    """
    Format market context for LLM prompt.

    Builds a concise summary of the current market situation
    to minimize token usage while preserving essential information.
    """
    sections: list[str] = []

    # --- Market Data ---
    sections.append(f"## Market Data for {symbol}")
    if market_summary:
        sections.append(f"- Last Price: ${market_summary.get('last_price', 0):,.2f}")
        sections.append(f"- 24h Change: {market_summary.get('price_change_24h_pct', 0):.2f}%")
        sections.append(f"- 24h Volume: ${market_summary.get('volume_24h', 0):,.0f}")
        sections.append(f"- 24h High/Low: ${market_summary.get('high_24h', 0):,.2f} / ${market_summary.get('low_24h', 0):,.2f}")
        sections.append(f"- Bid/Ask Spread: {market_summary.get('spread_pct', 0):.4f}%")
        sections.append(f"- Order Book Imbalance: {market_summary.get('order_book_imbalance', 0):.3f}")
        if market_summary.get('funding_rate') is not None:
            sections.append(f"- Funding Rate: {market_summary['funding_rate']:.6f}")

    # --- Technical Signals ---
    sections.append("\n## Technical Signals (Fast Path)")
    for name, value in signals.items():
        sections.append(f"- {name}: {value:.4f}")

    # --- Sentiment ---
    sections.append(f"\n## Sentiment Score: {sentiment_score:.3f} (-1=bearish, 1=bullish)")

    # --- Recent News ---
    if news_items:
        sections.append("\n## Recent News")
        for news in news_items[:5]:
            title = news.get("title", "")[:100]
            sent = news.get("sentiment", 0)
            sections.append(f"- [{sent:+.2f}] {title}")

    # --- On-Chain Activity ---
    if onchain_events:
        sections.append("\n## On-Chain Activity")
        for event in onchain_events[:3]:
            if event.get("type") == "whale_transfer":
                sections.append(
                    f"- Whale transfer: {event.get('value_eth', 0):.1f} ETH"
                )

    # --- Current Positions ---
    sections.append("\n## Current Positions")
    if current_positions:
        for pos in current_positions:
            sections.append(
                f"- {pos.get('symbol')}: {pos.get('side')} "
                f"{pos.get('amount', 0)} @ ${pos.get('entry_price', 0):,.2f} "
                f"(PnL: {pos.get('pnl_pct', 0):+.2f}%)"
            )
    else:
        sections.append("- No open positions")

    # --- Past Experiences (RAG) ---
    if past_experiences:
        sections.append("\n## Similar Past Situations")
        for exp in past_experiences[:3]:
            sections.append(
                f"- Situation: {exp.get('situation', '')[:150]}\n"
                f"  Action: {exp.get('action', '')} → "
                f"PnL: {exp.get('pnl', 0):+.2f} USD"
            )

    # --- Risk Constraints ---
    sections.append("\n## Risk Constraints")
    sections.append(f"- Max Position Size: ${risk_config.get('max_position_size_usd', 1000):,.0f}")
    sections.append(f"- Max Total Exposure: ${risk_config.get('max_total_exposure_usd', 5000):,.0f}")
    sections.append(f"- Max Drawdown: {risk_config.get('max_drawdown_percent', 10)}%")
    sections.append(f"- Daily Loss Limit: ${risk_config.get('daily_loss_limit_usd', 500):,.0f}")

    sections.append(f"\n## Timestamp: {datetime.utcnow().isoformat()}Z")

    return "\n".join(sections)


# Tool definitions for LLM function calling
LLM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_trade_decision",
            "description": "Submit your final trading decision for the analyzed symbol",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["buy", "sell", "hold", "close"],
                        "description": "Trade action to execute. Default to hold if uncertain.",
                    },
                    "symbol": {
                        "type": "string",
                        "description": "Trading pair symbol being analyzed (e.g., BTC/USDT)",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence level in this decision from 0.0 to 1.0",
                    },
                    "position_size_pct": {
                        "type": "number",
                        "description": "Position size as percentage of capital (0-100)",
                    },
                    "entry_price": {
                        "type": "number",
                        "description": "Target entry price (optional, use if waiting for specific level)",
                    },
                    "stop_loss": {
                        "type": "number",
                        "description": "Stop loss price level (highly recommended for buy/sell)",
                    },
                    "take_profit": {
                        "type": "number",
                        "description": "Take profit price level (highly recommended for buy/sell)",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of your decision",
                    },
                },
                "required": ["action", "symbol", "confidence", "position_size_pct", "reasoning"],
                "additionalProperties": False,
            },
        },
    }
]
