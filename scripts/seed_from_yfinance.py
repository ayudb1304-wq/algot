"""
scripts/seed_from_yfinance.py
==============================
Download USDINR=X candles from Yahoo Finance and seed the local SQLite
database so the offline backtest can run without Angel One API access.

Two modes:
  5m  (default) — 5-minute candles, up to 60 days back from today
                   Best for recent signal-level backtests.

  1h            — 1-hour candles, up to 730 days back (yfinance limit)
                   Lets us test strategy logic on 2024–2025 data when
                   USDINR was calm and range-bound (~83–86 INR).
                   Note: Z_WINDOW=48 means 48 hours (2 days) on 1h data
                   vs 4 hours on 5m data — strategy semantics differ.

Source:  Yahoo Finance (USDINR=X = USD/INR spot forex)
Note:    Spot and NSE CDS futures track very closely (basis < 0.01 INR)
         so this data is valid for strategy signal testing.
         Do NOT divide by 100 — that divisor only applies to Angel One
         raw WebSocket ticks.

Usage:
    # Recent 5-min data (last 60 days)
    python scripts/seed_from_yfinance.py

    # Specify exact date range for 5-min (must be within last 60 days)
    python scripts/seed_from_yfinance.py --start 2026-01-05 --end 2026-03-27

    # Historical 1-hour data (up to 2 years back) for pre-volatility testing
    python scripts/seed_from_yfinance.py --interval 1h --start 2024-01-01 --end 2025-06-30

    # Full 2-year 1h dataset
    python scripts/seed_from_yfinance.py --interval 1h --days 730
"""

import argparse
import io
import sys
from datetime import datetime, timedelta
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import pytz
import yfinance as yf

from core.audit.database import count_candles, init_db, upsert_candle

IST    = pytz.timezone("Asia/Kolkata")
TICKER = "USDINR=X"
SYMBOL = "USDINR"

# yfinance hard limits per interval
_MAX_DAYS = {"5m": 60, "15m": 60, "1h": 730}

# How we store the interval label in SQLite
_INTERVAL_LABEL = {"5m": "FIVE_MINUTE", "15m": "FIFTEEN_MINUTE", "1h": "ONE_HOUR"}


# ── Download ───────────────────────────────────────────────────────────────────

def download(
    interval: str,
    start:    str | None = None,
    end:      str | None = None,
    days:     int | None = None,
) -> pd.DataFrame:
    """
    Download USDINR=X candles from Yahoo Finance.

    Args:
        interval: "5m" or "1h"
        start:    ISO date string "YYYY-MM-DD" (optional)
        end:      ISO date string "YYYY-MM-DD" (optional)
        days:     fall-back period in days when start/end not given
    """
    max_days = _MAX_DAYS[interval]

    if start and end:
        print(f"[yfinance] Downloading {interval} USDINR=X  {start} → {end}...")
        df = yf.download(
            TICKER,
            start=start,
            end=end,
            interval=interval,
            auto_adjust=True,
            progress=False,
        )
    else:
        cap = min(days or max_days, max_days)
        if days and days > max_days:
            print(f"[WARN] yfinance {interval} limit is {max_days} days. Capping at {max_days}.")
        print(f"[yfinance] Downloading last {cap}d of {interval} USDINR=X...")
        df = yf.download(
            TICKER,
            period=f"{cap}d",
            interval=interval,
            auto_adjust=True,
            progress=False,
        )

    if df.empty:
        print("[ERROR] yfinance returned no data.")
        print("  Possible causes:")
        print("  - For 5m data: date range must be within last 60 days from today")
        print("  - For 1h data: date range must be within last 730 days from today")
        print("  - Check internet connection")
        sys.exit(1)

    # Flatten MultiIndex columns (yfinance sometimes returns these)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)

    df = df.rename(columns={
        "Open":   "open",
        "High":   "high",
        "Low":    "low",
        "Close":  "close",
        "Volume": "volume",
    })

    # Normalise index to IST-aware timestamps
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(IST)
    df.index.name = "timestamp"
    df = df.reset_index()

    df = df.dropna(subset=["open", "high", "low", "close"])
    df["volume"] = df["volume"].fillna(0).astype(int)

    print(
        f"[yfinance] Got {len(df)} {interval} candles  "
        f"({df['timestamp'].iloc[0].strftime('%Y-%m-%d')} to "
        f"{df['timestamp'].iloc[-1].strftime('%Y-%m-%d')})"
    )
    return df


# ── Seed ───────────────────────────────────────────────────────────────────────

def seed(df: pd.DataFrame, interval_label: str) -> int:
    """
    Upsert all candles into SQLite.  Returns number of new rows added.
    """
    init_db()
    count_before = count_candles()

    for _, row in df.iterrows():
        upsert_candle({
            "symbol":    SYMBOL,
            "interval":  interval_label,
            "timestamp": row["timestamp"].isoformat(),
            "open":      float(row["open"]),
            "high":      float(row["high"]),
            "low":       float(row["low"]),
            "close":     float(row["close"]),
            "volume":    int(row["volume"]),
        })

    added = count_candles() - count_before
    return added


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed SQLite DB with USDINR=X data from Yahoo Finance"
    )
    parser.add_argument(
        "--interval", choices=["5m", "15m", "1h"], default="15m",
        help="Candle size: '15m' (default, last 60 days), '5m' (last 60 days), or '1h' (up to 730 days)"
    )
    parser.add_argument(
        "--start", default=None,
        help="Start date YYYY-MM-DD (use with --end for exact range)"
    )
    parser.add_argument(
        "--end", default=None,
        help="End date YYYY-MM-DD (use with --start for exact range)"
    )
    parser.add_argument(
        "--days", type=int, default=None,
        help="Days of history to download (overrides default; capped by yfinance limit)"
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Print the last 10 candles after seeding"
    )
    args = parser.parse_args()

    # Validate: start requires end and vice versa
    if bool(args.start) != bool(args.end):
        print("[ERROR] --start and --end must be used together.")
        sys.exit(1)

    df = download(
        interval=args.interval,
        start=args.start,
        end=args.end,
        days=args.days,
    )

    interval_label = _INTERVAL_LABEL[args.interval]
    print(f"\n[DB] Seeding {interval_label} candles into SQLite...")
    added = seed(df, interval_label)
    total = count_candles()
    print(f"[DB] Done. Added {added} new candles | Total in DB: {total}")

    if args.show:
        print(f"\n[PREVIEW] Last 10 candles:")
        print(df.tail(10).to_string(index=False))

    print(f"\n  Run the backtest:")
    s = args.start or ""
    e = args.end   or ""
    if args.interval == "1h":
        print(f"    python scripts/backtest_offline.py --interval 1h --from {s} --to {e}")
        print()
        print("  NOTE: 1h candles — ORB window consumes full session, 0 entries expected.")
        print("    Use 15m or 5m for ARIA backtesting.")
    elif args.interval == "15m":
        print(f"    python scripts/backtest_offline.py --interval 15m --from {s} --to {e}")
    else:
        print(f"    python scripts/backtest_offline.py --interval 5m --from {s} --to {e}")


if __name__ == "__main__":
    main()
