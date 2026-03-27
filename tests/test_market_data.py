"""
tests/test_market_data.py
=========================
Tests for Phase 2 data pipeline modules.

Covers:
  - CandleBuilder logic (window boundaries, OHLCV accumulation)
  - RBI window / market-hours utilities
  - News RSS parsing and keyword flagging
  - has_rbi_news() time window query
  - Historical data storage and retrieval
  - Price normalisation divisor sanity check

No real API calls — all tests use mocks and the temp DB fixture.

Run with:
    pytest tests/test_market_data.py -v
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import pytz

IST = pytz.timezone("Asia/Kolkata")


# ═══════════════════════════════════════════════════════════════
# CandleBuilder
# ═══════════════════════════════════════════════════════════════

class TestCandleBuilder:
    """Unit tests for the 5-minute candle aggregator."""

    def _builder(self):
        from core.data.market_feed import _CandleBuilder
        return _CandleBuilder(interval_minutes=5)

    def _ts(self, h, m, s=0) -> datetime:
        """Helper: build an IST datetime for today at HH:MM:SS."""
        return datetime.now(IST).replace(
            hour=h, minute=m, second=s, microsecond=0
        )

    def test_first_tick_returns_none(self):
        """No candle is emitted on the very first tick."""
        b = self._builder()
        result = b.on_tick(84.25, 100, self._ts(9, 1))
        assert result is None

    def test_same_window_accumulates_ohlcv(self):
        """Ticks in the same 5-min window update high/low/close, not open."""
        b = self._builder()
        b.on_tick(84.20, 100, self._ts(9, 1))
        b.on_tick(84.30, 200, self._ts(9, 2))
        b.on_tick(84.10, 150, self._ts(9, 3))
        partial = b.get_partial()
        assert partial["open"]   == 84.20
        assert partial["high"]   == 84.30
        assert partial["low"]    == 84.10
        assert partial["close"]  == 84.10
        assert partial["volume"] == 450

    def test_window_boundary_emits_candle(self):
        """Crossing into a new 5-min window emits the previous candle."""
        b = self._builder()
        b.on_tick(84.20, 100, self._ts(9, 1))
        b.on_tick(84.30, 200, self._ts(9, 3))
        # Tick in next window (09:05) triggers candle emission
        candle = b.on_tick(84.40, 50, self._ts(9, 5))
        assert candle is not None
        assert candle["open"]   == 84.20
        assert candle["high"]   == 84.30
        assert candle["close"]  == 84.30
        assert candle["volume"] == 300

    def test_new_window_starts_fresh(self):
        """After emitting a candle, the new window starts with the triggering tick."""
        b = self._builder()
        b.on_tick(84.20, 100, self._ts(9, 1))
        b.on_tick(84.40, 50,  self._ts(9, 5))   # triggers candle, starts new window
        partial = b.get_partial()
        assert partial["open"]  == 84.40
        assert partial["close"] == 84.40

    def test_window_floor_rounds_correctly(self):
        """Timestamps at 09:06:59 and 09:07:00 should be in the same 09:05 window."""
        b = self._builder()
        b.on_tick(84.25, 100, self._ts(9, 6, 59))
        candle = b.on_tick(84.26, 50, self._ts(9, 7, 0))
        assert candle is None   # 09:07 is still in the 09:05 window

    def test_multiple_windows_emitted_correctly(self):
        """Multiple window crossings each emit a separate candle."""
        b = self._builder()
        b.on_tick(84.00, 100, self._ts(9, 1))
        b.on_tick(84.10, 100, self._ts(9, 5))   # emits 09:00 candle
        candle2 = b.on_tick(84.20, 100, self._ts(9, 10))  # emits 09:05 candle
        assert candle2 is not None
        assert candle2["open"] == 84.10

    def test_get_partial_none_before_first_tick(self):
        b = self._builder()
        assert b.get_partial() is None


# ═══════════════════════════════════════════════════════════════
# RBI window & market hours utilities
# ═══════════════════════════════════════════════════════════════

class TestRBIWindow:
    """Tests for is_rbi_window(), is_market_hours(), minutes_until_rbi_window()."""

    def _mock_now(self, h, m):
        """Patch datetime.now(IST) to return a fixed time."""
        fixed = datetime.now(IST).replace(hour=h, minute=m, second=0, microsecond=0)
        return fixed

    def test_inside_rbi_window(self):
        from core.data.market_feed import is_rbi_window
        with patch("core.data.market_feed.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_now(12, 0)
            assert is_rbi_window() is True

    def test_outside_rbi_window_morning(self):
        from core.data.market_feed import is_rbi_window
        with patch("core.data.market_feed.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_now(10, 0)
            assert is_rbi_window() is False

    def test_outside_rbi_window_afternoon(self):
        from core.data.market_feed import is_rbi_window
        with patch("core.data.market_feed.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_now(13, 0)
            assert is_rbi_window() is False

    def test_market_hours_open(self):
        from core.data.market_feed import is_market_hours
        with patch("core.data.market_feed.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_now(11, 0)
            assert is_market_hours() is True

    def test_market_hours_before_open(self):
        from core.data.market_feed import is_market_hours
        with patch("core.data.market_feed.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_now(8, 30)
            assert is_market_hours() is False

    def test_market_hours_after_close(self):
        from core.data.market_feed import is_market_hours
        with patch("core.data.market_feed.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_now(16, 0)
            assert is_market_hours() is False


# ═══════════════════════════════════════════════════════════════
# News RSS parsing
# ═══════════════════════════════════════════════════════════════

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>RBI Press Releases</title>
    <item>
      <title>RBI sells dollars to arrest rupee depreciation</title>
      <link>https://rbi.org.in/1</link>
    </item>
    <item>
      <title>India GDP growth forecast revised upward</title>
      <link>https://rbi.org.in/2</link>
    </item>
    <item>
      <title>RBI monetary policy committee meets next week</title>
      <link>https://rbi.org.in/3</link>
    </item>
  </channel>
</rss>"""

