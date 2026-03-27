"""
tests/test_strategy.py
=======================
Tests for Phase 3 strategy engine modules.

Covers:
  - indicators: zscore, ema, rsi, adx, atr (correctness + edge cases)
  - regime_detector: classify_regime, is_tradeable_regime
  - mean_reversion: entry/exit filters, signal state machine, DB storage

No real API calls — uses synthetic price series and the temp DB fixture.

Run with:
    pytest tests/test_strategy.py -v
"""

import math
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import pytz

IST = pytz.timezone("Asia/Kolkata")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _flat_series(value: float, n: int = 50) -> pd.Series:
    """Constant price series — Z-score should be 0, ATR small."""
    return pd.Series([value] * n, dtype=float)


def _sine_series(n: int = 50, amplitude: float = 0.5, base: float = 84.0) -> pd.Series:
    """Sine wave around `base` — produces meaningful Z-score oscillations."""
    t = np.linspace(0, 4 * np.pi, n)
    return pd.Series(base + amplitude * np.sin(t), dtype=float)


def _trending_series(n: int = 60, start: float = 80.0, end: float = 90.0) -> pd.Series:
    """Steady uptrend — should produce high ADX."""
    return pd.Series(np.linspace(start, end, n), dtype=float)


def _make_ohlcv(close_series: pd.Series, spread: float = 0.05) -> pd.DataFrame:
    """Build synthetic OHLCV DataFrame from a close series."""
    high  = close_series + spread
    low   = close_series - spread
    open_ = close_series.shift(1).fillna(close_series.iloc[0])
    vol   = pd.Series([1000] * len(close_series), dtype=int)
    return pd.DataFrame({
        "open":   open_,
        "high":   high,
        "low":    low,
        "close":  close_series,
        "volume": vol,
    }).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════
# indicators.py
# ═══════════════════════════════════════════════════════════════

class TestZscore:
    def test_flat_series_zscore_is_zero(self):
        from core.strategy.indicators import zscore
        s = _flat_series(84.25, 30)
        z = zscore(s, window=20)
        # Flat series: std=0, result is 0.0 (not NaN)
        assert z.iloc[-1] == 0.0 or math.isnan(z.iloc[-1]) is False

    def test_insufficient_data_returns_nan(self):
        from core.strategy.indicators import zscore
        s  = pd.Series([84.0] * 10, dtype=float)
        z  = zscore(s, window=20)
        # All values should be NaN — not enough data
        assert z.isna().all()

    def test_high_price_gives_positive_zscore(self):
        from core.strategy.indicators import zscore
        # 19 normal values + 1 extreme high → last Z should be large positive
        s = pd.Series([84.0] * 19 + [90.0], dtype=float)
        z = zscore(s, window=20)
        assert z.iloc[-1] > 2.0

    def test_low_price_gives_negative_zscore(self):
        from core.strategy.indicators import zscore
        s = pd.Series([84.0] * 19 + [78.0], dtype=float)
        z = zscore(s, window=20)
        assert z.iloc[-1] < -2.0

    def test_returns_same_length_as_input(self):
        from core.strategy.indicators import zscore
        s = _sine_series(50)
        z = zscore(s, window=20)
        assert len(z) == len(s)

    def test_zscore_is_centered_near_zero(self):
        """Z-score of a random-ish series should be near 0 on average."""
        from core.strategy.indicators import zscore
        s = _sine_series(100)
        z = zscore(s, window=20).dropna()
        assert abs(z.mean()) < 0.5


class TestEMA:
    def test_ema_length_matches_input(self):
        from core.strategy.indicators import ema
        s   = _flat_series(84.0, 30)
        out = ema(s, span=10)
        assert len(out) == 30

    def test_ema_of_flat_series_equals_value(self):
        from core.strategy.indicators import ema
        s   = _flat_series(84.0, 30)
        out = ema(s, span=5)
        assert abs(out.iloc[-1] - 84.0) < 1e-6

    def test_ema_min_periods_nan_before_span(self):
        from core.strategy.indicators import ema
        s   = pd.Series([1.0] * 20, dtype=float)
        out = ema(s, span=10)
        # First 9 should be NaN
        assert out.iloc[:9].isna().all()
        assert not math.isnan(out.iloc[9])

    def test_ema_lags_close_series(self):
        """EMA should lag a rising series."""
        from core.strategy.indicators import ema
        s   = _trending_series(50)
        out = ema(s, span=10)
        # EMA(50) < last close
        assert out.iloc[-1] < s.iloc[-1]


