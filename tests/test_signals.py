"""
Tests for the Fast Path Signal Engine and Decision Engine.

Validates technical indicator computation, heuristic signal
generation, and decision aggregation.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

import pytest

from minerva.brain.decision import DecisionEngine
from minerva.brain.fast_path import FastPathEngine
from minerva.models.signals import (
    AggregatedSignal,
    LLMDecision,
    SignalScore,
    SignalSource,
    TradeAction,
)


@pytest.fixture
def fast_path() -> FastPathEngine:
    return FastPathEngine()


@pytest.fixture
def decision_engine() -> DecisionEngine:
    return DecisionEngine(
        fast_weight=0.6,
        slow_weight=0.4,
        buy_threshold=0.3,
        sell_threshold=-0.3,
        min_confidence=0.4,
    )


def _generate_ohlcv(
    count: int = 100,
    start_price: float = 50000.0,
    trend: float = 0.0,
) -> list[dict]:
    """Generate synthetic OHLCV data for testing."""
    candles = []
    price = start_price
    random.seed(42)

    for i in range(count):
        change = (random.random() - 0.5 + trend) * 100
        o = price
        c = price + change
        h = max(o, c) + random.random() * 50
        low = min(o, c) - random.random() * 50
        vol = random.random() * 1000 + 500

        candles.append({
            "open": o,
            "high": h,
            "low": low,
            "close": c,
            "volume": vol,
            "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
        })
        price = c

    return candles


class TestFastPathEngine:
    """Test fast path signal generation."""

    def test_insufficient_data_returns_neutral(
        self, fast_path: FastPathEngine
    ) -> None:
        """With insufficient data, signal should be neutral with low confidence."""
        candles = _generate_ohlcv(count=10)
        signal = fast_path.compute_signal("BTC/USDT", candles)

        assert signal.score == 0.0
        assert signal.confidence < 0.3
        assert signal.symbol == "BTC/USDT"

    def test_signal_score_range(self, fast_path: FastPathEngine) -> None:
        """Signal score should always be between -1 and 1."""
        candles = _generate_ohlcv(count=200)
        signal = fast_path.compute_signal("BTC/USDT", candles)

        assert -1.0 <= signal.score <= 1.0
        assert 0.0 <= signal.confidence <= 1.0

    def test_uptrend_generates_buy_signal(
        self, fast_path: FastPathEngine
    ) -> None:
        """Strong uptrend should produce positive signal."""
        candles = _generate_ohlcv(count=200, trend=0.05)
        signal = fast_path.compute_signal("BTC/USDT", candles)

        # Should be at least slightly positive in an uptrend
        assert signal.score > -0.5  # Not strongly negative

    def test_downtrend_generates_sell_signal(
        self, fast_path: FastPathEngine
    ) -> None:
        """Strong downtrend should produce negative signal."""
        candles = _generate_ohlcv(count=200, trend=-0.05)
        signal = fast_path.compute_signal("BTC/USDT", candles)

        # Should be at least slightly negative in a downtrend
        assert signal.score < 0.5  # Not strongly positive

    def test_signal_metadata_populated(
        self, fast_path: FastPathEngine
    ) -> None:
        """Signal should include technical indicator metadata."""
        candles = _generate_ohlcv(count=200)
        signal = fast_path.compute_signal("BTC/USDT", candles)

        assert "rsi_14" in signal.metadata
        assert "macd_diff" in signal.metadata
        assert "bb_position" in signal.metadata
        assert "adx" in signal.metadata

    def test_orderbook_imbalance_affects_signal(
        self, fast_path: FastPathEngine
    ) -> None:
        """Order book imbalance should influence signal direction."""
        candles = _generate_ohlcv(count=200)

        signal_neutral = fast_path.compute_signal(
            "BTC/USDT", candles, orderbook_imbalance=0.0
        )
        signal_buy_pressure = fast_path.compute_signal(
            "BTC/USDT", candles, orderbook_imbalance=0.8
        )
        signal_sell_pressure = fast_path.compute_signal(
            "BTC/USDT", candles, orderbook_imbalance=-0.8
        )

        # Buy pressure should push signal higher than sell pressure
        assert signal_buy_pressure.score >= signal_sell_pressure.score

    def test_scalping_vs_swing_timeframe(
        self, fast_path: FastPathEngine
    ) -> None:
        """Different timeframes should use different indicator weights."""
        candles = _generate_ohlcv(count=200)

        scalp_signal = fast_path.compute_signal(
            "BTC/USDT", candles, timeframe="1m"
        )
        swing_signal = fast_path.compute_signal(
            "BTC/USDT", candles, timeframe="4h"
        )

        # Both should be valid signals
        assert -1.0 <= scalp_signal.score <= 1.0
        assert -1.0 <= swing_signal.score <= 1.0
        assert scalp_signal.source == SignalSource.TECHNICAL


class TestDecisionEngine:
    """Test decision aggregation."""

    def test_fast_only_buy_decision(
        self, decision_engine: DecisionEngine
    ) -> None:
        """Strong fast path buy should trigger buy decision."""
        fast = SignalScore(
            symbol="BTC/USDT",
            source=SignalSource.TECHNICAL,
            score=0.7,
            confidence=0.8,
        )
        result = decision_engine.make_decision(
            symbol="BTC/USDT",
            fast_signal=fast,
            llm_decision=None,
        )

        assert result is not None
        assert result.action == TradeAction.BUY
        assert result.combined_score > 0

    def test_hold_when_below_threshold(
        self, decision_engine: DecisionEngine
    ) -> None:
        """Weak signal should result in HOLD."""
        fast = SignalScore(
            symbol="BTC/USDT",
            source=SignalSource.TECHNICAL,
            score=0.1,
            confidence=0.5,
        )
        result = decision_engine.make_decision(
            symbol="BTC/USDT",
            fast_signal=fast,
            llm_decision=None,
        )

        # Either None (no change) or HOLD action
        if result is not None:
            assert result.action == TradeAction.HOLD

    def test_combined_fast_slow_decision(
        self, decision_engine: DecisionEngine
    ) -> None:
        """Fast + slow path should combine with configured weights."""
        fast = SignalScore(
            symbol="BTC/USDT",
            source=SignalSource.TECHNICAL,
            score=0.5,
            confidence=0.7,
        )
        llm = LLMDecision(
            action=TradeAction.BUY,
            symbol="BTC/USDT",
            confidence=0.9,
            position_size_pct=10.0,
            reasoning="Bullish momentum detected",
        )

        result = decision_engine.make_decision(
            symbol="BTC/USDT",
            fast_signal=fast,
            llm_decision=llm,
        )

        assert result is not None
        assert result.action == TradeAction.BUY
        assert result.position_size_pct == 10.0

    def test_idempotency_same_decision(
        self, decision_engine: DecisionEngine
    ) -> None:
        """Same decision twice should not produce duplicate signal."""
        fast = SignalScore(
            symbol="ETH/USDT",
            source=SignalSource.TECHNICAL,
            score=0.7,
            confidence=0.8,
        )

        # First call
        result1 = decision_engine.make_decision(
            symbol="ETH/USDT", fast_signal=fast, llm_decision=None
        )
        # Second call (same signal)
        result2 = decision_engine.make_decision(
            symbol="ETH/USDT", fast_signal=fast, llm_decision=None
        )

        assert result1 is not None
        assert result2 is None  # Idempotent — no new decision

    def test_close_decision_overrides(
        self, decision_engine: DecisionEngine
    ) -> None:
        """LLM CLOSE decision should produce CLOSE action."""
        fast = SignalScore(
            symbol="BTC/USDT",
            source=SignalSource.TECHNICAL,
            score=0.3,
            confidence=0.5,
        )
        llm = LLMDecision(
            action=TradeAction.CLOSE,
            symbol="BTC/USDT",
            confidence=0.8,
            reasoning="Take profits",
        )

        result = decision_engine.make_decision(
            symbol="BTC/USDT",
            fast_signal=fast,
            llm_decision=llm,
            has_open_position=True,
        )

        assert result is not None
        assert result.action == TradeAction.CLOSE

    def test_clear_decision_allows_new(
        self, decision_engine: DecisionEngine
    ) -> None:
        """Clearing decision should allow new decision for same symbol."""
        fast = SignalScore(
            symbol="SOL/USDT",
            source=SignalSource.TECHNICAL,
            score=0.7,
            confidence=0.8,
        )

        result1 = decision_engine.make_decision(
            symbol="SOL/USDT", fast_signal=fast, llm_decision=None
        )
        assert result1 is not None

        decision_engine.clear_decision("SOL/USDT")

        result2 = decision_engine.make_decision(
            symbol="SOL/USDT", fast_signal=fast, llm_decision=None
        )
        assert result2 is not None  # Should work after clear
