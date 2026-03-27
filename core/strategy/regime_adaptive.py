"""
core/strategy/regime_adaptive.py
==================================
ARIA — Adaptive Regime Intraday Algo.

Regime-switching strategy for USDINR intraday trading (NSE CDS segment).

Calibration phase (9:00–10:00 AM IST):
  Builds Opening Range (ORB) from the first ORB_CANDLES × 15-min candles.
  Locks in the day's regime classification using ADX(14).

Entry window (10:00 AM – ENTRY_SESSION_END):
  TRENDING (ADX > ADX_TRENDING_MIN):
    LONG  if price > ORB_high + 0.5×ATR AND RSI > 50 AND EMA_fast > EMA_slow
    SHORT if price < ORB_low  − 0.5×ATR AND RSI < 50 AND EMA_fast < EMA_slow
    Macro gate: price > EMA(200) for LONG, price < EMA(200) for SHORT
    Stop:   entry ± ATR_STOP_MULTIPLIER × ATR(10)
    Target: entry ± ATR_TARGET_MULTIPLIER × ATR(10)   [2:1 R:R]

  RANGING (ADX < ADX_RANGING_MAX):
    LONG  if Z(96) < −Z_ENTRY_THRESHOLD
    SHORT if Z(96) > +Z_ENTRY_THRESHOLD
    Stop:   entry ± ATR_STOP_MULTIPLIER × ATR(10)
    Exit:   |Z| < Z_EXIT_THRESHOLD  OR  TIME_EXIT_CANDLES elapsed

  NEUTRAL (ADX_RANGING_MAX ≤ ADX ≤ ADX_TRENDING_MIN):
    No new positions today.

  Max MAX_DAILY_TRADES per session.

Exit management (any time, while position is open):
  stop_loss   — ATR-based stop hit
  target_hit  — ATR-based target hit (TRENDING mode only)
  z_revert    — |Z| < Z_EXIT_THRESHOLD (RANGING mode only)
  time_exit   — position open ≥ TIME_EXIT_CANDLES candles
  eod_exit    — SQUARE_OFF_TIME reached

evaluate(ltp, volume, ts=None):
  Pass ts=None in live trading (uses datetime.now(IST)).
  Pass ts=candle_timestamp in backtesting (enables accurate ORB window detection).
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import List, Optional
from unittest.mock import patch

import pandas as pd

from config.settings import (
    ADX_RANGING_MAX,
    ADX_TRENDING_MIN,
    ATR_STOP_MULTIPLIER,
    ATR_TARGET_MULTIPLIER,
    CANDLE_INTERVAL,
    CANDLE_MINUTES,
    EMA_DIRECTION_SPAN,
    EMA_FAST_SPAN,
    EMA_SLOW_SPAN,
    ENTRY_SESSION_END,
    IST,
    MAX_DAILY_TRADES,
    ORB_CANDLES,
    ORB_MIN_BREAKOUT_ATR,
    SQUARE_OFF_TIME,
    SYMBOL,
    TIME_EXIT_CANDLES,
    Z_ENTRY_THRESHOLD,
    Z_EXIT_THRESHOLD,
    Z_WINDOW,
)
from core.audit.database import insert_signal
from core.audit.logger import get_logger
from core.data.historical import get_latest_candles
from core.data.market_feed import is_rbi_window
from core.strategy.indicators import adx, atr, ema, rsi, zscore
from core.strategy.mean_reversion import SignalEvent
from core.strategy.regime_detector import (
    NEUTRAL,
    RANGING,
    TRENDING,
    classify_regime,
)

log = get_logger("aria")

# Need enough candles for the largest indicator span + warmup buffer.
# EMA_DIRECTION_SPAN(200) > Z_WINDOW(96), so EMA is the binding constraint.
_MIN_CANDLES  = max(Z_WINDOW, EMA_DIRECTION_SPAN) + 24  # 224 candles minimum
_CANDLE_FETCH = _MIN_CANDLES + 10                        # 234 fetched

# ORB window: 9:00 AM to (9:00 + ORB_CANDLES × CANDLE_MINUTES)
# e.g. 4 × 15-min = 60 min → ORB ends at 10:00 AM, entries start at 10:00 AM
_ORB_TOTAL_MINUTES  = ORB_CANDLES * CANDLE_MINUTES          # 60
_ORB_WINDOW_START   = time(9, 0)
_ORB_WINDOW_END     = time(
    (9 * 60 + _ORB_TOTAL_MINUTES) // 60,
    (9 * 60 + _ORB_TOTAL_MINUTES) % 60,
)                                                            # time(10, 0)
_ENTRY_WINDOW_START = _ORB_WINDOW_END                        # entries begin at 10:00 AM


# ── Opening Range state ────────────────────────────────────────────────────────

@dataclass
class ORBState:
    """
    Tracks the Opening Range for the current session.
    Accumulates high/low across the first ORB_CANDLES five-minute candles
    (9:00–9:15 AM), then locks in place for the rest of the day.
    """
    high:         Optional[float] = None
    low:          Optional[float] = None
    is_built:     bool            = False
    candles_seen: int             = 0

    def update(self, candle_high: float, candle_low: float) -> None:
        if self.is_built:
            return
        if self.high is None or candle_high > self.high:
            self.high = candle_high
        if self.low is None or candle_low < self.low:
            self.low = candle_low
        self.candles_seen += 1
        if self.candles_seen >= ORB_CANDLES:
            self.is_built = True

    def reset(self) -> None:
        self.high = None
        self.low  = None
        self.is_built = False
        self.candles_seen = 0

    @property
    def width(self) -> float:
        if self.high is None or self.low is None:
            return 0.0
        return self.high - self.low


# ── Position state ─────────────────────────────────────────────────────────────

class _PositionState:
    """
    Tracks the current open position including its ATR-based stop and target.
    """
    def __init__(self) -> None:
        self.side:            Optional[str]   = None
        self.open_candle_idx: Optional[int]   = None
        self.entry_price:     Optional[float] = None
        self.stop_price:      Optional[float] = None
        self.target_price:    Optional[float] = None
        self.mode:            Optional[str]   = None  # "TRENDING_ORB" | "RANGING_ZSCORE"

    def open(
        self,
        side: str,
        candle_idx: int,
        price: float,
        stop: float,
        target: Optional[float],
        mode: str,
    ) -> None:
        self.side            = side
        self.open_candle_idx = candle_idx
        self.entry_price     = price
        self.stop_price      = stop
        self.target_price    = target
        self.mode            = mode

    def close(self) -> None:
        self.__init__()

    @property
    def is_open(self) -> bool:
        return self.side is not None

    def candles_open(self, current_idx: int) -> int:
        if self.open_candle_idx is None:
            return 0
        return current_idx - self.open_candle_idx


# ── ARIA Strategy ──────────────────────────────────────────────────────────────

class ARIAStrategy:
    """
    ARIA — Adaptive Regime Intraday Algo.

    Usage (live trading):
        strategy = ARIAStrategy()
        # called by execution layer after fill:
        strategy.on_position_open(side, entry_price, stop, target, mode)
        strategy.on_position_close()
        # called on every 5-min candle close:
        signal = strategy.evaluate(ltp=close, volume=vol)

    Usage (backtesting):
        signal = strategy.evaluate(ltp=close, volume=vol, ts=candle_timestamp)
    """

    def __init__(self) -> None:
        self._position         = _PositionState()
        self._orb              = ORBState()
        self._candle_count     = 0
        self._daily_trade_count = 0
        self._today_date:       Optional[object] = None
        self._day_regime:       Optional[str]    = None
        self._last_signal:      Optional[SignalEvent] = None

    # ── External position updates (called by paper / live engine) ─────────────

    def on_position_open(
        self,
        side: str,
        entry_price: float,
        stop: float,
        target: Optional[float],
        mode: str,
    ) -> None:
        self._position.open(side, self._candle_count, entry_price, stop, target, mode)
        self._daily_trade_count += 1
        log.info(
            f"[ARIA] Position opened | side={side} mode={mode} "
            f"entry={entry_price:.4f} stop={stop:.4f} target={target}"
        )

    def on_position_close(self) -> None:
        log.info(f"[ARIA] Position closed | was {self._position.side}")
        self._position.close()

    # ── Day boundary reset ────────────────────────────────────────────────────

    def _maybe_reset_day(self, ts: datetime) -> None:
        today = ts.date()
        if today != self._today_date:
            self._today_date        = today
            self._daily_trade_count = 0
            self._day_regime        = None
            self._orb.reset()
            log.info(f"[ARIA] New day {today} — ORB and counters reset")

    # ── Main evaluation ───────────────────────────────────────────────────────

    def evaluate(
        self,
        ltp:    float = 0.0,
        volume: int   = 0,
        ts:     Optional[datetime] = None,
    ) -> Optional[SignalEvent]:
        """
        Evaluate one 5-minute candle close and return a SignalEvent or None.

        Args:
            ltp:    Last traded price from tick feed (0 = use candle close).
            volume: Cumulative volume from tick feed (0 = use candle volume).
            ts:     Candle timestamp (None = use datetime.now(IST) for live).
        """
        self._candle_count += 1
        now = ts if ts is not None else datetime.now(IST)

        # ── Fetch candles and compute indicators ──────────────────────────────
        df = get_latest_candles(n=_CANDLE_FETCH, interval=CANDLE_INTERVAL)
        if len(df) < _MIN_CANDLES:
            log.warning(f"[ARIA] Insufficient candles: {len(df)} < {_MIN_CANDLES}")
            return None

        close_s = df["close"]
        high_s  = df["high"]
        low_s   = df["low"]
        vol_s   = df["volume"]

        z_series   = zscore(close_s, window=Z_WINDOW)
        adx_series = adx(high_s, low_s, close_s, period=14)
        rsi_series = rsi(close_s, period=14)
        atr_series = atr(high_s, low_s, close_s, period=10)
        ema_fast_s = ema(close_s, span=EMA_FAST_SPAN)
        ema_slow_s = ema(close_s, span=EMA_SLOW_SPAN)
        ema_dir_s  = ema(close_s, span=EMA_DIRECTION_SPAN)

        z_val      = float(z_series.iloc[-1])
        adx_val    = float(adx_series.iloc[-1])
        rsi_val    = float(rsi_series.iloc[-1])
        atr_val    = float(atr_series.iloc[-1])
        ema_fast   = float(ema_fast_s.iloc[-1])
        ema_slow   = float(ema_slow_s.iloc[-1])
        ema_dir    = float(ema_dir_s.iloc[-1])   # 50-period macro trend gate
        price      = ltp if ltp > 0 else float(close_s.iloc[-1])
        vol        = volume if volume > 0 else int(vol_s.iloc[-1])
        regime     = classify_regime(adx_val)

        self._maybe_reset_day(now)

        # ── ORB calibration window (9:00–9:15 AM) ────────────────────────────
        now_time = now.time()
        in_orb_window = _ORB_WINDOW_START <= now_time <= _ORB_WINDOW_END
        if in_orb_window and not self._orb.is_built:
            last_high = float(high_s.iloc[-1])
            last_low  = float(low_s.iloc[-1])
            self._orb.update(last_high, last_low)
            if self._orb.is_built:
                self._day_regime = regime
                log.info(
                    f"[ARIA] ORB complete | high={self._orb.high:.4f} "
                    f"low={self._orb.low:.4f} width={self._orb.width:.4f} "
                    f"day_regime={self._day_regime}"
                )

        log.info(
            f"[ARIA] tick | Z={z_val:+.3f} ADX={adx_val:.1f} RSI={rsi_val:.1f} "
            f"ATR={atr_val:.4f} regime={regime} LTP={price:.4f} "
            f"ORB={'built' if self._orb.is_built else 'pending'} "
            f"trades_today={self._daily_trade_count}/{MAX_DAILY_TRADES}"
        )

        # ── Exit checks (run always — no session or trade-count gate) ─────────
        if self._position.is_open:
            signal = self._check_exit(
                now, z_val, adx_val, rsi_val, atr_val, price, vol, regime
            )
            if signal:
                self._store_signal(signal)
                self._last_signal = signal
                return signal

        # ── Guard: skip entries on NaN indicators ─────────────────────────────
        if any(math.isnan(v) for v in [z_val, adx_val, rsi_val, atr_val,
                                        ema_fast, ema_slow, ema_dir]):
            return None

        # ── Entry window gate (9:15 AM – 12:00 PM) ───────────────────────────
        if not (_ENTRY_WINDOW_START <= now_time < ENTRY_SESSION_END):
            return None

        # ── Daily trade cap ───────────────────────────────────────────────────
        if self._daily_trade_count >= MAX_DAILY_TRADES:
            return None

        # ── RBI window gate ───────────────────────────────────────────────────
        if is_rbi_window():
            return None

        # ── Entry check (only when flat and ORB is ready) ────────────────────
        if not self._position.is_open and self._orb.is_built:
            signal = self._check_entry(
                now, z_val, adx_val, rsi_val, atr_val,
                ema_fast, ema_slow, ema_dir, price, vol, regime,
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
        passed: List[str] = []
        failed: List[str] = []
        pos = self._position

        # 1. ATR stop-loss (all modes)
        stop_hit = False
        if pos.stop_price is not None:
            if pos.side == "LONG":
                stop_hit = price <= pos.stop_price
            else:
                stop_hit = price >= pos.stop_price
        if stop_hit:
            passed.append("stop_loss")
            log.info(
                f"[ARIA] Stop hit | side={pos.side} entry={pos.entry_price:.4f} "
                f"stop={pos.stop_price:.4f} price={price:.4f}"
            )

        # 2. ATR profit target (TRENDING mode only)
        target_hit = False
        if pos.mode == "TRENDING_ORB" and pos.target_price is not None:
            if pos.side == "LONG":
                target_hit = price >= pos.target_price
            else:
                target_hit = price <= pos.target_price
        if target_hit:
            passed.append("target_hit")
            log.info(
                f"[ARIA] Target hit | side={pos.side} "
                f"target={pos.target_price:.4f} price={price:.4f}"
            )

        # 3. Z-score reversion (RANGING mode only)
        z_reverted = (
            pos.mode == "RANGING_ZSCORE"
            and not math.isnan(z_val)
            and abs(z_val) < Z_EXIT_THRESHOLD
        )
        if z_reverted:
            passed.append("z_exit")

        # 4. Time exit (both modes)
        candles_open = pos.candles_open(self._candle_count)
        time_exit    = candles_open >= TIME_EXIT_CANDLES
        if time_exit:
            passed.append("time_exit")
            log.info(f"[ARIA] Time exit | {candles_open} candles held")

        # 5. EOD square-off
        eod_exit = ts.time() >= SQUARE_OFF_TIME
        if eod_exit:
            passed.append("eod_exit")

        if stop_hit or target_hit or z_reverted or time_exit or eod_exit:
            return SignalEvent(
                timestamp=ts, symbol=SYMBOL, action="EXIT",
                z_score=z_val, adx=adx_val, rsi=rsi_val, atr=atr_val,
                ltp=price, volume=vol, regime=regime,
                filters_passed=passed, filters_failed=failed,
                strategy_mode=pos.mode or "",
                orb_high=self._orb.high,
                orb_low=self._orb.low,
            )
        return None

    # ── Entry logic ────────────────────────────────────────────────────────────

    def _check_entry(
        self,
        ts: datetime,
        z_val: float, adx_val: float, rsi_val: float, atr_val: float,
        ema_fast: float, ema_slow: float, ema_dir: float,
        price: float, vol: int, regime: str,
    ) -> Optional[SignalEvent]:
        if regime == TRENDING:
            return self._orb_entry(
                ts, z_val, adx_val, rsi_val, atr_val,
                ema_fast, ema_slow, ema_dir, price, vol, regime,
            )
        if regime == RANGING:
            return self._zscore_entry(
                ts, z_val, adx_val, rsi_val, atr_val,
                ema_dir, price, vol, regime,
            )
        # NEUTRAL — sit out
        return None

    def _orb_entry(
        self,
        ts: datetime,
        z_val: float, adx_val: float, rsi_val: float, atr_val: float,
        ema_fast: float, ema_slow: float, ema_dir: float,
        price: float, vol: int, regime: str,
    ) -> Optional[SignalEvent]:
        """ORB breakout entry for TRENDING regime."""
        passed: List[str] = []
        failed: List[str] = []

        # Require price to clear ORB high/low by at least ORB_MIN_BREAKOUT_ATR × ATR(10)
        # This eliminates false breakouts where price barely ticks above the range
        min_gap  = ORB_MIN_BREAKOUT_ATR * atr_val
        is_long  = price > self._orb.high + min_gap
        is_short = price < self._orb.low  - min_gap

        if not (is_long or is_short):
            return None  # no confirmed breakout — wait quietly

        passed.append("orb_break")

        # Macro trend direction gate: EMA(50) determines which side we trade
        # LONG only in uptrend (price > EMA50), SHORT only in downtrend (price < EMA50)
        trend_ok_long  = price > ema_dir
        trend_ok_short = price < ema_dir

        if (is_long and not trend_ok_long) or (is_short and not trend_ok_short):
            failed.append("trend_direction")
            return SignalEvent(
                timestamp=ts, symbol=SYMBOL, action="SKIP",
                z_score=z_val, adx=adx_val, rsi=rsi_val, atr=atr_val,
                ltp=price, volume=vol, regime=regime,
                filters_passed=passed, filters_failed=failed,
                strategy_mode="TRENDING_ORB",
                orb_high=self._orb.high, orb_low=self._orb.low,
            )

        passed.append("trend_direction")

        # Short-term momentum confirmation: RSI direction + EMA(9/21) crossover
        momentum_long  = rsi_val > 50 and ema_fast > ema_slow
        momentum_short = rsi_val < 50 and ema_fast < ema_slow

        if (is_long and not momentum_long) or (is_short and not momentum_short):
            failed.append("momentum")
            return SignalEvent(
                timestamp=ts, symbol=SYMBOL, action="SKIP",
                z_score=z_val, adx=adx_val, rsi=rsi_val, atr=atr_val,
                ltp=price, volume=vol, regime=regime,
                filters_passed=passed, filters_failed=failed,
                strategy_mode="TRENDING_ORB",
                orb_high=self._orb.high, orb_low=self._orb.low,
            )

        passed.append("momentum")
        action = "LONG" if is_long else "SHORT"

        if action == "LONG":
            stop   = price - ATR_STOP_MULTIPLIER   * atr_val
            target = price + ATR_TARGET_MULTIPLIER * atr_val
        else:
            stop   = price + ATR_STOP_MULTIPLIER   * atr_val
            target = price - ATR_TARGET_MULTIPLIER * atr_val

        log.info(
            f"[ARIA] ORB {action} | price={price:.4f} "
            f"ORB={self._orb.low:.4f}–{self._orb.high:.4f} "
            f"stop={stop:.4f} target={target:.4f} ATR={atr_val:.4f}"
        )
        return SignalEvent(
            timestamp=ts, symbol=SYMBOL, action=action,
            z_score=z_val, adx=adx_val, rsi=rsi_val, atr=atr_val,
            ltp=price, volume=vol, regime=regime,
            filters_passed=passed, filters_failed=failed,
            stop_price=stop, target_price=target,
            strategy_mode="TRENDING_ORB",
            orb_high=self._orb.high, orb_low=self._orb.low,
        )

    def _zscore_entry(
        self,
        ts: datetime,
        z_val: float, adx_val: float, rsi_val: float, atr_val: float,
        ema_dir: float,
        price: float, vol: int, regime: str,
    ) -> Optional[SignalEvent]:
        """Z-score mean reversion entry for RANGING regime."""
        passed: List[str] = []
        failed: List[str] = []

        is_long  = z_val < -Z_ENTRY_THRESHOLD
        is_short = z_val >  Z_ENTRY_THRESHOLD

        if not (is_long or is_short):
            return None

        passed.append("z_score")

        # Macro trend direction gate: same filter as ORB — don't fight the trend
        trend_ok_long  = price > ema_dir
        trend_ok_short = price < ema_dir

        if (is_long and not trend_ok_long) or (is_short and not trend_ok_short):
            failed.append("trend_direction")
            return SignalEvent(
                timestamp=ts, symbol=SYMBOL, action="SKIP",
                z_score=z_val, adx=adx_val, rsi=rsi_val, atr=atr_val,
                ltp=price, volume=vol, regime=regime,
                filters_passed=passed, filters_failed=failed,
                strategy_mode="RANGING_ZSCORE",
                orb_high=self._orb.high, orb_low=self._orb.low,
            )

        passed.append("trend_direction")
        action = "LONG" if is_long else "SHORT"

        if action == "LONG":
            stop   = price - ATR_STOP_MULTIPLIER * atr_val
            target = None   # exit on Z-reversion, not fixed target
        else:
            stop   = price + ATR_STOP_MULTIPLIER * atr_val
            target = None

        log.info(
            f"[ARIA] Z-score {action} | Z={z_val:+.3f} price={price:.4f} "
            f"stop={stop:.4f} ATR={atr_val:.4f}"
        )
        return SignalEvent(
            timestamp=ts, symbol=SYMBOL, action=action,
            z_score=z_val, adx=adx_val, rsi=rsi_val, atr=atr_val,
            ltp=price, volume=vol, regime=regime,
            filters_passed=passed, filters_failed=failed,
            stop_price=stop, target_price=target,
            strategy_mode="RANGING_ZSCORE",
            orb_high=self._orb.high, orb_low=self._orb.low,
        )

    # ── Persistence ────────────────────────────────────────────────────────────

    def _store_signal(self, signal: SignalEvent) -> None:
        try:
            insert_signal(
                symbol=signal.symbol, action=signal.action,
                z_score=signal.z_score, adx=signal.adx,
                rsi=signal.rsi, atr=signal.atr,
                ltp=signal.ltp, volume=signal.volume,
                regime=signal.regime,
                filters_passed=signal.filters_passed,
                filters_failed=signal.filters_failed,
            )
        except Exception as exc:
            log.warning(f"[ARIA] Failed to store signal: {exc}")

    # ── Read-only accessors ────────────────────────────────────────────────────

    @property
    def position_side(self) -> Optional[str]:
        return self._position.side

    @property
    def orb(self) -> ORBState:
        return self._orb

    @property
    def day_regime(self) -> Optional[str]:
        return self._day_regime

    @property
    def last_signal(self) -> Optional[SignalEvent]:
        return self._last_signal
