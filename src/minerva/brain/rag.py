"""
Minerva AI — RAG Memory Interface.

Retrieval-Augmented Generation using Pinecone vector store.
Provides past trading experiences as context for LLM decisions.
"""

from __future__ import annotations

from typing import Any

from minerva.logger import get_logger
from minerva.memory.vector_store import VectorStore

log = get_logger(__name__)


class RAGMemory:
    """
    RAG interface for the AI brain.

    Bridges the vector store with the LLM controller by:
    1. Building situation descriptions from current market state
    2. Retrieving similar past experiences
    3. Storing new decision outcomes for future reference
    """

    def __init__(self, vector_store: VectorStore) -> None:
        """
        Initialize RAG memory.

        Args:
            vector_store: Pinecone vector store instance.
        """
        self._store = vector_store

    def build_situation_description(
        self,
        symbol: str,
        signals: dict[str, float],
        sentiment: float,
        market_summary: dict | None = None,
    ) -> str:
        """
        Build a textual description of the current market situation.

        This description is used as the query for similarity search.

        Args:
            symbol: Trading pair.
            signals: Technical indicator scores.
            sentiment: Sentiment score.
            market_summary: Market data summary.

        Returns:
            Formatted situation description string.
        """
        parts = [f"Symbol: {symbol}"]

        if market_summary:
            price = market_summary.get("last_price", 0)
            change = market_summary.get("price_change_24h_pct", 0)
            parts.append(f"Price: ${price:,.2f} ({change:+.2f}% 24h)")
            parts.append(f"Volume: ${market_summary.get('volume_24h', 0):,.0f}")

        # Key signals
        rsi = signals.get("rsi_14", 50)
        macd = signals.get("macd_diff", 0)
        bb = signals.get("bb_position", 0.5)
        adx = signals.get("adx", 0)

        parts.append(f"RSI: {rsi:.1f}")
        parts.append(f"MACD diff: {macd:.4f}")
        parts.append(f"BB position: {bb:.2f}")
        parts.append(f"ADX: {adx:.1f}")
        parts.append(f"Sentiment: {sentiment:.3f}")

        # Classify overall state
        if rsi < 30:
            parts.append("State: OVERSOLD")
        elif rsi > 70:
            parts.append("State: OVERBOUGHT")
        elif adx > 25:
            if macd > 0:
                parts.append("State: STRONG_UPTREND")
            else:
                parts.append("State: STRONG_DOWNTREND")
        else:
            parts.append("State: RANGING")

        return " | ".join(parts)

    async def recall(
        self,
        symbol: str,
        signals: dict[str, float],
        sentiment: float,
        market_summary: dict | None = None,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Recall similar past experiences for the current situation.

        Args:
            symbol: Trading pair.
            signals: Current technical indicators.
            sentiment: Current sentiment score.
            market_summary: Current market data.
            top_k: Number of experiences to retrieve.

        Returns:
            List of past experience dicts with situation, action, outcome, pnl.
        """
        situation = self.build_situation_description(
            symbol, signals, sentiment, market_summary
        )

        experiences = await self._store.recall_similar(situation, top_k=top_k)

        if experiences:
            log.info(
                "rag_recall_complete",
                symbol=symbol,
                results=len(experiences),
                top_pnl=experiences[0].get("pnl", 0),
            )

        return experiences

    async def remember(
        self,
        symbol: str,
        signals: dict[str, float],
        sentiment: float,
        market_summary: dict | None,
        action: str,
        outcome: str,
        pnl: float,
    ) -> None:
        """
        Store a new trading experience for future RAG retrieval.

        Args:
            symbol: Trading pair.
            signals: Technical indicators at time of decision.
            sentiment: Sentiment score at time of decision.
            market_summary: Market data at time of decision.
            action: Action taken (buy/sell/hold).
            outcome: Description of what happened.
            pnl: Realized PnL from this decision.
        """
        situation = self.build_situation_description(
            symbol, signals, sentiment, market_summary
        )

        await self._store.store_experience(
            situation=situation,
            action=action,
            outcome=outcome,
            pnl=pnl,
            metadata={"symbol": symbol},
        )

        log.info(
            "rag_experience_stored",
            symbol=symbol,
            action=action,
            pnl=pnl,
        )
