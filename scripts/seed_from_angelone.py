"""
scripts/seed_from_angelone.py
==============================
Download USDINR FIVE_MINUTE candles from Angel One SmartAPI, resample to
FIFTEEN_MINUTE, and seed the local SQLite database for offline backtesting.

Why resample?  Angel One's getCandleData does not return FIFTEEN_MINUTE
data for the CDS segment. We fetch the raw 5-minute bars (which work),
aggregate each 3-candle group into one 15-minute OHLCV bar, and store it
with interval="FIFTEEN_MINUTE". The result is identical to what the
exchange would publish directly.

Resampling rules (pandas resample('15min')):
  open   = first 5m open in group
  high   = max of three 5m highs
  low    = min of three 5m lows
  close  = last 5m close in group
  volume = sum of three 5m volumes

Requires valid Angel One credentials in .env:
  ANGEL_ONE_API_KEY, ANGEL_ONE_CLIENT_ID, ANGEL_ONE_PASSWORD, ANGEL_ONE_TOTP_SECRET

Angel One FIVE_MINUTE historical API limits:
  - Max 30 days per request (hard limit)
  - Rate limit: 3 req/sec, 180 req/min — script sleeps 3s between requests

Usage:
    # Full 2-year dataset (730 days back from today) — recommended first run
    python scripts/seed_from_angelone.py

    # Custom date range
    python scripts/seed_from_angelone.py --start 2024-01-01 --end 2025-12-31

    # Wipe existing FIFTEEN_MINUTE candles and re-seed fresh
    python scripts/seed_from_angelone.py --wipe

    # Dry run — show what would be fetched without calling the API
    python scripts/seed_from_angelone.py --dry-run
"""

import argparse
import io
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import logging
logging.disable(logging.CRITICAL)

import pandas as pd
import pytz

from config.settings import (
    EXCHANGE,
    IST,
    MARKET_CLOSE,
    MARKET_OPEN,
    SYMBOL,
    TOKEN,
)
from core.audit.database import clear_candles, count_candles, init_db, upsert_candle
from core.auth.angel_auth import login, logout
import core.auth.session_manager as _sm

_5M_INTERVAL    = "FIVE_MINUTE"
_15M_INTERVAL   = "FIFTEEN_MINUTE"
MAX_DAYS_CHUNK  = 30    # Angel One hard limit for FIVE_MINUTE
RATE_DELAY      = 3.0   # seconds between chunks — well under 180/min


def _fetch_5m_chunk(smart, from_dt: datetime, to_dt: datetime) -> list:
    """
    Call getCandleData for one 30-day chunk of 5-minute data.
    Returns raw rows [[ts, o, h, l, c, v], ...] or [] on failure.
    """
    params = {
        "exchange":    EXCHANGE,
        "symboltoken": TOKEN,
        "interval":    _5M_INTERVAL,
        "fromdate":    from_dt.strftime("%Y-%m-%d %H:%M"),
        "todate":      to_dt.strftime("%Y-%m-%d %H:%M"),
    }
    try:
        resp = smart.getCandleData(params)
        if resp and resp.get("status") and resp.get("data"):
            return resp["data"]
        msg = (resp or {}).get("message", "empty response")
        print(f"  [WARN] No data {from_dt.date()} → {to_dt.date()} | {msg}")
        return []
    except Exception as exc:
        print(f"  [ERROR] getCandleData: {exc}")
        return []


def _resample_to_15m(raw_rows: list) -> pd.DataFrame:
    """
    Convert raw Angel One 5m rows to a 15-minute OHLCV DataFrame.
    Returns DataFrame with columns: [timestamp, open, high, low, close, volume]
    """
    if not raw_rows:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(raw_rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(IST)
    df = df.set_index("timestamp")
    df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].astype(float)
    df["volume"] = df["volume"].astype(int)

    df_15m = df.resample("15min", closed="left", label="left").agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna(subset=["open"])

    df_15m = df_15m.reset_index()
    df_15m = df_15m.rename(columns={"timestamp": "timestamp"})
    return df_15m


