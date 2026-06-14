"""
Minerva AI — Market data models.

Pydantic models for OHLCV, order book, ticks, and funding rate data.
All data from exchanges is validated through these models.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TimeFrame(str, Enum):
    """Supported OHLCV timeframes."""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


class OHLCV(BaseModel):
    """Open-High-Low-Close-Volume candle data."""

    symbol: str = Field(..., description="Trading pair symbol, e.g. BTC/USDT")
    exchange: str = Field(..., description="Exchange name")
    timeframe: TimeFrame = Field(default=TimeFrame.M1)
    timestamp: datetime
    open: float = Field(..., ge=0)
    high: float = Field(..., ge=0)
    low: float = Field(..., ge=0)
    close: float = Field(..., ge=0)
    volume: float = Field(..., ge=0)

    @property
    def mid_price(self) -> float:
        return (self.high + self.low) / 2


class OrderBookLevel(BaseModel):
    """Single price level in an order book."""

    price: float = Field(..., ge=0)
    amount: float = Field(..., ge=0)


class OrderBookSnapshot(BaseModel):
    """Aggregated order book snapshot."""

    symbol: str
    exchange: str
    timestamp: datetime
    bids: list[OrderBookLevel] = Field(default_factory=list)
    asks: list[OrderBookLevel] = Field(default_factory=list)

    @property
    def best_bid(self) -> float | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> float | None:
        if self.best_bid is not None and self.best_ask is not None:
            return self.best_ask - self.best_bid
        return None

    @property
    def imbalance(self) -> float:
        """
        Order book imbalance ratio.

        Returns a value between -1 and 1 where:
        - Positive = more bid volume (buying pressure)
        - Negative = more ask volume (selling pressure)
        """
        bid_vol = sum(level.amount for level in self.bids[:10])
        ask_vol = sum(level.amount for level in self.asks[:10])
        total = bid_vol + ask_vol
        if total == 0:
            return 0.0
        return (bid_vol - ask_vol) / total


class TickData(BaseModel):
    """Real-time trade tick data."""

    symbol: str
    exchange: str
    timestamp: datetime
    price: float = Field(..., ge=0)
    amount: float = Field(..., ge=0)
    side: str = Field(..., pattern="^(buy|sell)$")
    trade_id: str = ""


class FundingRate(BaseModel):
    """Perpetual futures funding rate data."""

    symbol: str
    exchange: str
    timestamp: datetime
    funding_rate: float
    next_funding_time: datetime | None = None
    estimated_rate: float | None = None


class MarketSummary(BaseModel):
    """Aggregated market summary for a single pair."""

    symbol: str
    exchange: str
    timestamp: datetime
    last_price: float = 0.0
    price_change_24h_pct: float = 0.0
    volume_24h: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    spread_pct: float = 0.0
    order_book_imbalance: float = 0.0
    funding_rate: float | None = None
    rsi_14: float | None = None
    macd_signal: float | None = None
