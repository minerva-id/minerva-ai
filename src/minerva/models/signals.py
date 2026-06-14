"""
Minerva AI — Signal and decision models.

Models for fast path signals, LLM decisions, and aggregated trading signals.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class TradeAction(str, Enum):
    """Possible trading actions."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"


class SignalSource(str, Enum):
    """Source of a trading signal."""
    TECHNICAL = "technical"
    ML_MODEL = "ml_model"
    LLM = "llm"
    ON_CHAIN = "on_chain"
    SENTIMENT = "sentiment"
    COMBINED = "combined"


class SignalScore(BaseModel):
    """
    Signal score from fast path analysis.

    Score ranges from -1 (strong sell) to 1 (strong buy).
    """

    symbol: str
    source: SignalSource
    score: float = Field(..., ge=-1.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    timeframe: str = "1m"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    metadata: dict[str, float] = Field(default_factory=dict)


class LLMDecision(BaseModel):
    """
    Structured decision output from the LLM slow path.

    The LLM returns a JSON-structured decision with action,
    allocation, and risk parameters.
    """

    action: TradeAction
    symbol: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    position_size_pct: float = Field(
        default=0.0, ge=0.0, le=100.0,
        description="Position size as percentage of available capital",
    )
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    reasoning: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    raw_response: str = Field(default="", exclude=True)


class AggregatedSignal(BaseModel):
    """
    Combined signal from fast path + slow path.

    Used by the decision engine to make final trading decisions.
    """

    symbol: str
    action: TradeAction
    fast_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    slow_score: float | None = None
    combined_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    position_size_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    stop_loss: float | None = None
    take_profit: float | None = None
    reasoning: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Individual signal components
    technical_signals: dict[str, float] = Field(default_factory=dict)
    sentiment_score: float | None = None
    on_chain_score: float | None = None
