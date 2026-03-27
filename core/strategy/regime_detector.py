"""
core/strategy/regime_detector.py
==================================
Market regime classification based on ADX value.

Three regimes:
  RANGING  — ADX < ADX_RANGING_MAX (20): mean reversion strategy is ACTIVE
  NEUTRAL  — 20 ≤ ADX ≤ 25: ambiguous zone, strategy runs with caution
  TRENDING — ADX > ADX_TRENDING_MIN (25): trend is strong, strategy PAUSED

The strategy engine only enters new positions when regime = RANGING.
"""

import math

from config.settings import ADX_RANGING_MAX, ADX_TRENDING_MIN

# Regime constants — used as string identifiers throughout the codebase
RANGING  = "RANGING"
NEUTRAL  = "NEUTRAL"
TRENDING = "TRENDING"


def classify_regime(adx_value: float) -> str:
    """
    Classify market regime from a single ADX reading.

    Returns:
        "RANGING"  if adx_value < ADX_RANGING_MAX  (strategy active)
        "NEUTRAL"  if ADX_RANGING_MAX <= adx_value <= ADX_TRENDING_MIN
        "TRENDING" if adx_value > ADX_TRENDING_MIN  (strategy paused)

    Edge cases:
        NaN input → NEUTRAL (conservative default when data is missing)
    """
    try:
        val = float(adx_value)
    except (TypeError, ValueError):
        return NEUTRAL   # treat bad data as ambiguous

    if math.isnan(val):
        return NEUTRAL   # NaN → ambiguous, default conservative

    if val < ADX_RANGING_MAX:
        return RANGING
    elif val <= ADX_TRENDING_MIN:
        return NEUTRAL
    else:
        return TRENDING


def is_tradeable_regime(regime: str) -> bool:
    """Return True only if the strategy should enter new positions."""
    return regime == RANGING
