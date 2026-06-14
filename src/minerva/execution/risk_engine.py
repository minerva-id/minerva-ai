"""
Minerva AI — Risk Engine.

Pre-trade risk validation and circuit breaker protection.
Enforces position limits, exposure caps, drawdown guards,
and daily loss limits before any order is submitted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from minerva.logger import get_logger
from minerva.models.config import RiskConfig
from minerva.models.orders import Order, OrderSide, Position

log = get_logger(__name__)


class RiskViolation:
    """Represents a risk rule violation."""

    def __init__(self, rule: str, message: str) -> None:
        self.rule = rule
        self.message = message

    def __str__(self) -> str:
        return f"[{self.rule}] {self.message}"


class RiskEngine:
    """
    Pre-trade risk validation engine.

    Validates all orders against risk rules before submission.
    Implements circuit breaker to halt trading on excessive losses.
    """

    def __init__(self, config: RiskConfig) -> None:
        """
        Initialize risk engine.

        Args:
            config: Risk management configuration.
        """
        self._config = config
        self._circuit_breaker_open = False
        self._daily_pnl = 0.0
        self._daily_reset_date: str = ""
        self._peak_equity = 0.0
        self._current_equity = 0.0

    @property
    def is_trading_halted(self) -> bool:
        """Check if trading is halted by circuit breaker."""
        return self._circuit_breaker_open

    def validate_order(
        self,
        order: Order,
        current_positions: dict[str, Position],
        current_price: float,
        available_balance: float,
    ) -> list[RiskViolation]:
        """
        Validate an order against all risk rules.

        Args:
            order: The order to validate.
            current_positions: Dict of symbol -> Position.
            current_price: Current price of the asset.
            available_balance: Available USD balance.

        Returns:
            List of violations. Empty list means order is approved.
        """
        violations: list[RiskViolation] = []

        # --- Circuit breaker check ---
        if self._circuit_breaker_open:
            violations.append(RiskViolation(
                "CIRCUIT_BREAKER",
                "Trading halted due to circuit breaker",
            ))
            return violations  # No point checking further

        # --- Reset daily PnL if new day ---
        self._check_daily_reset()

        # --- Token whitelist ---
        if order.symbol not in self._config.token_whitelist:
            violations.append(RiskViolation(
                "TOKEN_WHITELIST",
                f"{order.symbol} is not in the allowed token list: "
                f"{self._config.token_whitelist}",
            ))

        # --- Max position size ---
        order_value = order.amount * current_price
        if order_value > self._config.max_position_size_usd:
            violations.append(RiskViolation(
                "MAX_POSITION_SIZE",
                f"Order value ${order_value:,.2f} exceeds max "
                f"${self._config.max_position_size_usd:,.2f}",
            ))

        # --- Max total exposure ---
        total_exposure = sum(
            pos.notional_value for pos in current_positions.values()
        )
        new_total = total_exposure + order_value
        if new_total > self._config.max_total_exposure_usd:
            violations.append(RiskViolation(
                "MAX_EXPOSURE",
                f"Total exposure ${new_total:,.2f} would exceed max "
                f"${self._config.max_total_exposure_usd:,.2f}",
            ))

        # --- Max open positions ---
        if (
            order.symbol not in current_positions
            and len(current_positions) >= self._config.max_open_positions
        ):
            violations.append(RiskViolation(
                "MAX_POSITIONS",
                f"Already at max {self._config.max_open_positions} open positions",
            ))

        # --- Daily loss limit ---
        if self._daily_pnl <= -self._config.daily_loss_limit_usd:
            violations.append(RiskViolation(
                "DAILY_LOSS_LIMIT",
                f"Daily PnL ${self._daily_pnl:,.2f} has hit limit "
                f"-${self._config.daily_loss_limit_usd:,.2f}",
            ))

        # --- Insufficient balance ---
        if order.side == OrderSide.BUY and order_value > available_balance:
            violations.append(RiskViolation(
                "INSUFFICIENT_BALANCE",
                f"Order value ${order_value:,.2f} exceeds available "
                f"${available_balance:,.2f}",
            ))

        if violations:
            log.warning(
                "risk_violations",
                symbol=order.symbol,
                violations=[str(v) for v in violations],
            )
        else:
            log.info(
                "risk_approved",
                symbol=order.symbol,
                side=order.side.value,
                value=round(order_value, 2),
            )

        return violations

    def update_pnl(self, pnl: float) -> None:
        """
        Update daily PnL and check circuit breaker.

        Args:
            pnl: Realized PnL from a closed trade.
        """
        self._check_daily_reset()
        self._daily_pnl += pnl
        self._current_equity += pnl

        # Update peak equity
        if self._current_equity > self._peak_equity:
            self._peak_equity = self._current_equity

        # Check drawdown circuit breaker
        if self._peak_equity > 0:
            drawdown_pct = (
                (self._peak_equity - self._current_equity) / self._peak_equity
            ) * 100

            if drawdown_pct >= self._config.max_drawdown_percent:
                self._circuit_breaker_open = True
                log.error(
                    "circuit_breaker_triggered",
                    drawdown_pct=round(drawdown_pct, 2),
                    threshold=self._config.max_drawdown_percent,
                    peak_equity=round(self._peak_equity, 2),
                    current_equity=round(self._current_equity, 2),
                )

        # Check daily loss limit
        if self._daily_pnl <= -self._config.daily_loss_limit_usd:
            log.warning(
                "daily_loss_limit_reached",
                daily_pnl=round(self._daily_pnl, 2),
                limit=self._config.daily_loss_limit_usd,
            )

    def set_initial_equity(self, equity: float) -> None:
        """Set the initial equity for drawdown tracking."""
        self._current_equity = equity
        self._peak_equity = equity
        log.info("equity_initialized", equity=round(equity, 2))

    def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker."""
        self._circuit_breaker_open = False
        log.info("circuit_breaker_reset")

    def _check_daily_reset(self) -> None:
        """Reset daily PnL at the start of each UTC day."""
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        if today != self._daily_reset_date:
            if self._daily_reset_date:
                log.info(
                    "daily_pnl_reset",
                    previous_date=self._daily_reset_date,
                    previous_pnl=round(self._daily_pnl, 2),
                )
            self._daily_pnl = 0.0
            self._daily_reset_date = today

    def get_risk_status(self) -> dict[str, Any]:
        """Get current risk engine status."""
        drawdown_pct = 0.0
        if self._peak_equity > 0:
            drawdown_pct = (
                (self._peak_equity - self._current_equity) / self._peak_equity
            ) * 100

        return {
            "circuit_breaker_open": self._circuit_breaker_open,
            "daily_pnl": round(self._daily_pnl, 2),
            "daily_loss_limit": self._config.daily_loss_limit_usd,
            "current_equity": round(self._current_equity, 2),
            "peak_equity": round(self._peak_equity, 2),
            "drawdown_pct": round(drawdown_pct, 2),
            "max_drawdown_pct": self._config.max_drawdown_percent,
        }
