"""
Minerva AI — Backtest Runner.

Historical backtesting engine using vectorbt for blazing fast
vectorized portfolio simulation over historical data.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pandas as pd
import ta
import vectorbt as vbt

from minerva.logger import get_logger

log = get_logger(__name__)


class BacktestRunner:
    """
    Backtest engine for historical data replay.

    Downloads OHLCV data from exchanges and replays it
    using vectorbt for instant performance metrics.
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        fee_rate: float = 0.001,
    ) -> None:
        """
        Initialize backtest runner.

        Args:
            initial_balance: Starting balance.
            fee_rate: Fee rate per trade.
        """
        self._initial_balance = initial_balance
        self._fee_rate = fee_rate

    async def fetch_historical_data(
        self,
        symbol: str,
        exchange_id: str = "binance",
        timeframe: str = "1h",
        limit: int = 1000,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data from exchange."""
        import ccxt.async_support as ccxt_async

        # Handle DEX mapping if needed, or fallback to binance for backtest data
        if exchange_id == "hyperliquid":
            exchange_id = "binance"  # Use binance for historical data if hyperliquid isn't fully supported for fetch_ohlcv

        exchange_class = getattr(ccxt_async, exchange_id)
        exchange = exchange_class({"enableRateLimit": True})

        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(
                ohlcv,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)
            return df
        finally:
            await exchange.close()

    def _compute_vectorized_signals(self, df: pd.DataFrame) -> pd.Series:
        """
        Compute vectorized signal scores (-1 to 1) for the entire dataframe.
        Mimics FastPathEngine heuristic but vectorized.
        """
        close = df["close"]
        high = df["high"]
        low = df["low"]

        # 1. RSI
        rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
        rsi_score = pd.Series(0.0, index=df.index)
        rsi_score[rsi < 30] = 0.8
        rsi_score[(rsi >= 30) & (rsi < 40)] = 0.3
        rsi_score[rsi > 70] = -0.8
        rsi_score[(rsi <= 70) & (rsi > 60)] = -0.3

        # 2. MACD
        macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9).macd_diff()
        macd_score = macd.clip(-1.0, 1.0) # Simplified

        # 3. Bollinger Bands
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_pos = (close - bb.bollinger_lband()) / (bb.bollinger_hband() - bb.bollinger_lband())
        bb_score = pd.Series(0.0, index=df.index)
        bb_score[bb_pos < 0.1] = 0.7
        bb_score[bb_pos > 0.9] = -0.7

        # Weighting
        score = (rsi_score * 0.4) + (macd_score * 0.3) + (bb_score * 0.3)
        return score.clip(-1.0, 1.0)

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
        Run backtest on historical data using vectorbt.

        Args:
            symbol: Trading pair.
            data: OHLCV DataFrame indexed by timestamp.
            buy_threshold: Signal score threshold for buy.
            sell_threshold: Signal score threshold for sell.
            position_size_pct: Position size as % of balance.
            timeframe: Candle timeframe.

        Returns:
            Backtest result summary dict.
        """
        log.info(
            "vectorbt_backtest_starting",
            symbol=symbol,
            candles=len(data),
            timeframe=timeframe,
        )

        score = self._compute_vectorized_signals(data)

        entries = score >= buy_threshold
        exits = score <= sell_threshold

        # VectorBT Portfolio simulation
        pf = vbt.Portfolio.from_signals(
            data["close"],
            entries,
            exits,
            init_cash=self._initial_balance,
            fees=self._fee_rate,
            size=position_size_pct / 100, # Use size as percentage of equity
            size_type="percent",
            freq=timeframe,
        )

        # Compile professional metrics
        stats = pf.stats()
        
        result = {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": len(data),
            "period_start": str(data.index[0]),
            "period_end": str(data.index[-1]),
            "total_trades": int(stats.get("Total Closed Trades", 0)),
            "win_rate": float(stats.get("Win Rate [%]", 0)),
            "total_pnl": float(stats.get("Total Return [%]", 0)) / 100 * self._initial_balance,
            "pnl_pct": float(stats.get("Total Return [%]", 0)),
            "max_drawdown": float(stats.get("Max Drawdown [%]", 0)),
            "sharpe_ratio": float(stats.get("Sharpe Ratio", 0.0) if not pd.isna(stats.get("Sharpe Ratio", 0.0)) else 0.0),
            "final_balance": float(pf.value()[-1]),
        }

        log.info(
            "vectorbt_backtest_complete",
            symbol=symbol,
            trades=result["total_trades"],
            pnl=result["total_pnl"],
            win_rate=result["win_rate"],
        )

        return result
