"""
core/strategy/mean_reversion.py
=================================
USDINR Mean Reversion Signal Engine.

Signal flow:
  1. Called on every new 5-minute candle close (from market feed callback)
  2. Fetches latest N candles from SQLite
  3. Computes all indicators
  4. Runs entry / exit / filter logic → produces SignalEvent
  5. Stores signal candidate in SQLite (even if filtered out, for audit)
  6. Returns SignalEvent — caller (paper engine / live engine) acts on it

State machine:
  FLAT → LONG   (when LONG entry conditions met)
  FLAT → SHORT  (when SHORT entry conditions met)
  LONG → FLAT   (on exit conditions)
  SHORT → FLAT  (on exit conditions)

The strategy never re-enters while a position is already open.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import pandas as pd

from config.settings import (
    ATR_MULTIPLIER,
    ATR_STOP_MULTIPLIER,
    CANDLE_INTERVAL,
    IST,
    SQUARE_OFF_TIME,
    SYMBOL,
    TIME_EXIT_CANDLES,
    VOLUME_THRESHOLD,
    Z_ENTRY_THRESHOLD,
    Z_EXIT_THRESHOLD,
    Z_WINDOW,
)
from core.audit.database import get_connection, insert_signal
from core.audit.logger import get_logger
from core.data.historical import get_latest_candles
from core.data.market_feed import is_rbi_window
from core.strategy.indicators import adx, atr, rsi, zscore
from core.strategy.regime_detector import RANGING, classify_regime, is_tradeable_regime

log = get_logger("strategy")

# Candles needed: Z_WINDOW(20) for z-score + 14 for ADX + buffer
_MIN_CANDLES  = Z_WINDOW + 20   # 40 candles minimum
_CANDLE_FETCH = _MIN_CANDLES + 10   # fetch 50 to have buffer


# ── Signal data classes ────────────────────────────────────────────────────────

@dataclass
class SignalEvent:
    """
    Fully describes one signal evaluation cycle.
    Stored in SQLite for audit. Passed to Claude for validation.
    """
    timestamp:         datetime
    symbol:            str
    action:            str             # "LONG" | "SHORT" | "EXIT" | "SKIP"
    z_score:           float
    adx:               float
    rsi:               float
    atr:               float
    ltp:               float
    volume:            int
    regime:            str
    filters_passed:    List[str] = field(default_factory=list)
    filters_failed:    List[str] = field(default_factory=list)
    claude_confidence: int            = 0     # set by Claude layer (Phase 4)
    claude_reasoning:  str            = ""    # set by Claude layer (Phase 4)
    # ARIA extensions (optional — populated by ARIAStrategy, None for legacy signals)
    stop_price:        Optional[float] = None  # ATR-based stop for execution layer
    target_price:      Optional[float] = None  # ATR-based target (TRENDING mode)
    strategy_mode:     str             = ""    # "TRENDING_ORB" | "RANGING_ZSCORE" | ""
    orb_high:          Optional[float] = None  # for Claude prompt context
    orb_low:           Optional[float] = None  # for Claude prompt context

    def is_entry(self) -> bool:
        return self.action in ("LONG", "SHORT")

    def is_exit(self) -> bool:
        return self.action == "EXIT"

    def is_actionable(self) -> bool:
        """True if the signal should be forwarded to the execution layer."""
        return self.action in ("LONG", "SHORT", "EXIT")

    def to_dict(self) -> dict:
        return {
            "timestamp":         self.timestamp.isoformat(),
            "symbol":            self.symbol,
            "action":            self.action,
            "z_score":           round(self.z_score, 4),
            "adx":               round(self.adx,     4),
            "rsi":               round(self.rsi,     2),
            "atr":               round(self.atr,     4),
            "ltp":               round(self.ltp,     4),
            "volume":            self.volume,
            "regime":            self.regime,
            "filters_passed":    ",".join(self.filters_passed),
            "filters_failed":    ",".join(self.filters_failed),
            "claude_confidence": self.claude_confidence,
            "claude_reasoning":  self.claude_reasoning,
            "stop_price":        round(self.stop_price,   4) if self.stop_price   else None,
            "target_price":      round(self.target_price, 4) if self.target_price else None,
            "strategy_mode":     self.strategy_mode,
            "orb_high":          round(self.orb_high, 4) if self.orb_high else None,
            "orb_low":           round(self.orb_low,  4) if self.orb_low  else None,
        }


# ── Position state ─────────────────────────────────────────────────────────────

class _PositionState:
    """
    Tracks the current open position for the signal engine.
    Updated by the execution layer — the strategy reads this to suppress re-entry.
    """
    def __init__(self):
        self.side:            Optional[str]      = None   # "LONG" | "SHORT" | None
        self.open_candle_idx: Optional[int]      = 0      # absolute candle counter when position opened
        self.entry_price:     Optional[float]    = None

    def open(self, side: str, candle_idx: int, price: float) -> None:
        self.side            = side
        self.open_candle_idx = candle_idx
        self.entry_price     = price

    def close(self) -> None:
        self.side            = None
        self.open_candle_idx = None
        self.entry_price     = None

    @property
    def is_open(self) -> bool:
        return self.side is not None

    def candles_open(self, current_idx: int) -> int:
        if self.open_candle_idx is None:
            return 0
        return current_idx - self.open_candle_idx


# ── Strategy engine ────────────────────────────────────────────────────────────

class MeanReversionStrategy:
    """
    Mean Reversion Strategy Engine.

    Usage:
        strategy = MeanReversionStrategy()
        strategy.on_position_open("LONG", entry_price=84.25)   # called by paper/live engine
        strategy.on_position_close()                            # called by paper/live engine
        signal = strategy.evaluate()                            # call on each candle close
    """

    def __init__(self):
        self._position      = _PositionState()
        self._candle_count  = 0   # monotonic counter for time-exit
        self._last_signal:  Optional[SignalEvent] = None

    # ── Position state updates (called by execution layer) ────────────────────

    def on_position_open(self, side: str, entry_price: float) -> None:
        """Call when the execution layer successfully opens a position."""
        self._position.open(side, self._candle_count, entry_price)
        log.info(f"Position opened | side={side} entry={entry_price:.4f}")

    def on_position_close(self) -> None:
        """Call when the execution layer closes the position."""
        log.info(f"Position closed | was {self._position.side}")
        self._position.close()

    # ── Main evaluation ───────────────────────────────────────────────────────

    def evaluate(self, ltp: float = 0.0, volume: int = 0) -> Optional[SignalEvent]:
        """
        Evaluate strategy conditions and return a SignalEvent.

        Called on each 5-minute candle close.
        - ltp: current last traded price (from tick feed)
        - volume: current day's cumulative volume (from tick feed)

        Returns SignalEvent or None if not enough data to evaluate.
        """
        self._candle_count += 1

        # ── Fetch candles and compute indicators ──────────────────────────────
        df = get_latest_candles(n=_CANDLE_FETCH, interval=CANDLE_INTERVAL)

        if len(df) < _MIN_CANDLES:
            log.warning(
                f"Insufficient candles: {len(df)} < {_MIN_CANDLES}. "
                "Waiting for more data."
            )
            return None

        close  = df["close"]
        high   = df["high"]
        low    = df["low"]
        volume_series = df["volume"]

        # Compute indicators (all return Series)
        z_series   = zscore(close, window=Z_WINDOW)
        adx_series = adx(high, low, close, period=14)
        rsi_series = rsi(close, period=14)
        atr_series = atr(high, low, close, period=10)

        # Latest values
        z_val   = float(z_series.iloc[-1])
        adx_val = float(adx_series.iloc[-1])
        rsi_val = float(rsi_series.iloc[-1])
        atr_val = float(atr_series.iloc[-1])

        # Use LTP from tick feed if provided, else use last close
        price = ltp if ltp > 0 else float(close.iloc[-1])
        # Use cumulative volume from tick feed if provided, else sum last candle
        vol   = volume if volume > 0 else int(volume_series.iloc[-1])

        regime = classify_regime(adx_val)
        ts     = datetime.now(IST)

        log.info(
            f"Strategy tick | Z={z_val:+.3f} ADX={adx_val:.1f} "
            f"RSI={rsi_val:.1f} ATR={atr_val:.4f} "
            f"Regime={regime} LTP={price:.4f}"
        )

        # ── Check for exit signals first (exits fire even if indicators are NaN)
        if self._position.is_open:
            signal = self._check_exit(ts, z_val, adx_val, rsi_val, atr_val, price, vol, regime)
            if signal:
                self._store_signal(signal)
                self._last_signal = signal
                return signal

        # ── Block entries if any critical indicator is NaN ─────────────────────
        if any(math.isnan(v) for v in [z_val, adx_val, rsi_val, atr_val]):
            log.warning("NaN in indicators — entry signals blocked")
            return None

        # ── Check for entry signals (only when FLAT) ───────────────────────────
        if not self._position.is_open:
            signal = self._check_entry(
                ts, df, z_val, adx_val, rsi_val, atr_val, atr_series,
                volume_series, price, vol, regime
            )
            if signal:
                self._store_signal(signal)
                self._last_signal = signal
                return signal

        return None

    # ── Exit logic ─────────────────────────────────────────────────────────────

    def _check_exit(
        self,
        ts: datetime,
        z_val: float, adx_val: float, rsi_val: float, atr_val: float,
        price: float, vol: int, regime: str,
    ) -> Optional[SignalEvent]:
        """Check if the open position should be exited."""
        passed = []
        failed = []

        # 1. Z-score reversion exit
        z_reverted = abs(z_val) < Z_EXIT_THRESHOLD
        if z_reverted:
            passed.append("z_exit")
        else:
            failed.append("z_exit")

        # 2. ATR-based stop-loss (1.5 × ATR adverse move)
        stop_hit = False
        if self._position.entry_price is not None and not math.isnan(atr_val) and atr_val > 0:
            stop_distance = ATR_STOP_MULTIPLIER * atr_val
            if self._position.side == "LONG":
                stop_hit = price <= self._position.entry_price - stop_distance
            else:
                stop_hit = price >= self._position.entry_price + stop_distance
        if stop_hit:
            passed.append("stop_loss")
            log.info(
                f"Stop-loss triggered | entry={self._position.entry_price:.4f} "
                f"price={price:.4f} atr={atr_val:.4f} side={self._position.side}"
            )

        # 3. Time-based exit (60 minutes = 12 candles)
        candles_open = self._position.candles_open(self._candle_count)
        time_exit    = candles_open >= TIME_EXIT_CANDLES
        if time_exit:
            passed.append("time_exit")
            log.info(f"Time exit triggered | open for {candles_open} candles")

        # 4. EOD square-off
        eod_exit = ts.time() >= SQUARE_OFF_TIME
        if eod_exit:
            passed.append("eod_exit")
            log.info("EOD square-off triggered | 15:15 IST reached")

        if z_reverted or stop_hit or time_exit or eod_exit:
            return SignalEvent(
                timestamp=ts, symbol=SYMBOL, action="EXIT",
                z_score=z_val, adx=adx_val, rsi=rsi_val, atr=atr_val,
                ltp=price, volume=vol, regime=regime,
                filters_passed=passed, filters_failed=failed,
            )
        return None

    # ── Entry logic ────────────────────────────────────────────────────────────

    def _check_entry(
        self,
        ts: datetime,
        df: pd.DataFrame,
        z_val: float, adx_val: float, rsi_val: float, atr_val: float,
        atr_series: "pd.Series",
        volume_series: "pd.Series",
        price: float, vol: int, regime: str,
    ) -> Optional[SignalEvent]:
        """
        Run all 6 entry filters and return a LONG/SHORT/SKIP SignalEvent.
        All filters must pass for a LONG or SHORT to be emitted.
        """
        passed = []
        failed = []

        # ── Filter 1: Z-score threshold ────────────────────────────────────────
        is_long  = z_val < -Z_ENTRY_THRESHOLD
        is_short = z_val >  Z_ENTRY_THRESHOLD
        if is_long or is_short:
            passed.append("z_score")
        else:
            failed.append("z_score")

        # ── Filter 2: EMA trend direction (trade only with the macro trend) ────
        # LONG allowed only when price > EMA (buying dips in uptrend)
        # SHORT allowed only when price < EMA (selling bounces in downtrend)
        ema_series = ema(close, span=EMA_TREND_SPAN)
        ema_val    = float(ema_series.iloc[-1])
        if (is_long and price >= ema_val) or (is_short and price <= ema_val):
            passed.append("trend")
        else:
            failed.append("trend")

        # ── Filter 3: Regime = RANGING ─────────────────────────────────────────
        if is_tradeable_regime(regime):
            passed.append("regime")
        else:
            failed.append("regime")

        # ── Filter 4: NOT in RBI window ────────────────────────────────────────
        if not is_rbi_window():
            passed.append("rbi_window")
        else:
            failed.append("rbi_window")

        # ── Filter 5: ATR < ATR_MULTIPLIER × rolling mean ATR ─────────────────
        # Use last 10 candles of ATR for the rolling mean
        atr_mean = float(atr_series.tail(10).mean())
        atr_ok   = atr_val <= ATR_MULTIPLIER * atr_mean if atr_mean > 0 else True
        if atr_ok:
            passed.append("atr")
        else:
            failed.append("atr")

        # ── Filter 6: Volume > 50% of 5-candle average ────────────────────────
        vol_mean   = float(volume_series.tail(5).mean())
        current_vol = int(volume_series.iloc[-1])
        vol_ok     = current_vol >= VOLUME_THRESHOLD * vol_mean if vol_mean > 0 else True
        if vol_ok:
            passed.append("volume")
        else:
            failed.append("volume")

        # ── Determine action ───────────────────────────────────────────────────
        all_pass = len(failed) == 0

        if not (is_long or is_short):
            # No threshold crossed — nothing to emit
            return None

        action = "LONG" if is_long else "SHORT"

        if not all_pass:
            # Threshold crossed but filters blocked — emit SKIP for audit
            log.info(
                f"Signal SKIP | action={action} Z={z_val:+.3f} | "
                f"passed={passed} failed={failed}"
            )
            return SignalEvent(
                timestamp=ts, symbol=SYMBOL, action="SKIP",
                z_score=z_val, adx=adx_val, rsi=rsi_val, atr=atr_val,
                ltp=price, volume=vol, regime=regime,
                filters_passed=passed, filters_failed=failed,
            )

        log.info(
            f"Signal {action} | Z={z_val:+.3f} ADX={adx_val:.1f} "
            f"RSI={rsi_val:.1f} ATR={atr_val:.4f} LTP={price:.4f} | "
            f"all filters passed"
        )
        return SignalEvent(
            timestamp=ts, symbol=SYMBOL, action=action,
            z_score=z_val, adx=adx_val, rsi=rsi_val, atr=atr_val,
            ltp=price, volume=vol, regime=regime,
            filters_passed=passed, filters_failed=failed,
        )

    # ── Persistence ────────────────────────────────────────────────────────────

    def _store_signal(self, signal: SignalEvent) -> None:
        """Write signal to SQLite signals table for audit trail."""
        try:
            insert_signal(
                symbol=signal.symbol,
                action=signal.action,
                z_score=signal.z_score,
                adx=signal.adx,
                rsi=signal.rsi,
                atr=signal.atr,
                ltp=signal.ltp,
                volume=signal.volume,
                regime=signal.regime,
                filters_passed=signal.filters_passed,
                filters_failed=signal.filters_failed,
            )
        except Exception as exc:
            log.warning(f"Failed to store signal: {exc}")

    # ── Read-only accessors ────────────────────────────────────────────────────

    @property
    def position_side(self) -> Optional[str]:
        return self._position.side

    @property
    def last_signal(self) -> Optional[SignalEvent]:
        return self._last_signal