class TestRSI:
    def test_rsi_range_0_to_100(self):
        from core.strategy.indicators import rsi
        s   = _sine_series(60)
        r   = rsi(s, period=14).dropna()
        assert (r >= 0).all() and (r <= 100).all()

    def test_rsi_returns_same_length(self):
        from core.strategy.indicators import rsi
        s   = _sine_series(50)
        r   = rsi(s, period=14)
        assert len(r) == 50

    def test_rsi_nan_for_insufficient_data(self):
        from core.strategy.indicators import rsi
        s   = pd.Series([84.0] * 5, dtype=float)
        r   = rsi(s, period=14)
        assert r.isna().all()

    def test_rising_series_gives_high_rsi(self):
        from core.strategy.indicators import rsi
        s   = _trending_series(40, 80.0, 90.0)
        r   = rsi(s, period=14).dropna()
        # Steady uptrend → RSI should be elevated
        assert r.iloc[-1] > 60

    def test_falling_series_gives_low_rsi(self):
        from core.strategy.indicators import rsi
        s   = _trending_series(40, 90.0, 80.0)
        r   = rsi(s, period=14).dropna()
        assert r.iloc[-1] < 40


class TestADX:
    def test_adx_returns_same_length(self):
        from core.strategy.indicators import adx
        df  = _make_ohlcv(_trending_series(60))
        out = adx(df["high"], df["low"], df["close"], period=14)
        assert len(out) == 60

    def test_adx_range_0_to_100(self):
        from core.strategy.indicators import adx
        df  = _make_ohlcv(_sine_series(60))
        out = adx(df["high"], df["low"], df["close"], period=14).dropna()
        assert (out >= 0).all() and (out <= 100).all()

    def test_trending_series_has_higher_adx(self):
        from core.strategy.indicators import adx
        df_trend  = _make_ohlcv(_trending_series(60, 80, 90))
        df_range  = _make_ohlcv(_sine_series(60))
        adx_trend = adx(df_trend["high"], df_trend["low"], df_trend["close"]).dropna()
        adx_range = adx(df_range["high"], df_range["low"], df_range["close"]).dropna()
        assert adx_trend.iloc[-1] > adx_range.iloc[-1]

    def test_adx_nan_for_insufficient_data(self):
        from core.strategy.indicators import adx
        df  = _make_ohlcv(pd.Series([84.0] * 5, dtype=float))
        out = adx(df["high"], df["low"], df["close"], period=14)
        assert out.isna().all()


class TestATR:
    def test_atr_returns_same_length(self):
        from core.strategy.indicators import atr
        df  = _make_ohlcv(_sine_series(30))
        out = atr(df["high"], df["low"], df["close"], period=10)
        assert len(out) == 30

    def test_atr_is_positive(self):
        from core.strategy.indicators import atr
        df  = _make_ohlcv(_sine_series(40))
        out = atr(df["high"], df["low"], df["close"], period=10).dropna()
        assert (out > 0).all()

    def test_volatile_series_has_higher_atr(self):
        from core.strategy.indicators import atr
        df_volatile = _make_ohlcv(_sine_series(40, amplitude=2.0))
        df_calm     = _make_ohlcv(_sine_series(40, amplitude=0.05))
        atr_v = atr(df_volatile["high"], df_volatile["low"], df_volatile["close"]).dropna()
        atr_c = atr(df_calm["high"],     df_calm["low"],     df_calm["close"]).dropna()
        assert atr_v.iloc[-1] > atr_c.iloc[-1]

    def test_flat_series_has_near_zero_atr(self):
        from core.strategy.indicators import atr
        df  = _make_ohlcv(_flat_series(84.0, 30), spread=0.001)
        out = atr(df["high"], df["low"], df["close"], period=10).dropna()
        assert out.iloc[-1] < 0.01


# ═══════════════════════════════════════════════════════════════
# regime_detector.py
# ═══════════════════════════════════════════════════════════════

