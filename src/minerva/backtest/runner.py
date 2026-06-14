"""
Minerva AI — Backtest Runner.

Historical backtesting engine that replays market data
through the signal engine and simulates trading.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from minerva.backtest.paper_trader import PaperTrader
from minerva.brain.fast_path import FastPathEngine
from minerva.logger import get_logger

log = get_logger(__name__)


class BacktestRunner:
    """
    Backtest engine for historical data replay.

    Downloads OHLCV data from exchanges and replays it
    through the fast path signal engine with paper trading.
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        fee_rate: float = 0.001,
    ) -> None:
        """
        Initialize backtest runner.

        Args:
            initial_balance: Starting balance for paper trading.
            fee_rate: Fee rate per trade.
        """
        self._initial_balance = initial_balance
        self._fee_rate = fee_rate
        self._fast_path = FastPathEngine()
        self._results: list[dict] = []

    async def fetch_historical_data(
        self,
        symbol: str,
        exchange_id: str = "binance",
        timeframe: str = "1h",
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data from exchange.

        Args:
            symbol: Trading pair.
            exchange_id: Exchange to fetch from.
            timeframe: Candle timeframe.
            limit: Number of candles.

        Returns:
            DataFrame with OHLCV columns.
        """
        import ccxt.async_support as ccxt_async

        exchange_class = getattr(ccxt_async, exchange_id)
        exchange = exchange_class({"enableRateLimit": True})

        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(
                ohlcv,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            return df
        finally:
            await exchange.close()

    async def run(
        self,
        symbol: str,
        data: pd.DataFrame,
        buy_threshold: float = 0.3,
        sell_threshold: float = -0.3,
        position_size_pct: float = 10.0,
        timeframe: str = "1h",
    ) -> dict:
        """
        Run backtest on historical data.

        Args:
            symbol: Trading pair.
            data: OHLCV DataFrame.
            buy_threshold: Signal score threshold for buy.
            sell_threshold: Signal score threshold for sell.
            position_size_pct: Position size as % of balance.
            timeframe: Candle timeframe.

        Returns:
            Backtest result summary dict.
        """
        paper = PaperTrader(
            initial_balance=self._initial_balance,
            fee_rate=self._fee_rate,
        )
        await paper.connect()

        trades: list[dict] = []
        signals: list[dict] = []
        position: dict | None = None
        window = 50  # Minimum candles for indicators

        log.info(
            "backtest_starting",
            symbol=symbol,
            candles=len(data),
            timeframe=timeframe,
        )

        for i in range(window, len(data)):
            # Build history window
            history_slice = data.iloc[max(0, i - 200) : i + 1]
            history = history_slice.to_dict("records")

            current_price = float(data.iloc[i]["close"])
            paper.set_price(symbol, current_price)

            # Generate signal
            signal = self._fast_path.compute_signal(
                symbol=symbol,
                ohlcv_history=history,
                timeframe=timeframe,
            )

            signals.append({
                "timestamp": str(data.iloc[i]["timestamp"]),
                "price": current_price,
                "score": signal.score,
                "confidence": signal.confidence,
            })

            # Trading logic
            from minerva.models.orders import Order, OrderSide, OrderType

            if position is None and signal.score >= buy_threshold:
                # Open long position
                balance = await paper.get_balance()
                amount_usd = balance * (position_size_pct / 100)
                amount = amount_usd / current_price

                if amount > 0:
                    order = Order(
                        symbol=symbol,
                        exchange="backtest",
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        price=current_price,
                        amount=amount,
                    )
                    fill = await paper.submit_order(order)
                    if fill:
                        position = {
                            "entry_price": current_price,
                            "amount": amount,
                            "entry_time": str(data.iloc[i]["timestamp"]),
                        }

            elif position is not None and signal.score <= sell_threshold:
                # Close position
                order = Order(
                    symbol=symbol,
                    exchange="backtest",
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    price=current_price,
                    amount=position["amount"],
                )
                fill = await paper.submit_order(order)
                if fill:
                    pnl = (current_price - position["entry_price"]) * position["amount"]
                    trades.append({
                        "entry_price": position["entry_price"],
                        "exit_price": current_price,
                        "amount": position["amount"],
                        "pnl": round(pnl, 4),
                        "entry_time": position["entry_time"],
                        "exit_time": str(data.iloc[i]["timestamp"]),
                    })
                    position = None

        # Close any remaining position
        if position is not None:
            final_price = float(data.iloc[-1]["close"])
            order = Order(
                symbol=symbol,
                exchange="backtest",
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                price=final_price,
                amount=position["amount"],
            )
            fill = await paper.submit_order(order)
            if fill:
                pnl = (final_price - position["entry_price"]) * position["amount"]
                trades.append({
                    "entry_price": position["entry_price"],
                    "exit_price": final_price,
                    "amount": position["amount"],
                    "pnl": round(pnl, 4),
                    "entry_time": position["entry_time"],
                    "exit_time": str(data.iloc[-1]["timestamp"]),
                })

        await paper.disconnect()

        # Compile results
        performance = paper.get_performance()
        winning = [t for t in trades if t["pnl"] >= 0]
        losing = [t for t in trades if t["pnl"] < 0]

        result = {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": len(data),
            "period_start": str(data.iloc[0]["timestamp"]),
            "period_end": str(data.iloc[-1]["timestamp"]),
            "total_trades": len(trades),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": (len(winning) / len(trades) * 100) if trades else 0,
            "total_pnl": performance["total_pnl"],
            "pnl_pct": performance["pnl_pct"],
            "total_fees": performance["total_fees"],
            "final_balance": performance["current_balance"],
            "avg_win": (
                sum(t["pnl"] for t in winning) / len(winning) if winning else 0
            ),
            "avg_loss": (
                sum(t["pnl"] for t in losing) / len(losing) if losing else 0
            ),
            "trades": trades,
        }

        log.info(
            "backtest_complete",
            symbol=symbol,
            trades=len(trades),
            pnl=performance["total_pnl"],
            win_rate=result["win_rate"],
        )

        return result
