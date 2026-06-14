"""
Minerva AI — Pinecone vector store for RAG memory.

Embeds market situations and decision outcomes for similarity-based retrieval.
Used by the LLM slow path to include "past experience" in prompts.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime
from typing import Any

from minerva.logger import get_logger

log = get_logger(__name__)


class VectorStore:
    """
    Pinecone vector store for long-term memory and RAG.

    Stores embedded market situations alongside decision outcomes.
    Enables the agent to learn from past similar scenarios.
    """

    EMBEDDING_DIM = 1536  # OpenAI text-embedding-3-small dimension

    def __init__(self, api_key: str, index_name: str) -> None:
        """
        Initialize vector store.

        Args:
            api_key: Pinecone API key.
            index_name: Name of the Pinecone index.
        """
        self._api_key = api_key
        self._index_name = index_name
        self._index: Any = None
        self._openai_client: Any = None

    async def connect(self) -> None:
        """Connect to Pinecone and initialize the index."""
        try:
            from pinecone import Pinecone

            pc = Pinecone(api_key=self._api_key)

            # Check if index exists; use existing
            existing = await asyncio.to_thread(lambda: pc.list_indexes().names())
            if self._index_name not in existing:
                log.warning(
                    "pinecone_index_not_found",
                    index=self._index_name,
                    message="Create index manually in Pinecone dashboard",
                )
                return

            self._index = await asyncio.to_thread(
                lambda: pc.Index(self._index_name)
            )
            log.info("pinecone_connected", index=self._index_name)
        except Exception as e:
            log.error("pinecone_connection_failed", error=str(e))

    async def disconnect(self) -> None:
        """Cleanup resources."""
        self._index = None
        log.info("pinecone_disconnected")

    def _generate_id(self, text: str) -> str:
        """Generate a deterministic ID from content."""
        return hashlib.sha256(text.encode()).hexdigest()[:32]

    async def _get_embedding(self, text: str) -> list[float]:
        """
        Get embedding vector for text using OpenAI API.

        Falls back to a simple hash-based embedding if API is unavailable.
        """
        try:
            if self._openai_client is None:
                import openai
                self._openai_client = openai.AsyncOpenAI()

            response = await self._openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            log.warning("embedding_fallback", error=str(e))
            # Fallback: simple hash-based pseudo-embedding
            return self._hash_embedding(text)

    def _hash_embedding(self, text: str) -> list[float]:
        """
        Generate a deterministic pseudo-embedding from text hash.

        This is a fallback when the embedding API is unavailable.
        Not suitable for semantic similarity but maintains functionality.
        """
        import hashlib
        h = hashlib.sha512(text.encode()).digest()
        # Expand to EMBEDDING_DIM values between -1 and 1
        values: list[float] = []
        for i in range(self.EMBEDDING_DIM):
            byte_val = h[i % len(h)]
            values.append((byte_val / 127.5) - 1.0)
        return values

    async def store_experience(
        self,
        situation: str,
        action: str,
        outcome: str,
        pnl: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Store a trading experience for future RAG retrieval.

        Args:
            situation: Description of market situation (indicators, sentiment, etc.).
            action: Action taken (buy/sell/hold).
            outcome: What happened after the action.
            pnl: Profit/loss from this decision.
            metadata: Additional metadata (symbol, timestamp, etc.).
        """
        if self._index is None:
            return

        text = f"Situation: {situation}\nAction: {action}\nOutcome: {outcome}"
        embedding = await self._get_embedding(text)
        doc_id = self._generate_id(text)

        meta = {
            "situation": situation[:1000],  # Pinecone metadata limit
            "action": action,
            "outcome": outcome[:500],
            "pnl": pnl,
            "timestamp": datetime.utcnow().isoformat(),
            **(metadata or {}),
        }

        try:
            await asyncio.to_thread(
                lambda: self._index.upsert(
                    vectors=[{
                        "id": doc_id,
                        "values": embedding,
                        "metadata": meta,
                    }]
                )
            )
            log.info("experience_stored", action=action, pnl=pnl)
        except Exception as e:
            log.error("pinecone_upsert_error", error=str(e))

    async def recall_similar(
        self,
        situation: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Recall similar past experiences for RAG.

        Args:
            situation: Current market situation description.
            top_k: Number of similar experiences to retrieve.

        Returns:
            List of dicts with situation, action, outcome, pnl, and score.
        """
        if self._index is None:
            return []

        embedding = await self._get_embedding(situation)

        try:
            results = await asyncio.to_thread(
                lambda: self._index.query(
                    vector=embedding,
                    top_k=top_k,
                    include_metadata=True,
                )
            )

            experiences = []
            for match in results.get("matches", []):
                meta = match.get("metadata", {})
                experiences.append({
                    "situation": meta.get("situation", ""),
                    "action": meta.get("action", ""),
                    "outcome": meta.get("outcome", ""),
                    "pnl": meta.get("pnl", 0),
                    "score": match.get("score", 0),
                })

            log.info(
                "rag_recall",
                results=len(experiences),
                top_score=experiences[0]["score"] if experiences else 0,
            )
            return experiences
        except Exception as e:
            log.error("pinecone_query_error", error=str(e))
            return []

    async def health_check(self) -> bool:
        """Check Pinecone connectivity."""
        if self._index is None:
            return False
        try:
            await asyncio.to_thread(
                lambda: self._index.describe_index_stats()
            )
            return True
        except Exception:
            return False
