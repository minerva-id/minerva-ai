"""
Minerva AI — Decision Engine.

Aggregates fast path signals and slow path LLM decisions into
final trading actions. Implements idempotency to prevent
redundant order spam.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from minerva.logger import get_logger
from minerva.models.signals import (
    AggregatedSignal,
    LLMDecision,
    SignalScore,
    TradeAction,
)

log = get_logger(__name__)


class DecisionEngine:
    """
    Central decision aggregation engine.

    Combines fast path (technical/ML) signals with slow path (LLM)
    decisions using configurable weights. Implements idempotency
    to only act on changed decisions.
    """

    def __init__(
        self,
        fast_weight: float = 0.6,
        slow_weight: float = 0.4,
        buy_threshold: float = 0.3,
        sell_threshold: float = -0.3,
        min_confidence: float = 0.5,
    ) -> None:
        """
        Initialize decision engine.

        Args:
            fast_weight: Weight for fast path signals (0-1).
            slow_weight: Weight for slow path signals (0-1).
            buy_threshold: Minimum combined score to trigger buy.
            sell_threshold: Maximum combined score to trigger sell.
            min_confidence: Minimum confidence to act on a signal.
        """
        self._fast_weight = fast_weight
        self._slow_weight = slow_weight
        self._buy_threshold = buy_threshold
        self._sell_threshold = sell_threshold
        self._min_confidence = min_confidence

        # Track last decisions for idempotency
        self._last_decisions: dict[str, AggregatedSignal] = {}

    def make_decision(
        self,
        symbol: str,
        fast_signal: SignalScore | None,
        llm_decision: LLMDecision | None,
        sentiment_score: float = 0.0,
        onchain_score: float = 0.0,
        has_open_position: bool = False,
    ) -> AggregatedSignal | None:
        """
        Make a final trading decision by aggregating all signals.

        Args:
            symbol: Trading pair.
            fast_signal: Fast path signal score.
            llm_decision: LLM slow path decision.
            sentiment_score: News/social sentiment score.
            onchain_score: On-chain activity score.
            has_open_position: Whether there's an existing position.

        Returns:
            AggregatedSignal if a new action should be taken, None if HOLD
            or no change from previous decision.
        """
        # Compute combined score
        fast_score = fast_signal.score if fast_signal else 0.0
        fast_confidence = fast_signal.confidence if fast_signal else 0.0

        slow_score: float | None = None
        slow_confidence = 0.0
        position_size_pct = 0.0
        stop_loss = None
        take_profit = None
        reasoning = ""

        if llm_decision:
            # Convert LLM action to score
            action_score_map = {
                TradeAction.BUY: 1.0,
                TradeAction.SELL: -1.0,
                TradeAction.HOLD: 0.0,
                TradeAction.CLOSE: -0.5 if has_open_position else 0.0,
            }
            slow_score = action_score_map.get(llm_decision.action, 0.0)
            slow_score *= llm_decision.confidence
            slow_confidence = llm_decision.confidence
            position_size_pct = llm_decision.position_size_pct
            stop_loss = llm_decision.stop_loss
            take_profit = llm_decision.take_profit
            reasoning = llm_decision.reasoning

        # Weighted combination
        if slow_score is not None:
            combined = (
                fast_score * self._fast_weight +
                slow_score * self._slow_weight
            )
            combined_confidence = (
                fast_confidence * self._fast_weight +
                slow_confidence * self._slow_weight
            )
        else:
            # Only fast path available
            combined = fast_score
            combined_confidence = fast_confidence

        # Add sentiment/onchain influence (small weight)
        combined += sentiment_score * 0.05
        combined += onchain_score * 0.05

        # Clamp
        combined = max(-1.0, min(1.0, combined))

        # Determine action
        if llm_decision and llm_decision.action == TradeAction.CLOSE:
            action = TradeAction.CLOSE
        elif combined >= self._buy_threshold:
            action = TradeAction.BUY
        elif combined <= self._sell_threshold:
            action = TradeAction.SELL
        else:
            action = TradeAction.HOLD

        # Build aggregated signal
        signal = AggregatedSignal(
            symbol=symbol,
            action=action,
            fast_score=fast_score,
            slow_score=slow_score,
            combined_score=round(combined, 4),
            confidence=round(min(1.0, combined_confidence), 4),
            position_size_pct=position_size_pct,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reasoning=reasoning,
            timestamp=datetime.now(tz=timezone.utc),
            technical_signals=fast_signal.metadata if fast_signal else {},
            sentiment_score=sentiment_score,
            on_chain_score=onchain_score,
        )

        # Idempotency check: only return if decision changed
        if not self._is_new_decision(symbol, signal):
            return None

        self._last_decisions[symbol] = signal

        # Filter low confidence signals
        if action != TradeAction.HOLD and combined_confidence < self._min_confidence:
            log.info(
                "decision_low_confidence",
                symbol=symbol,
                action=action.value,
                confidence=combined_confidence,
                threshold=self._min_confidence,
            )
            return None

        log.info(
            "decision_made",
            symbol=symbol,
            action=action.value,
            score=combined,
            confidence=combined_confidence,
            fast=fast_score,
            slow=slow_score,
        )

        return signal

    def _is_new_decision(self, symbol: str, signal: AggregatedSignal) -> bool:
        """Check if this decision is different from the last one."""
        last = self._last_decisions.get(symbol)
        if last is None:
            return True

        # Same action means no new decision (idempotent)
        if last.action == signal.action:
            # Unless confidence changed significantly
            if abs(last.confidence - signal.confidence) < 0.15:
                return False

        return True

    def get_last_decision(self, symbol: str) -> AggregatedSignal | None:
        """Get the last decision for a symbol."""
        return self._last_decisions.get(symbol)

    def clear_decision(self, symbol: str) -> None:
        """Clear the last decision for a symbol (e.g., after position closed)."""
        self._last_decisions.pop(symbol, None)