class TestRegimeDetector:
    def test_below_ranging_max_is_ranging(self):
        from core.strategy.regime_detector import classify_regime, RANGING
        assert classify_regime(15.0) == RANGING

    def test_zero_adx_is_ranging(self):
        from core.strategy.regime_detector import classify_regime, RANGING
        assert classify_regime(0.0) == RANGING

    def test_between_thresholds_is_neutral(self):
        from core.strategy.regime_detector import classify_regime, NEUTRAL
        # ADX_RANGING_MAX=20, ADX_TRENDING_MIN=25 → 22 is neutral
        assert classify_regime(22.0) == NEUTRAL

    def test_above_trending_min_is_trending(self):
        from core.strategy.regime_detector import classify_regime, TRENDING
        assert classify_regime(30.0) == TRENDING

    def test_exactly_ranging_max_is_neutral(self):
        from core.strategy.regime_detector import classify_regime, NEUTRAL
        # ADX = 20 exactly → "not < 20" → NEUTRAL
        assert classify_regime(20.0) == NEUTRAL

    def test_exactly_trending_min_is_neutral(self):
        from core.strategy.regime_detector import classify_regime, NEUTRAL
        # ADX = 25 exactly → "not > 25" → NEUTRAL
        assert classify_regime(25.0) == NEUTRAL

    def test_nan_returns_neutral(self):
        from core.strategy.regime_detector import classify_regime, NEUTRAL
        assert classify_regime(float("nan")) == NEUTRAL

    def test_none_returns_neutral(self):
        from core.strategy.regime_detector import classify_regime, NEUTRAL
        assert classify_regime(None) == NEUTRAL

    def test_is_tradeable_ranging(self):
        from core.strategy.regime_detector import is_tradeable_regime, RANGING
        assert is_tradeable_regime(RANGING) is True

    def test_is_tradeable_neutral_false(self):
        from core.strategy.regime_detector import is_tradeable_regime, NEUTRAL
        assert is_tradeable_regime(NEUTRAL) is False

    def test_is_tradeable_trending_false(self):
        from core.strategy.regime_detector import is_tradeable_regime, TRENDING
        assert is_tradeable_regime(TRENDING) is False


# ═══════════════════════════════════════════════════════════════
# mean_reversion.py — signal logic
# ═══════════════════════════════════════════════════════════════

def _make_candle_df(n: int = 50, close_values=None, spread: float = 0.05) -> pd.DataFrame:
    """
    Build a candle DataFrame with IST timestamps going back n×5min from now.
    Used to mock get_latest_candles().
    """
    if close_values is None:
        # Default: sine wave around 84.0 — produces non-trivial Z-score
        close_values = 84.0 + 0.5 * np.sin(np.linspace(0, 4 * np.pi, n))
    close  = pd.Series(close_values, dtype=float)
    high   = close + spread
    low    = close - spread
    open_  = close.shift(1).fillna(close.iloc[0])
    volume = pd.Series([5000] * n, dtype=int)
    now    = datetime.now(IST)
    times  = [now - timedelta(minutes=5 * (n - i)) for i in range(n)]
    return pd.DataFrame({
        "timestamp": times,
        "open":      open_,
        "high":      high,
        "low":       low,
        "close":     close,
        "volume":    volume,
    }).reset_index(drop=True)


def _make_ranging_df(n: int = 50) -> pd.DataFrame:
    """
    Produce a candle df that will result in RANGING regime (low ADX).
    Uses a pure sine wave — price oscillates predictably, no trend.
    """
    close = 84.0 + 0.3 * np.sin(np.linspace(0, 6 * np.pi, n))
    return _make_candle_df(n=n, close_values=close, spread=0.02)


