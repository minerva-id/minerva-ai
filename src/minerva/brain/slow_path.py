"""
Minerva AI — LLM Slow Path Controller.

Meta-controller that uses LLM reasoning for high-level trading decisions.
Called periodically (1-5 min intervals), not per-tick.
Supports Groq (Llama 3 70B) and OpenAI (GPT-4o) with auto-fallback.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from openai import AsyncOpenAI

from minerva.brain.prompts import SYSTEM_PROMPT, LLM_TOOLS, format_market_context
from minerva.logger import get_logger
from minerva.models.signals import LLMDecision, TradeAction

log = get_logger(__name__)


class SlowPathController:
    """
    LLM-based meta-controller for strategic trading decisions.

    Uses LLM reasoning at configurable intervals (not per-tick)
    to make high-level allocation and entry/exit decisions.
    Falls back to fast path signals if LLM is unavailable or slow.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout: int = 5,
    ) -> None:
        """
        Initialize slow path controller.

        Args:
            api_key: LLM API key (Groq or OpenAI).
            model: Model name (e.g., "llama-3.3-70b-versatile" or "gpt-4o").
            base_url: API base URL (e.g., Groq endpoint).
            timeout: Request timeout in seconds.
        """
        self._model = model
        self._timeout = timeout
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=float(timeout),
        )
        self._last_call_time: datetime | None = None
        self._consecutive_failures = 0
        self._max_failures = 5  # Circuit breaker threshold

    @property
    def is_circuit_open(self) -> bool:
        """Check if circuit breaker is triggered."""
        return self._consecutive_failures >= self._max_failures

    async def analyze(
        self,
        symbol: str,
        market_summary: dict | None,
        signals: dict[str, float],
        sentiment_score: float,
        news_items: list[dict],
        onchain_events: list[dict],
        current_positions: list[dict],
        past_experiences: list[dict],
        user_principles: list[str],
        risk_config: dict,
    ) -> LLMDecision | None:
        """
        Get LLM trading decision for a symbol.

        Args:
            symbol: Trading pair to analyze.
            market_summary: Current market data summary.
            signals: Technical indicator scores from fast path.
            sentiment_score: Aggregated sentiment score.
            news_items: Recent news items.
            onchain_events: Recent on-chain events.
            current_positions: Currently open positions.
            past_experiences: Similar past situations from RAG.
            user_principles: User defined trading principles.
            risk_config: Risk management parameters.

        Returns:
            LLMDecision if successful, None if failed/timed out.
        """
        # Circuit breaker check
        if self.is_circuit_open:
            log.warning(
                "llm_circuit_open",
                failures=self._consecutive_failures,
                message="Falling back to fast path",
            )
            return None

        # Build prompt
        context = format_market_context(
            symbol=symbol,
            market_summary=market_summary,
            signals=signals,
            sentiment_score=sentiment_score,
            news_items=news_items,
            onchain_events=onchain_events,
            current_positions=current_positions,
            past_experiences=past_experiences,
            user_principles=user_principles,
            risk_config=risk_config,
        )

        try:
            response = await asyncio.wait_for(
                self._call_llm(context),
                timeout=self._timeout,
            )

            if response is None:
                self._consecutive_failures += 1
                return None

            decision = self._parse_decision(response, symbol)
            self._consecutive_failures = 0  # Reset on success
            self._last_call_time = datetime.now(tz=timezone.utc)

            log.info(
                "llm_decision",
                symbol=symbol,
                action=decision.action.value,
                confidence=decision.confidence,
            )

            return decision

        except asyncio.TimeoutError:
            self._consecutive_failures += 1
            log.warning(
                "llm_timeout",
                symbol=symbol,
                timeout=self._timeout,
                failures=self._consecutive_failures,
            )
            return None

        except Exception as e:
            self._consecutive_failures += 1
            log.error(
                "llm_error",
                symbol=symbol,
                error=str(e),
                failures=self._consecutive_failures,
            )
            return None

    async def _call_llm(self, context: str) -> str | None:
        """Make the actual LLM API call."""
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": context},
                ],
                temperature=0.1,  # Low temperature for consistent decisions
                max_tokens=500,
                tools=LLM_TOOLS,
                tool_choice={"type": "function", "function": {"name": "submit_trade_decision"}},
            )

            # Extract tool call arguments
            message = response.choices[0].message
            if message.tool_calls and len(message.tool_calls) > 0:
                return message.tool_calls[0].function.arguments
            
            # Fallback if model ignored tool_choice (rare but possible)
            return message.content

        except Exception as e:
            log.warning("llm_api_error", error=str(e))
            return None

    def _parse_decision(self, response: str, symbol: str) -> LLMDecision:
        """Parse LLM response into structured decision."""
        try:
            data = json.loads(response)

            # Validate and normalize action
            action_str = data.get("action", "hold").lower()
            action_map = {
                "buy": TradeAction.BUY,
                "sell": TradeAction.SELL,
                "hold": TradeAction.HOLD,
                "close": TradeAction.CLOSE,
            }
            action = action_map.get(action_str, TradeAction.HOLD)

            return LLMDecision(
                action=action,
                symbol=data.get("symbol", symbol),
                confidence=min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
                position_size_pct=min(100.0, max(0.0, float(data.get("position_size_pct", 0)))),
                entry_price=data.get("entry_price"),
                stop_loss=data.get("stop_loss"),
                take_profit=data.get("take_profit"),
                reasoning=data.get("reasoning", ""),
                raw_response=response,
            )

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            log.warning("llm_parse_error", error=str(e), response=response[:200])
            return LLMDecision(
                action=TradeAction.HOLD,
                symbol=symbol,
                confidence=0.1,
                reasoning=f"Failed to parse LLM response: {str(e)}",
                raw_response=response,
            )

    def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker."""
        self._consecutive_failures = 0
        log.info("llm_circuit_breaker_reset")
