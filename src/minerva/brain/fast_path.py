"""
Minerva AI — Fast Path Signal Engine.

Technical indicators and ML-based signal generation.
Runs locally with <10ms latency per tick.
Supports both heuristic rule-based signals (default) and
pre-trained ML models (LightGBM/ONNX when available).

Supports both scalping (1m/5m) and swing (1h/4h/1d) timeframes.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import ta

from minerva.logger import get_logger
from minerva.models.signals import SignalScore, SignalSource

log = get_logger(__name__)


class FastPathEngine:
    """
    Fast path signal generation engine.

    Computes technical indicators and generates trading signals
    with sub-10ms latency. Uses rule-based heuristics by default;
    can load pre-trained LightGBM or ONNX models if available.
    """

    # Signal weight configuration for different timeframes
    SCALPING_TIMEFRAMES = {"1m", "5m", "15m"}
    SWING_TIMEFRAMES = {"1h", "4h", "1d"}

    def __init__(self, model_dir: str | None = None) -> None:
        """
        Initialize fast path engine.

        Args:
            model_dir: Directory containing pre-trained model files.
                       If None, uses rule-based heuristics only.
        """
        self._model_dir = model_dir
        self._lgb_model: Any = None
        self._onnx_session: Any = None
        self._model_loaded = False

        if model_dir:
            self._load_models(model_dir)

    def _load_models(self, model_dir: str) -> None:
        """Attempt to load pre-trained models."""
        model_path = Path(model_dir)

        # Try LightGBM
        lgb_path = model_path / "signal_model.lgb"
        if lgb_path.exists():
            try:
                import lightgbm as lgb
                self._lgb_model = lgb.Booster(model_file=str(lgb_path))
                self._model_loaded = True
                log.info("lightgbm_model_loaded", path=str(lgb_path))
            except Exception as e:
                log.warning("lightgbm_load_failed", error=str(e))

        # Try ONNX
        onnx_path = model_path / "signal_model.onnx"
        if onnx_path.exists():
            try:
                import onnxruntime as ort
                self._onnx_session = ort.InferenceSession(
                    str(onnx_path),
                    providers=["CPUExecutionProvider"],
                )
                self._model_loaded = True
                log.info("onnx_model_loaded", path=str(onnx_path))
            except Exception as e:
                log.warning("onnx_load_failed", error=str(e))

        if not self._model_loaded:
            log.info("no_ml_models_found", message="Using heuristic signals only")

    def compute_signal(
        self,
        symbol: str,
        ohlcv_history: list[dict],
        orderbook_imbalance: float = 0.0,
        funding_rate: float | None = None,
        timeframe: str = "1m",
    ) -> SignalScore:
        """
        Compute trading signal for a symbol.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT").
            ohlcv_history: List of OHLCV dicts (most recent last).
            orderbook_imbalance: Order book imbalance ratio (-1 to 1).
            funding_rate: Current funding rate (if perpetual).
            timeframe: Candle timeframe.

        Returns:
            SignalScore with score from -1 (sell) to 1 (buy).
        """
        if len(ohlcv_history) < 30:
            return SignalScore(
                symbol=symbol,
                source=SignalSource.TECHNICAL,
                score=0.0,
                confidence=0.1,
                timeframe=timeframe,
                metadata={"data_points": float(len(ohlcv_history))},
            )

        # Build DataFrame from history
        df = self._build_dataframe(ohlcv_history)

        # Compute technical indicators
        indicators = self._compute_indicators(df)

        # Determine if scalping or swing mode
        is_scalping = timeframe in self.SCALPING_TIMEFRAMES

        # Generate signal
        if self._model_loaded:
            return self._ml_signal(symbol, indicators, orderbook_imbalance,
                                   funding_rate, timeframe, is_scalping)
        else:
            return self._heuristic_signal(symbol, indicators, orderbook_imbalance,
                                          funding_rate, timeframe, is_scalping)

    def _build_dataframe(self, ohlcv_history: list[dict]) -> pd.DataFrame:
        """Convert OHLCV history to pandas DataFrame."""
        df = pd.DataFrame(ohlcv_history)

        # Ensure required columns
        for col in ["open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                df[col] = 0.0
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

        return df

    def _compute_indicators(self, df: pd.DataFrame) -> dict[str, float]:
        """
        Compute technical indicators using the `ta` library.

        Returns dict of indicator name -> current value.
        """
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        indicators: dict[str, float] = {}

        # RSI (14-period)
        rsi = ta.momentum.RSIIndicator(close, window=14)
        rsi_val = rsi.rsi().iloc[-1]
        indicators["rsi_14"] = float(rsi_val) if not pd.isna(rsi_val) else 50.0

        # MACD
        macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        macd_diff = macd.macd_diff().iloc[-1]
        indicators["macd_diff"] = float(macd_diff) if not pd.isna(macd_diff) else 0.0
        macd_line = macd.macd().iloc[-1]
        indicators["macd_line"] = float(macd_line) if not pd.isna(macd_line) else 0.0

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        bb_mid = bb.bollinger_mavg().iloc[-1]
        current_price = close.iloc[-1]

        if not pd.isna(bb_upper) and not pd.isna(bb_lower) and bb_upper != bb_lower:
            bb_position = (current_price - bb_lower) / (bb_upper - bb_lower)
            indicators["bb_position"] = float(bb_position)
        else:
            indicators["bb_position"] = 0.5

        # EMA 9 / 21 crossover
        ema_9 = ta.trend.EMAIndicator(close, window=9).ema_indicator().iloc[-1]
        ema_21 = ta.trend.EMAIndicator(close, window=21).ema_indicator().iloc[-1]
        if not pd.isna(ema_9) and not pd.isna(ema_21) and ema_21 != 0:
            indicators["ema_cross"] = float((ema_9 - ema_21) / ema_21)
        else:
            indicators["ema_cross"] = 0.0

        # EMA 50 / 200 for swing trading
        if len(df) >= 200:
            ema_50 = ta.trend.EMAIndicator(close, window=50).ema_indicator().iloc[-1]
            ema_200 = ta.trend.EMAIndicator(close, window=200).ema_indicator().iloc[-1]
            if not pd.isna(ema_50) and not pd.isna(ema_200) and ema_200 != 0:
                indicators["ema_50_200"] = float((ema_50 - ema_200) / ema_200)
            else:
                indicators["ema_50_200"] = 0.0
        else:
            indicators["ema_50_200"] = 0.0

        # Stochastic RSI
        stoch_rsi = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)
        stoch_k = stoch_rsi.stochrsi_k().iloc[-1]
        indicators["stoch_rsi_k"] = float(stoch_k) if not pd.isna(stoch_k) else 0.5

        # ADX (trend strength)
        adx = ta.trend.ADXIndicator(high, low, close, window=14)
        adx_val = adx.adx().iloc[-1]
        indicators["adx"] = float(adx_val) if not pd.isna(adx_val) else 0.0

        # Volume change
        if len(volume) >= 20:
            vol_sma = volume.rolling(20).mean().iloc[-1]
            if not pd.isna(vol_sma) and vol_sma > 0:
                indicators["volume_ratio"] = float(volume.iloc[-1] / vol_sma)
            else:
                indicators["volume_ratio"] = 1.0
        else:
            indicators["volume_ratio"] = 1.0

        # ATR (Average True Range) for volatility
        atr = ta.volatility.AverageTrueRange(high, low, close, window=14)
        atr_val = atr.average_true_range().iloc[-1]
        indicators["atr"] = float(atr_val) if not pd.isna(atr_val) else 0.0

        # Price momentum (rate of change)
        if len(close) >= 10:
            roc = ((close.iloc[-1] - close.iloc[-10]) / close.iloc[-10]) * 100
            indicators["roc_10"] = float(roc) if not pd.isna(roc) else 0.0
        else:
            indicators["roc_10"] = 0.0

        return indicators

    def _heuristic_signal(
        self,
        symbol: str,
        indicators: dict[str, float],
        ob_imbalance: float,
        funding_rate: float | None,
        timeframe: str,
        is_scalping: bool,
    ) -> SignalScore:
        """
        Generate signal using rule-based heuristics.

        Combines multiple indicator signals with configurable weights.
        """
        signals: list[tuple[float, float]] = []  # (signal, weight)

        rsi = indicators["rsi_14"]
        macd_diff = indicators["macd_diff"]
        bb_pos = indicators["bb_position"]
        ema_cross = indicators["ema_cross"]
        stoch_rsi = indicators["stoch_rsi_k"]
        adx = indicators["adx"]
        volume_ratio = indicators["volume_ratio"]

        # --- RSI Signal ---
        if rsi < 30:
            rsi_signal = 0.8  # Oversold → buy
        elif rsi < 40:
            rsi_signal = 0.3
        elif rsi > 70:
            rsi_signal = -0.8  # Overbought → sell
        elif rsi > 60:
            rsi_signal = -0.3
        else:
            rsi_signal = 0.0
        signals.append((rsi_signal, 0.2))

        # --- MACD Signal ---
        if macd_diff > 0:
            macd_signal = min(macd_diff * 100, 1.0)  # Normalize
        else:
            macd_signal = max(macd_diff * 100, -1.0)
        signals.append((macd_signal, 0.2))

        # --- Bollinger Bands Signal ---
        if bb_pos < 0.1:
            bb_signal = 0.7  # Near lower band → buy
        elif bb_pos > 0.9:
            bb_signal = -0.7  # Near upper band → sell
        else:
            bb_signal = 0.0
        signals.append((bb_signal, 0.15))

        # --- EMA Crossover Signal ---
        if is_scalping:
            ema_signal = max(-1.0, min(1.0, ema_cross * 500))
            signals.append((ema_signal, 0.15))
        else:
            # Swing: use longer-term EMA
            ema_50_200 = indicators.get("ema_50_200", 0.0)
            ema_signal = max(-1.0, min(1.0, ema_50_200 * 200))
            signals.append((ema_signal, 0.2))

        # --- Stochastic RSI Signal ---
        if stoch_rsi < 0.2:
            stoch_signal = 0.6
        elif stoch_rsi > 0.8:
            stoch_signal = -0.6
        else:
            stoch_signal = 0.0
        signals.append((stoch_signal, 0.1))

        # --- Order Book Imbalance ---
        ob_signal = max(-1.0, min(1.0, ob_imbalance))
        signals.append((ob_signal, 0.1 if is_scalping else 0.05))

        # --- Funding Rate (contrarian) ---
        if funding_rate is not None:
            if funding_rate > 0.0005:
                fr_signal = -0.3  # High funding → potential short squeeze
            elif funding_rate < -0.0005:
                fr_signal = 0.3  # Negative funding → potential long squeeze
            else:
                fr_signal = 0.0
            signals.append((fr_signal, 0.1))

        # --- Compute weighted average ---
        total_weight = sum(w for _, w in signals)
        if total_weight > 0:
            score = sum(s * w for s, w in signals) / total_weight
        else:
            score = 0.0

        # Clamp to [-1, 1]
        score = max(-1.0, min(1.0, score))

        # --- Confidence based on trend strength (ADX) and volume ---
        confidence = 0.3  # Base confidence
        if adx > 25:
            confidence += 0.2  # Strong trend
        if adx > 40:
            confidence += 0.1  # Very strong trend
        if volume_ratio > 1.5:
            confidence += 0.15  # High volume confirms signal
        if abs(score) > 0.5:
            confidence += 0.1  # Strong signal

        confidence = min(1.0, confidence)

        return SignalScore(
            symbol=symbol,
            source=SignalSource.TECHNICAL,
            score=round(score, 4),
            confidence=round(confidence, 4),
            timeframe=timeframe,
            timestamp=datetime.now(tz=timezone.utc),
            metadata={
                "rsi_14": indicators["rsi_14"],
                "macd_diff": indicators["macd_diff"],
                "bb_position": indicators["bb_position"],
                "ema_cross": indicators["ema_cross"],
                "stoch_rsi_k": indicators["stoch_rsi_k"],
                "adx": indicators["adx"],
                "volume_ratio": indicators["volume_ratio"],
                "ob_imbalance": ob_imbalance,
            },
        )

    def _ml_signal(
        self,
        symbol: str,
        indicators: dict[str, float],
        ob_imbalance: float,
        funding_rate: float | None,
        timeframe: str,
        is_scalping: bool,
    ) -> SignalScore:
        """Generate signal using pre-trained ML model."""
        # Build feature vector
        features = np.array([[
            indicators["rsi_14"],
            indicators["macd_diff"],
            indicators["macd_line"],
            indicators["bb_position"],
            indicators["ema_cross"],
            indicators["stoch_rsi_k"],
            indicators["adx"],
            indicators["volume_ratio"],
            indicators["atr"],
            indicators["roc_10"],
            ob_imbalance,
            funding_rate or 0.0,
        ]])

        score = 0.0
        confidence = 0.5

        if self._lgb_model:
            try:
                prediction = self._lgb_model.predict(features)[0]
                # Assume model outputs value in [-1, 1] or probability
                score = float(max(-1.0, min(1.0, prediction)))
                confidence = 0.7  # ML model has higher base confidence
            except Exception as e:
                log.warning("lgb_prediction_error", error=str(e))
                return self._heuristic_signal(
                    symbol, indicators, ob_imbalance,
                    funding_rate, timeframe, is_scalping
                )

        elif self._onnx_session:
            try:
                input_name = self._onnx_session.get_inputs()[0].name
                result = self._onnx_session.run(
                    None, {input_name: features.astype(np.float32)}
                )
                score = float(max(-1.0, min(1.0, result[0][0])))
                confidence = 0.7
            except Exception as e:
                log.warning("onnx_prediction_error", error=str(e))
                return self._heuristic_signal(
                    symbol, indicators, ob_imbalance,
                    funding_rate, timeframe, is_scalping
                )

        return SignalScore(
            symbol=symbol,
            source=SignalSource.ML_MODEL,
            score=round(score, 4),
            confidence=round(confidence, 4),
            timeframe=timeframe,
            timestamp=datetime.now(tz=timezone.utc),
            metadata=indicators,
        )