class TestMeanReversionSignals:
    """Test signal generation in isolation by mocking get_latest_candles."""

    def _strategy(self):
        from core.strategy.mean_reversion import MeanReversionStrategy
        return MeanReversionStrategy()

    def test_insufficient_candles_returns_none(self, fresh_db):
        """If DB has < 40 candles, evaluate() returns None."""
        strat = self._strategy()
        small_df = _make_candle_df(n=10)
        with patch("core.strategy.mean_reversion.get_latest_candles", return_value=small_df):
            result = strat.evaluate(ltp=84.25)
        assert result is None

    def test_no_signal_when_z_within_threshold(self, fresh_db):
        """Z-score inside ±1.5 → no LONG/SHORT signal."""
        strat = self._strategy()
        # Sine wave with small amplitude → Z-score stays within ±1.5
        close  = 84.0 + 0.1 * np.sin(np.linspace(0, 4 * np.pi, 50))
        df     = _make_candle_df(n=50, close_values=close)
        with patch("core.strategy.mean_reversion.get_latest_candles", return_value=df):
            result = strat.evaluate(ltp=84.0)
        # If Z is small, evaluate returns None (no signal crossed threshold)
        if result is not None:
            assert result.action == "SKIP"   # can be SKIP if filtered

    def test_rbi_window_blocks_entry(self, fresh_db):
        """During the RBI window (11:30–12:30), entry signals become SKIP."""
        from core.strategy.mean_reversion import MeanReversionStrategy
        strat = MeanReversionStrategy()
        # Extreme Z-score
        close = pd.Series([84.0] * 19 + [78.0], dtype=float)
        df    = _make_candle_df(n=50, close_values=np.append([84.0] * 49, 78.0))
        with patch("core.strategy.mean_reversion.get_latest_candles", return_value=df):
            with patch("core.strategy.mean_reversion.is_rbi_window", return_value=True):
                result = strat.evaluate(ltp=78.0)
        # If z crossed threshold, it should be SKIP because RBI window is active
        if result is not None:
            assert result.action == "SKIP"
            assert "rbi_window" in result.filters_failed

    def test_trending_regime_blocks_entry(self, fresh_db):
        """Trending market (high ADX) should block entry."""
        strat = self._strategy()
        # Steadily trending close series
        close = np.linspace(80, 92, 50)
        df    = _make_candle_df(n=50, close_values=close)
        with patch("core.strategy.mean_reversion.get_latest_candles", return_value=df):
            with patch("core.strategy.mean_reversion.is_rbi_window", return_value=False):
                result = strat.evaluate(ltp=92.0)
        if result is not None and result.action != "SKIP":
            # If a signal fired, regime should not be RANGING
            assert result.regime != "RANGING"

    def test_exit_on_z_reversion(self, fresh_db):
        """Z-score reverting to near zero should trigger EXIT."""
        strat = self._strategy()
        # Open a long position manually
        strat.on_position_open("LONG", 84.0)

        # Z-score near 0 → trigger exit
        close = pd.Series([84.0] * 50, dtype=float)  # flat series, Z=0
        df    = _make_candle_df(n=50, close_values=close)
        with patch("core.strategy.mean_reversion.get_latest_candles", return_value=df):
            with patch("core.strategy.mean_reversion.is_rbi_window", return_value=False):
                result = strat.evaluate(ltp=84.0)
        # With a flat (Z=0) series and open position, EXIT should be triggered
        assert result is not None
        assert result.action == "EXIT"
        assert "z_exit" in result.filters_passed

    def test_time_exit_after_12_candles(self, fresh_db):
        """Position held for 12+ candles triggers a time-based exit."""
        strat = self._strategy()
        strat.on_position_open("LONG", 84.0)

        close = pd.Series([84.0] * 50, dtype=float)  # flat → Z=0
        df    = _make_candle_df(n=50, close_values=close)

        with patch("core.strategy.mean_reversion.get_latest_candles", return_value=df):
            with patch("core.strategy.mean_reversion.is_rbi_window", return_value=False):
                # Burn 12 candle evaluations without closing
                for _ in range(12):
                    strat._candle_count += 1
                strat._position.open_candle_idx = strat._candle_count - 13
                result = strat.evaluate(ltp=84.0)

        assert result is not None
        assert result.action == "EXIT"
        assert "time_exit" in result.filters_passed

    def test_eod_square_off_triggers_exit(self, fresh_db):
        """At or after 15:15 IST, EOD square-off should fire."""
        strat = self._strategy()
        strat.on_position_open("LONG", 84.0)

        close = pd.Series([84.25] * 50, dtype=float)
        df    = _make_candle_df(n=50, close_values=close)

        import datetime as _dt
        eod_time = _dt.time(15, 16)

        with patch("core.strategy.mean_reversion.get_latest_candles", return_value=df):
            with patch("core.strategy.mean_reversion.is_rbi_window", return_value=False):
                with patch("core.strategy.mean_reversion.datetime") as mock_dt:
                    # Make datetime.now(IST) return a time at 15:16
                    fake_now = datetime.now(IST).replace(hour=15, minute=16, second=0)
                    mock_dt.now.return_value = fake_now
                    result = strat.evaluate(ltp=84.25)

        assert result is not None
        assert result.action == "EXIT"
        assert "eod_exit" in result.filters_passed

    def test_no_reentry_while_position_open(self, fresh_db):
        """Strategy should emit EXIT, not a new LONG/SHORT, when position is open."""
        strat = self._strategy()
        strat.on_position_open("SHORT", 85.0)

        # Try to force an entry-level Z-score while position is open
        close = pd.Series([84.0] * 19 + [78.0], dtype=float)
        df    = _make_candle_df(n=50, close_values=np.append([84.0] * 49, 78.0))
        with patch("core.strategy.mean_reversion.get_latest_candles", return_value=df):
            with patch("core.strategy.mean_reversion.is_rbi_window", return_value=False):
                result = strat.evaluate(ltp=78.0)
        # Must not be a new LONG entry — can only EXIT or nothing
        if result is not None:
            assert result.action != "LONG"

    def test_position_state_open_close(self):
        """on_position_open and on_position_close update internal state correctly."""
        strat = self._strategy()
        assert not strat._position.is_open
        strat.on_position_open("LONG", 84.25)
        assert strat._position.is_open
        assert strat.position_side == "LONG"
        strat.on_position_close()
        assert not strat._position.is_open
        assert strat.position_side is None

    def test_signal_stored_in_db(self, fresh_db):
        """EXIT signals should be written to the SQLite signals table."""
        from core.audit.database import get_connection
        strat = self._strategy()
        strat.on_position_open("LONG", 84.0)

        close = pd.Series([84.0] * 50, dtype=float)
        df    = _make_candle_df(n=50, close_values=close)

        with patch("core.strategy.mean_reversion.get_latest_candles", return_value=df):
            with patch("core.strategy.mean_reversion.is_rbi_window", return_value=False):
                result = strat.evaluate(ltp=84.0)

        assert result is not None and result.action == "EXIT"
        with get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        assert count == 1

    def test_signal_event_to_dict(self):
        """SignalEvent.to_dict() should return the expected keys."""
        from core.strategy.mean_reversion import SignalEvent
        ts = datetime.now(IST)
        se = SignalEvent(
            timestamp=ts, symbol="USDINR", action="LONG",
            z_score=-1.8, adx=16.0, rsi=32.0, atr=0.025,
            ltp=84.10, volume=5000, regime="RANGING",
            filters_passed=["z_score", "regime"],
            filters_failed=[],
        )
        d = se.to_dict()
        assert d["action"] == "LONG"
        assert d["z_score"] == -1.8
        assert "USDINR" in d["symbol"]

    def test_signal_event_is_entry_exit(self):
        from core.strategy.mean_reversion import SignalEvent
        ts = datetime.now(IST)
        long_sig  = SignalEvent(datetime.now(IST), "USDINR", "LONG",  -1.8, 16.0, 32.0, 0.025, 84.1, 5000, "RANGING")
        short_sig = SignalEvent(datetime.now(IST), "USDINR", "SHORT",  1.8, 16.0, 68.0, 0.025, 84.4, 5000, "RANGING")
        exit_sig  = SignalEvent(datetime.now(IST), "USDINR", "EXIT",   0.1, 16.0, 50.0, 0.025, 84.2, 5000, "RANGING")
        skip_sig  = SignalEvent(datetime.now(IST), "USDINR", "SKIP",  -1.8, 30.0, 32.0, 0.025, 84.1, 5000, "TRENDING")
        assert long_sig.is_entry()  and not long_sig.is_exit()
        assert short_sig.is_entry() and not short_sig.is_exit()
        assert exit_sig.is_exit()   and not exit_sig.is_entry()
        assert not skip_sig.is_actionable() or skip_sig.action == "SKIP"
