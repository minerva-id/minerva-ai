"""
Minerva AI — Runtime configuration models.

Models for risk parameters, trading pair configuration, and agent runtime config.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RiskConfig(BaseModel):
    """Risk management configuration."""

    max_position_size_usd: float = Field(
        default=1000.0, ge=0,
        description="Maximum position size per token in USD",
    )
    max_total_exposure_usd: float = Field(
        default=5000.0, ge=0,
        description="Maximum total portfolio exposure in USD",
    )
    max_drawdown_percent: float = Field(
        default=10.0, ge=0, le=100,
        description="Maximum drawdown percentage before circuit breaker triggers",
    )
    daily_loss_limit_usd: float = Field(
        default=500.0, ge=0,
        description="Maximum daily loss in USD before halting trading",
    )
    token_whitelist: list[str] = Field(
        default_factory=lambda: ["BTC/USDT", "ETH/USDT"],
        description="Only trade these pairs",
    )
    max_open_positions: int = Field(
        default=5, ge=1,
        description="Maximum number of concurrent open positions",
    )
    min_signal_confidence: float = Field(
        default=0.6, ge=0.0, le=1.0,
        description="Minimum signal confidence to act on",
    )


class TradingPair(BaseModel):
    """Trading pair configuration."""

    symbol: str = Field(..., description="Trading pair, e.g. BTC/USDT")
    exchange: str = Field(default="binance")
    enabled: bool = True
    max_position_usd: float | None = None
    timeframes: list[str] = Field(
        default_factory=lambda: ["1m", "5m", "1h"],
    )


class AgentConfig(BaseModel):
    """Agent runtime configuration."""

    mode: str = Field(default="paper", pattern="^(paper|live)$")
    loop_interval_seconds: int = Field(default=60, ge=5, le=3600)
    fast_path_enabled: bool = True
    slow_path_enabled: bool = True
    rag_enabled: bool = True
    onchain_enabled: bool = False
    news_enabled: bool = False
    social_enabled: bool = False
    telegram_enabled: bool = False
    metrics_enabled: bool = False

    # Signal weights
    fast_path_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    slow_path_weight: float = Field(default=0.4, ge=0.0, le=1.0)

    # Fast path threshold for action
    buy_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    sell_threshold: float = Field(default=-0.3, ge=-1.0, le=0.0)
