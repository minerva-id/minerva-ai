"""
Tests for the Risk Engine.

Validates all risk rules: position limits, exposure caps,
circuit breaker, daily loss limit, and token whitelist.
"""

from __future__ import annotations

import pytest

from minerva.execution.risk_engine import RiskEngine, RiskViolation
from minerva.models.config import RiskConfig
from minerva.models.orders import Order, OrderSide, OrderType, Position


@pytest.fixture
def risk_config() -> RiskConfig:
    return RiskConfig(
        max_position_size_usd=1000.0,
        max_total_exposure_usd=5000.0,
        max_drawdown_percent=10.0,
        daily_loss_limit_usd=500.0,
        token_whitelist=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        max_open_positions=3,
    )


@pytest.fixture
def risk_engine(risk_config: RiskConfig) -> RiskEngine:
    engine = RiskEngine(risk_config)
    engine.set_initial_equity(10000.0)
    return engine


@pytest.fixture
def sample_order() -> Order:
    return Order(
        symbol="BTC/USDT",
        exchange="binance",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        amount=0.01,
    )


class TestRiskValidation:
    """Test pre-trade risk validation."""

    def test_valid_order_passes(
        self, risk_engine: RiskEngine, sample_order: Order
    ) -> None:
        """Valid order within all limits should have no violations."""
        violations = risk_engine.validate_order(
            order=sample_order,
            current_positions={},
            current_price=50000.0,
            available_balance=10000.0,
        )
        assert len(violations) == 0

    def test_exceeds_position_size(
        self, risk_engine: RiskEngine
    ) -> None:
        """Order exceeding max position size should be rejected."""
        order = Order(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=1.0,  # 1 BTC at $50k = $50,000
        )
        violations = risk_engine.validate_order(
            order=order,
            current_positions={},
            current_price=50000.0,
            available_balance=100000.0,
        )
        rules = [v.rule for v in violations]
        assert "MAX_POSITION_SIZE" in rules

    def test_exceeds_total_exposure(
        self, risk_engine: RiskEngine, sample_order: Order
    ) -> None:
        """Order causing total exposure to exceed limit should be rejected."""
        existing_positions = {
            "ETH/USDT": Position(
                symbol="ETH/USDT",
                exchange="binance",
                side=OrderSide.BUY,
                amount=2.0,
                entry_price=2500.0,
                current_price=2500.0,
            ),
        }
        # Existing: $5000, new order: ~$500 → total ~$5500 > $5000
        violations = risk_engine.validate_order(
            order=sample_order,
            current_positions=existing_positions,
            current_price=50000.0,
            available_balance=10000.0,
        )
        rules = [v.rule for v in violations]
        assert "MAX_EXPOSURE" in rules

    def test_token_not_whitelisted(
        self, risk_engine: RiskEngine
    ) -> None:
        """Order for non-whitelisted token should be rejected."""
        order = Order(
            symbol="DOGE/USDT",
            exchange="binance",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=100.0,
        )
        violations = risk_engine.validate_order(
            order=order,
            current_positions={},
            current_price=0.1,
            available_balance=10000.0,
        )
        rules = [v.rule for v in violations]
        assert "TOKEN_WHITELIST" in rules

    def test_max_positions_reached(
        self, risk_engine: RiskEngine, sample_order: Order
    ) -> None:
        """New position when max positions reached should be rejected."""
        existing = {
            f"TOKEN{i}/USDT": Position(
                symbol=f"TOKEN{i}/USDT",
                exchange="binance",
                side=OrderSide.BUY,
                amount=0.01,
                entry_price=100.0,
                current_price=100.0,
            )
            for i in range(3)
        }
        violations = risk_engine.validate_order(
            order=sample_order,
            current_positions=existing,
            current_price=50000.0,
            available_balance=10000.0,
        )
        rules = [v.rule for v in violations]
        assert "MAX_POSITIONS" in rules

    def test_insufficient_balance(
        self, risk_engine: RiskEngine, sample_order: Order
    ) -> None:
        """Buy order exceeding available balance should be rejected."""
        violations = risk_engine.validate_order(
            order=sample_order,
            current_positions={},
            current_price=50000.0,
            available_balance=100.0,  # Only $100
        )
        rules = [v.rule for v in violations]
        assert "INSUFFICIENT_BALANCE" in rules


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_circuit_breaker_triggers(
        self, risk_engine: RiskEngine
    ) -> None:
        """Circuit breaker should trigger at max drawdown."""
        # Starting equity: $10,000
        # Max drawdown: 10% → triggers at $1,000 loss
        risk_engine.update_pnl(-1100.0)  # > 10% drawdown
        assert risk_engine.is_trading_halted is True

    def test_circuit_breaker_blocks_orders(
        self, risk_engine: RiskEngine, sample_order: Order
    ) -> None:
        """No orders should pass when circuit breaker is open."""
        risk_engine.update_pnl(-1100.0)

        violations = risk_engine.validate_order(
            order=sample_order,
            current_positions={},
            current_price=50000.0,
            available_balance=10000.0,
        )
        rules = [v.rule for v in violations]
        assert "CIRCUIT_BREAKER" in rules

    def test_circuit_breaker_reset(
        self, risk_engine: RiskEngine
    ) -> None:
        """Circuit breaker should be resettable."""
        risk_engine.update_pnl(-1100.0)
        assert risk_engine.is_trading_halted is True

        risk_engine.reset_circuit_breaker()
        assert risk_engine.is_trading_halted is False

    def test_daily_pnl_tracking(
        self, risk_engine: RiskEngine
    ) -> None:
        """Daily PnL should be tracked correctly."""
        risk_engine.update_pnl(-200.0)
        risk_engine.update_pnl(-100.0)
        status = risk_engine.get_risk_status()
        assert status["daily_pnl"] == -300.0

    def test_risk_status_report(
        self, risk_engine: RiskEngine
    ) -> None:
        """Risk status should return complete information."""
        status = risk_engine.get_risk_status()
        assert "circuit_breaker_open" in status
        assert "daily_pnl" in status
        assert "current_equity" in status
        assert "peak_equity" in status
        assert "drawdown_pct" in status