MALFORMED_RSS = "<this is not valid xml"


class TestNewsRSSParsing:
    def test_parse_valid_rss_returns_items(self):
        from core.data.news_feed import _parse_rss
        items = _parse_rss(SAMPLE_RSS)
        assert len(items) == 3
        assert items[0]["headline"] == "RBI sells dollars to arrest rupee depreciation"
        assert "rbi.org.in/1" in items[0]["url"]

    def test_parse_malformed_rss_returns_empty(self):
        from core.data.news_feed import _parse_rss
        items = _parse_rss(MALFORMED_RSS)
        assert items == []

    def test_parse_empty_string_returns_empty(self):
        from core.data.news_feed import _parse_rss
        assert _parse_rss("") == []


class TestNewsKeywordFlagging:
    def test_rbi_headline_flagged(self):
        from core.data.news_feed import _is_rbi_flag
        assert _is_rbi_flag("RBI sells dollars to arrest rupee depreciation") is True

    def test_neutral_headline_not_flagged(self):
        from core.data.news_feed import _is_rbi_flag
        assert _is_rbi_flag("India GDP growth forecast revised upward") is False

    def test_case_insensitive_matching(self):
        from core.data.news_feed import _is_rbi_flag
        assert _is_rbi_flag("RUPEE WEAKENS ON FED RATE DECISION") is True

    def test_intervention_keyword_flagged(self):
        from core.data.news_feed import _is_rbi_flag
        assert _is_rbi_flag("Central bank intervention lifts rupee") is True

    def test_fed_keyword_flagged(self):
        from core.data.news_feed import _is_rbi_flag
        assert _is_rbi_flag("Federal Reserve keeps rates unchanged") is True