def seed(from_dt: datetime, to_dt: datetime, wipe: bool = False) -> int:
    """
    Login to Angel One, fetch FIVE_MINUTE candles, resample to FIFTEEN_MINUTE,
    store in SQLite. Returns number of new 15m candle rows added.
    """
    init_db()

    if wipe:
        deleted = clear_candles(SYMBOL, interval=_15M_INTERVAL)
        print(f"[DB] Wiped {deleted} existing FIFTEEN_MINUTE candle rows.")

    before = count_candles(SYMBOL, interval=_15M_INTERVAL)

    print(f"\n[Angel One] Logging in...")
    session = login()
    _sm._session = session
    smart = _sm.get_smart_connect()
    print(f"[Angel One] Login successful.\n")

    total_days   = (to_dt - from_dt).days
    total_chunks = (total_days + MAX_DAYS_CHUNK - 1) // MAX_DAYS_CHUNK
    print(
        f"[Seed] Fetching FIVE_MINUTE → resampling to FIFTEEN_MINUTE\n"
        f"       {from_dt.date()} → {to_dt.date()}  "
        f"({total_days} days, ~{total_chunks} API calls)\n"
    )

    all_15m_rows = []
    chunk_start  = from_dt
    chunk_num    = 0

    while chunk_start < to_dt:
        chunk_end = min(chunk_start + timedelta(days=MAX_DAYS_CHUNK), to_dt)
        chunk_num += 1

        raw = _fetch_5m_chunk(smart, chunk_start, chunk_end)
        df_15m = _resample_to_15m(raw)
        all_15m_rows.append(df_15m)

        print(
            f"  Chunk {chunk_num:>2}/{total_chunks}  "
            f"{chunk_start.date()} → {chunk_end.date()}  "
            f"→ {len(raw)} 5m bars  →  {len(df_15m)} 15m bars"
        )

        chunk_start = chunk_end + timedelta(minutes=5)
        if chunk_start < to_dt:
            time.sleep(RATE_DELAY)

    logout(session)
    print(f"\n[Angel One] Logged out.")

    if all_15m_rows:
        combined = pd.concat([df for df in all_15m_rows if not df.empty], ignore_index=True)
        combined = combined.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")

        print(f"\n[DB] Storing {len(combined)} FIFTEEN_MINUTE candles...")
        for _, row in combined.iterrows():
            upsert_candle({
                "symbol":    SYMBOL,
                "interval":  _15M_INTERVAL,
                "timestamp": row["timestamp"].isoformat(),
                "open":      float(row["open"]),
                "high":      float(row["high"]),
                "low":       float(row["low"]),
                "close":     float(row["close"]),
                "volume":    int(row["volume"]),
            })

    after   = count_candles(SYMBOL, interval=_15M_INTERVAL)
    new_rows = after - before
    print(f"[DB] Done. New rows added: {new_rows} | Total 15m candles: {after}")
    return new_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed SQLite DB with USDINR 15m candles (via 5m fetch + resample)"
    )
    parser.add_argument(
        "--start", default=None,
        help="Start date YYYY-MM-DD (default: 730 days ago)"
    )
    parser.add_argument(
        "--end", default=None,
        help="End date YYYY-MM-DD (default: today)"
    )
    parser.add_argument(
        "--days", type=int, default=730,
        help="Days of history when --start/--end not given (default: 730)"
    )
    parser.add_argument(
        "--wipe", action="store_true",
        help="Delete existing FIFTEEN_MINUTE candles before seeding"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be fetched without making any API calls"
    )
    args = parser.parse_args()

    if bool(args.start) != bool(args.end):
        print("[ERROR] --start and --end must be used together.")
        sys.exit(1)

    now = datetime.now(IST)

    if args.start and args.end:
        from_dt = IST.localize(datetime.strptime(args.start, "%Y-%m-%d").replace(
            hour=MARKET_OPEN.hour, minute=MARKET_OPEN.minute))
        to_dt   = IST.localize(datetime.strptime(args.end, "%Y-%m-%d").replace(
            hour=MARKET_CLOSE.hour, minute=MARKET_CLOSE.minute))
    else:
        to_dt   = now.replace(hour=MARKET_CLOSE.hour, minute=MARKET_CLOSE.minute,
                              second=0, microsecond=0)
        from_dt = (to_dt - timedelta(days=args.days)).replace(
            hour=MARKET_OPEN.hour, minute=MARKET_OPEN.minute,
            second=0, microsecond=0)

    total_days = (to_dt - from_dt).days
    chunks     = (total_days + MAX_DAYS_CHUNK - 1) // MAX_DAYS_CHUNK

    print(f"\n  Source   : Angel One FIVE_MINUTE → resample to FIFTEEN_MINUTE")
    print(f"  Range    : {from_dt.date()} → {to_dt.date()} ({total_days} days)")
    print(f"  Chunks   : ~{chunks} API calls × {RATE_DELAY}s = ~{chunks * RATE_DELAY:.0f}s wait")
    print(f"  Wipe DB  : {'YES — deleting FIFTEEN_MINUTE rows first' if args.wipe else 'NO — upsert only'}")

    if args.dry_run:
        print("\n  [DRY RUN] No API calls made. Remove --dry-run to proceed.")
        return

    seed(from_dt, to_dt, wipe=args.wipe)

    print(f"\n  Run the backtest:")
    print(f"    python scripts/backtest_offline.py --interval 15m --from {from_dt.date()} --to {to_dt.date()}")


if __name__ == "__main__":
    main()
