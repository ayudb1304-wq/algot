"""
core/strategy/indicators.py
============================
Technical indicators for the USDINR mean reversion strategy.

All functions:
  - Accept pandas Series (or DataFrame columns where needed)
  - Return pandas Series of the same length (NaN where not enough data)
  - Are pure functions — no side effects, no state

Indicators used:
  zscore  — rolling Z-score (entry/exit signal)
  ema     — exponential moving average (trend context)
  rsi     — relative strength index (momentum filter)
  adx     — average directional index (regime filter)
  atr     — average true range (volatility filter)
"""

import numpy as np
import pandas as pd


# ── Z-score ───────────────────────────────────────────────────────────────────

def zscore(series: pd.Series, window: int = 20) -> pd.Series:
    """
    Rolling Z-score: (price - rolling_mean) / rolling_std.

    Returns NaN for the first `window-1` rows (insufficient data).
    Handles zero-std windows by returning 0.0 (flat price series).
    """
    roll   = series.rolling(window=window, min_periods=window)
    mean_  = roll.mean()
    std_   = roll.std(ddof=1)
    z = (series - mean_) / std_
    # std=0 produces NaN (0/0); replace with 0.0 (price exactly at mean)
    z = z.fillna(0.0)
    # Restore leading NaN where rolling window wasn't full (mean_ is NaN there)
    z[mean_.isna()] = np.nan
    return z


# ── EMA ───────────────────────────────────────────────────────────────────────

def ema(series: pd.Series, span: int) -> pd.Series:
    """
    Exponential moving average.
    Uses adjust=False (standard exponential decay) with min_periods=span.
    """
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


# ── RSI ───────────────────────────────────────────────────────────────────────

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Wilder's RSI (0-100).
    Uses Wilder's smoothing (equivalent to EWM with alpha=1/period).
    Returns NaN for first `period` rows.
    """
    delta   = series.diff()
    gain    = delta.clip(lower=0)
    loss    = (-delta).clip(lower=0)

    # Wilder's smoothing: alpha = 1/period, adjust=False
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi_ = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss is 0 (pure up-move), RSI = 100
    rsi_ = rsi_.where(avg_loss != 0, 100.0)
    return rsi_


# ── ADX ───────────────────────────────────────────────────────────────────────

def adx(
    high:   pd.Series,
    low:    pd.Series,
    close:  pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    Wilder's Average Directional Index (0-100).
    Higher = stronger trend. Below 20 = ranging. Above 25 = trending.
    Returns NaN for first 2*period rows (needs period for DM smoothing + period for ADX smoothing).
    """
    # True Range
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    # Directional Movement
    up_move   = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm  = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    # Wilder smoothing
    atr_w      = tr.ewm(      alpha=1.0 / period, adjust=False, min_periods=period).mean()
    plus_dm_s  = plus_dm.ewm( alpha=1.0 / period, adjust=False, min_periods=period).mean()
    minus_dm_s = minus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    # Directional Indicators
    plus_di  = 100.0 * plus_dm_s  / atr_w.replace(0, np.nan)
    minus_di = 100.0 * minus_dm_s / atr_w.replace(0, np.nan)

    # DX and ADX
    dx  = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_ = dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    return adx_


# ── ATR ───────────────────────────────────────────────────────────────────────

def atr(
    high:   pd.Series,
    low:    pd.Series,
    close:  pd.Series,
    period: int = 10,
) -> pd.Series:
    """
    Average True Range — Wilder's smoothing.
    Used as a volatility filter: if current ATR > 1.5× average ATR, skip entry.
    """
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