class TestNewsDatabaseStorage:
    def test_insert_new_headline_returns_true(self, fresh_db):
        from core.audit.database import insert_news_item
        result = insert_news_item("RBI", "Test headline", "http://x.com", 0)
        assert result is True

    def test_duplicate_headline_returns_false(self, fresh_db):
        from core.audit.database import insert_news_item
        insert_news_item("RBI", "Duplicate headline", "http://x.com", 0)
        result = insert_news_item("RBI", "Duplicate headline", "http://x.com", 0)
        assert result is False   # second insert silently ignored

    def test_get_recent_returns_correct_count(self, fresh_db):
        from core.audit.database import get_recent_news, insert_news_item
        for i in range(7):
            insert_news_item("RBI", f"Headline {i}", "", 0)
        rows = get_recent_news(5)
        assert len(rows) == 5

    def test_has_rbi_news_true_when_recent(self, fresh_db):
        from core.audit.database import insert_news_item
        from core.data.news_feed import has_rbi_news
        insert_news_item("RBI", "RBI intervention pushes rupee up", "", 1)
        assert has_rbi_news(minutes=60) is True

    def test_has_rbi_news_false_when_no_flagged(self, fresh_db):
        from core.audit.database import insert_news_item
        from core.data.news_feed import has_rbi_news
        insert_news_item("RBI", "India GDP grows 7 percent", "", 0)
        assert has_rbi_news(minutes=60) is False

    def test_poll_once_stores_headlines(self, fresh_db):
        """poll_once() fetches real HTTP + stores in DB — mock the HTTP layer."""
        from core.data.news_feed import poll_once
        with patch("core.data.news_feed.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.raise_for_status = lambda: None
            mock_get.return_value.text = SAMPLE_RSS
            added = poll_once()
        # 3 items × 2 feeds = 6 (but same RSS returned for both, so 6 inserts)
        assert added > 0


# ═══════════════════════════════════════════════════════════════
# Historical candle storage & retrieval
# ═══════════════════════════════════════════════════════════════

class TestCandleStorage:
    def _make_candle(self, ts_str: str, close: float = 84.25) -> dict:
        return {
            "symbol":    "USDINR",
            "interval":  "FIVE_MINUTE",
            "timestamp": ts_str,
            "open":      close - 0.05,
            "high":      close + 0.10,
            "low":       close - 0.10,
            "close":     close,
            "volume":    1000,
        }

    def test_upsert_candle_stores_row(self, fresh_db):
        from core.audit.database import count_candles, upsert_candle
        upsert_candle(self._make_candle("2026-03-27T09:05:00+05:30"))
        assert count_candles() == 1

    def test_upsert_candle_no_duplicate(self, fresh_db):
        from core.audit.database import count_candles, upsert_candle
        c = self._make_candle("2026-03-27T09:05:00+05:30")
        upsert_candle(c)
        upsert_candle(c)   # same timestamp — should overwrite, not duplicate
        assert count_candles() == 1

    def test_upsert_candle_replaces_value(self, fresh_db):
        from core.audit.database import get_connection, upsert_candle
        c = self._make_candle("2026-03-27T09:05:00+05:30", close=84.25)
        upsert_candle(c)
        c["close"] = 84.50   # updated close
        upsert_candle(c)
        with get_connection() as conn:
            row = conn.execute(
                "SELECT close FROM candles WHERE timestamp=?",
                ("2026-03-27T09:05:00+05:30",),
            ).fetchone()
        assert row["close"] == 84.50

    def test_get_latest_candles_returns_dataframe(self, fresh_db):
        from core.audit.database import upsert_candle
        # Insert 5 candles
        for i in range(5):
            ts = f"2026-03-27T09:0{i}:00+05:30"
            upsert_candle(self._make_candle(ts, close=84.20 + i * 0.01))

        # Patch session manager so historical.py doesn't need real auth
        with patch("core.data.historical.get_smart_connect"):
            from core.data.historical import get_latest_candles
            df = get_latest_candles(n=5)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5
        assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
        # Should be sorted oldest → newest
        assert df["close"].iloc[0] <= df["close"].iloc[-1]

    def test_get_latest_candles_empty_db(self, fresh_db):
        with patch("core.data.historical.get_smart_connect"):
            from core.data.historical import get_latest_candles
            df = get_latest_candles(n=5)
        assert len(df) == 0


# ═══════════════════════════════════════════════════════════════
# Price normalisation sanity check
# ═══════════════════════════════════════════════════════════════

class TestPriceNormalisation:
    def test_price_divisor_gives_plausible_usdinr(self):
        """
        Verifies that the PRICE_DIVISOR constant converts a raw Angel One
        CDS LTP to a plausible USDINR value (between 70 and 100).
        """
        from core.data.market_feed import PRICE_DIVISOR
        # Simulate raw LTP for USDINR ≈ 84.25
        raw_ltp = 8425           # what Angel One sends
        normalised = raw_ltp / PRICE_DIVISOR
        assert 70 < normalised < 100, (
            f"Normalised price {normalised} is outside plausible USDINR range (70-100). "
            f"Check PRICE_DIVISOR={PRICE_DIVISOR} against live data."
        )
