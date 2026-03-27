"""
scripts/backtest_offline.py
============================
Walk historical USDINR candles stored in SQLite and replay the ARIA
(Adaptive Regime Intraday Algo) strategy signal engine — no Angel One
API calls, no live orders.

What this measures:
  - Regime breakdown: how many TRENDING vs RANGING vs NEUTRAL days
  - Trades generated per mode (TRENDING_ORB vs RANGING_ZSCORE)
  - Win rate, avg win, avg loss, net P&L after brokerage
  - Exit reason breakdown (target_hit, z_revert, stop_loss, time_exit, eod)

Backtest-specific handling:
  - Candle timestamp passed to strategy.evaluate() for accurate ORB timing
  - is_rbi_window() patched to False (replaying history, not live)
  - ORB and daily counters reset automatically on date boundaries
  - Stop/target checked at each candle close (conservative — no intra-candle fill)

Usage:
    python scripts/backtest_offline.py
    python scripts/backtest_offline.py --from 2026-01-05 --to 2026-03-27
    python scripts/backtest_offline.py --verbose
    python scripts/backtest_offline.py --interval 1h --from 2024-01-01 --to 2025-06-30
"""

import argparse
import io
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import logging
logging.disable(logging.CRITICAL)

import pandas as pd
import pytz

from core.audit.database import count_candles, init_db
from core.data.historical import get_candles_for_backtest
from core.strategy.regime_adaptive import ARIAStrategy

IST          = pytz.timezone("Asia/Kolkata")
LOT_SIZE     = 1000    # 1 USDINR lot = 1000 USD
BROKERAGE    = 20.0    # ₹20 per order (entry + exit = ₹40/trade)
CANDLE_FETCH = 234     # must be ≥ EMA_DIRECTION_SPAN(200) + warmup; matches _CANDLE_FETCH in ARIA


# ── Trade record ───────────────────────────────────────────────────────────────

@dataclass
class Trade:
    side:          str
    entry_time:    datetime
    entry_price:   float
    entry_z:       float
    entry_adx:     float
    stop_price:    float
    target_price:  Optional[float]
    strategy_mode: str             # "TRENDING_ORB" | "RANGING_ZSCORE"
    exit_time:     Optional[datetime] = None
    exit_price:    Optional[float]    = None
    exit_reason:   str                = ""
    candles_held:  int                = 0
    gross_pnl:     float              = 0.0
    net_pnl:       float              = 0.0

    def close(
        self,
        exit_price: float,
        exit_time:  datetime,
        reason:     str,
        candles_held: int,
    ) -> None:
        self.exit_price   = exit_price
        self.exit_time    = exit_time
        self.exit_reason  = reason
        self.candles_held = candles_held
        if self.side == "LONG":
            self.gross_pnl = (exit_price - self.entry_price) * LOT_SIZE
        else:
            self.gross_pnl = (self.entry_price - exit_price) * LOT_SIZE
        self.net_pnl = self.gross_pnl - (2 * BROKERAGE)

    @property
    def is_win(self) -> bool:
        return self.net_pnl > 0


# ── Backtest engine ────────────────────────────────────────────────────────────

def run_backtest(df: pd.DataFrame, verbose: bool = False) -> List[Trade]:
    """
    Walk the candle DataFrame candle-by-candle and replay ARIA.
    Returns a list of completed Trade records.
    """
    strategy       = ARIAStrategy()
    trades:         List[Trade]      = []
    open_trade:     Optional[Trade]  = None
    entry_candle_i: int              = 0

    start_i = CANDLE_FETCH  # skip warmup period

    for i in range(start_i, len(df)):
        candle = df.iloc[i]
        ts     = candle["timestamp"]          # already IST datetime
        close  = float(candle["close"])
        volume = int(candle["volume"])

        # Window visible to strategy at candle i — no lookahead
        window = df.iloc[max(0, i - CANDLE_FETCH + 1) : i + 1].copy()
        window = window.reset_index(drop=True)

        # Patch get_latest_candles → return the correct historical window
        # Patch is_rbi_window → always False (not replaying live market hours check)
        with patch(
            "core.strategy.regime_adaptive.get_latest_candles",
            return_value=window,
        ), patch(
            "core.strategy.regime_adaptive.is_rbi_window",
            return_value=False,
        ):
            signal = strategy.evaluate(ltp=close, volume=volume, ts=ts)

        if signal is None:
            continue

        # ── Handle EXIT ────────────────────────────────────────────────────────
        if signal.action == "EXIT" and open_trade is not None:
            reason = _exit_reason(signal)
            candles_held = i - entry_candle_i
            open_trade.close(close, ts, reason, candles_held)
            trades.append(open_trade)
            strategy.on_position_close()
            open_trade = None

            if verbose:
                t = trades[-1]
                pnl_str = f"+{t.net_pnl:.0f}" if t.net_pnl >= 0 else f"{t.net_pnl:.0f}"
                print(
                    f"  EXIT  {t.side:<5} {t.exit_time.strftime('%m-%d %H:%M')}  "
                    f"@ {t.exit_price:.4f}  pnl=₹{pnl_str}  "
                    f"held={candles_held}  reason={reason}"
                )

        # ── Handle LONG / SHORT entry ──────────────────────────────────────────
        elif signal.action in ("LONG", "SHORT") and open_trade is None:
            stop   = signal.stop_price   if signal.stop_price   is not None else 0.0
            target = signal.target_price  # None is valid for RANGING mode
            open_trade = Trade(
                side=signal.action,
                entry_time=ts,
                entry_price=close,
                entry_z=signal.z_score,
                entry_adx=signal.adx,
                stop_price=stop,
                target_price=target,
                strategy_mode=signal.strategy_mode,
            )
            entry_candle_i = i
            strategy.on_position_open(
                side=signal.action,
                entry_price=close,
                stop=stop,
                target=target,
                mode=signal.strategy_mode,
            )

            if verbose:
                tgt_str = f"{target:.4f}" if target is not None else "z_rev"
                print(
                    f"  ENTRY {signal.action:<5} {ts.strftime('%m-%d %H:%M')}  "
                    f"@ {close:.4f}  Z={signal.z_score:+.3f}  "
                    f"ADX={signal.adx:.1f}  mode={signal.strategy_mode}  "
                    f"stop={stop:.4f}  target={tgt_str}"
                )

        elif signal.action == "SKIP" and verbose:
            print(
                f"  SKIP        {ts.strftime('%m-%d %H:%M')}  "
                f"mode={signal.strategy_mode}  "
                f"blocked=[{', '.join(signal.filters_failed)}]"
            )

    # Force-close any position still open at end of data
    if open_trade is not None:
        last         = df.iloc[-1]
        candles_held = len(df) - 1 - entry_candle_i
        open_trade.close(
            float(last["close"]),
            last["timestamp"],
            "data_end",
            candles_held,
        )
        trades.append(open_trade)
        if verbose:
            print(f"  FORCE CLOSE at data end @ {open_trade.exit_price:.4f}")

    return trades


def _exit_reason(signal) -> str:
    fp = signal.filters_passed
    if "stop_loss"   in fp: return "stop_loss"
    if "target_hit"  in fp: return "target_hit"
    if "z_exit"      in fp: return "z_revert"
    if "time_exit"   in fp: return "time_exit"
    if "eod_exit"    in fp: return "eod"
    return "data_end"


# ── Report ─────────────────────────────────────────────────────────────────────

def print_report(trades: List[Trade], df: pd.DataFrame, candle_label: str = "5-min") -> None:
    print()
    print("=" * 66)
    print("  OFFLINE BACKTEST REPORT — USDINR  |  ARIA Strategy")
    print("=" * 66)

    if not trades:
        print("\n  No trades generated.")
        print("  Possible reasons:")
        print("  - Market hours outside 9:15 AM–12:00 PM in dataset")
        print("  - ADX consistently in NEUTRAL band (18–25) → sit-out days")
        print("  - Z-score never exceeded ±2.5 (RANGING mode)")
        print("  - No ORB breakout + momentum confirmation (TRENDING mode)")
        return

    wins   = [t for t in trades if t.is_win]
    losses = [t for t in trades if not t.is_win]
    total_gross = sum(t.gross_pnl for t in trades)
    total_net   = sum(t.net_pnl   for t in trades)
    total_brok  = len(trades) * 2 * BROKERAGE

    print(f"\n  Period    : {df['timestamp'].iloc[0].strftime('%Y-%m-%d')} to "
          f"{df['timestamp'].iloc[-1].strftime('%Y-%m-%d')}")
    print(f"  Candles   : {len(df)} x {candle_label} bars")
    print(f"  Lot size  : {LOT_SIZE} USD  |  Brokerage: ₹{BROKERAGE}/order")

    print(f"\n  {'Trades':<24} {len(trades)}")
    print(f"  {'Wins':<24} {len(wins)}  ({100*len(wins)/len(trades):.0f}%)")
    print(f"  {'Losses':<24} {len(losses)}  ({100*len(losses)/len(trades):.0f}%)")

    avg_held = sum(t.candles_held for t in trades) / len(trades)
    avg_z    = sum(abs(t.entry_z)  for t in trades) / len(trades)
    avg_adx  = sum(t.entry_adx     for t in trades) / len(trades)
    print(f"  {'Avg candles held':<24} {avg_held:.1f}  ({candle_label} each)")
    print(f"  {'Avg |Z| at entry':<24} {avg_z:.3f}")
    print(f"  {'Avg ADX at entry':<24} {avg_adx:.1f}")

    print(f"\n  {'Gross P&L':<24} ₹{total_gross:,.0f}")
    print(f"  {'Total brokerage':<24} ₹{total_brok:,.0f}")
    print(f"  {'Net P&L (w/ brok.)':<24} ₹{total_net:,.0f}")
    if wins:
        print(f"  {'Avg win':<24} ₹{sum(t.net_pnl for t in wins)/len(wins):,.0f}")
    if losses:
        print(f"  {'Avg loss':<24} ₹{sum(t.net_pnl for t in losses)/len(losses):,.0f}")
    if wins and losses:
        rr = abs(sum(t.net_pnl for t in wins)/len(wins)) / abs(sum(t.net_pnl for t in losses)/len(losses))
        print(f"  {'Avg win/loss ratio':<24} {rr:.2f}×")

    # Mode breakdown
    orb_trades = [t for t in trades if t.strategy_mode == "TRENDING_ORB"]
    z_trades   = [t for t in trades if t.strategy_mode == "RANGING_ZSCORE"]
    print(f"\n  Strategy mode breakdown:")
    if orb_trades:
        orb_net = sum(t.net_pnl for t in orb_trades)
        orb_wins = sum(1 for t in orb_trades if t.is_win)
        print(f"    TRENDING_ORB   : {len(orb_trades):>3} trades  "
              f"{orb_wins}W/{len(orb_trades)-orb_wins}L  net ₹{orb_net:,.0f}")
    if z_trades:
        z_net  = sum(t.net_pnl for t in z_trades)
        z_wins = sum(1 for t in z_trades if t.is_win)
        print(f"    RANGING_ZSCORE : {len(z_trades):>3} trades  "
              f"{z_wins}W/{len(z_trades)-z_wins}L  net ₹{z_net:,.0f}")

    # Exit reasons
    reasons: dict = {}
    for t in trades:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
    print(f"\n  Exit reasons:")
    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"    {reason:<18} {count}")

    # Side breakdown
    longs  = [t for t in trades if t.side == "LONG"]
    shorts = [t for t in trades if t.side == "SHORT"]
    print(f"\n  LONG  trades : {len(longs)}  "
          f"(net ₹{sum(t.net_pnl for t in longs):,.0f})")
    print(f"  SHORT trades : {len(shorts)}  "
          f"(net ₹{sum(t.net_pnl for t in shorts):,.0f})")

    # Trade log
    print(f"\n  {'#':<3} {'Side':<6} {'Mode':<15} {'Entry':>10} {'Exit':>10} "
          f"{'Entry@':>8} {'Exit@':>8} {'Z':>6} {'Held':>5} {'Net P&L':>9} {'Reason'}")
    print("  " + "-" * 94)
    for n, t in enumerate(trades, 1):
        entry_str = t.entry_time.strftime("%m-%d %H:%M")
        exit_str  = t.exit_time.strftime("%m-%d %H:%M") if t.exit_time else "open"
        pnl_str   = f"₹{t.net_pnl:+,.0f}"
        mode_short = "ORB" if t.strategy_mode == "TRENDING_ORB" else "Z-REV"
        print(
            f"  {n:<3} {t.side:<6} {mode_short:<15} {entry_str:>10} {exit_str:>10} "
            f"{t.entry_price:>8.4f} {(t.exit_price or 0):>8.4f} "
            f"{t.entry_z:>+6.2f} {t.candles_held:>5} {pnl_str:>9} {t.exit_reason}"
        )

    print()
    verdict = "PROFITABLE ✓" if total_net > 0 else "UNPROFITABLE"
    print(f"  Verdict: {verdict}  (net ₹{total_net:+,.0f} on {len(trades)} trades)")
    print("=" * 66)
    print()


# ── Entry point ────────────────────────────────────────────────────────────────

_INTERVAL_MAP = {
    "5m":  "FIVE_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "1h":  "ONE_HOUR",
}
_CANDLE_LABEL = {
    "5m":  "5-min",
    "15m": "15-min",
    "1h":  "1-hour",
}
_CANDLE_MINUTES = {
    "5m":  5,
    "15m": 15,
    "1h":  60,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline ARIA backtest using candles in SQLite DB"
    )
    parser.add_argument(
        "--interval", choices=["5m", "15m", "1h"], default="15m",
        help="Candle size to backtest: '15m' (default), '5m', or '1h'"
    )
    parser.add_argument("--from", dest="from_date", default=None,
                        help="Start date YYYY-MM-DD")
    parser.add_argument("--to",   dest="to_date",   default=None,
                        help="End date YYYY-MM-DD")
    parser.add_argument("--verbose", action="store_true",
                        help="Print every signal as it fires")
    args = parser.parse_args()

    interval_label = _INTERVAL_MAP[args.interval]
    candle_label   = _CANDLE_LABEL[args.interval]

    init_db()

    total = count_candles()
    if total < CANDLE_FETCH + 10:
        print(f"\n[ERROR] Only {total} candles in DB — need at least {CANDLE_FETCH + 10}.")
        print("  Run first:  python scripts/seed_from_yfinance.py")
        sys.exit(1)

    if args.from_date or args.to_date:
        from_dt = (
            IST.localize(datetime.strptime(args.from_date, "%Y-%m-%d"))
            if args.from_date else datetime(2000, 1, 1, tzinfo=IST)
        )
        to_dt = (
            IST.localize(datetime.strptime(args.to_date, "%Y-%m-%d").replace(
                hour=23, minute=59))
            if args.to_date else datetime(2100, 1, 1, tzinfo=IST)
        )
    else:
        from_dt = datetime(2000, 1, 1, tzinfo=IST)
        to_dt   = datetime(2100, 1, 1, tzinfo=IST)

    df = get_candles_for_backtest(from_dt, to_dt, interval=interval_label)
    if df.empty:
        print(f"[ERROR] No {args.interval} candles found for the requested date range.")
        if args.interval == "1h":
            print("  Run first:  python scripts/seed_from_yfinance.py --interval 1h --start YYYY-MM-DD --end YYYY-MM-DD")
        else:
            print("  Run first:  python scripts/seed_from_yfinance.py")
        sys.exit(1)

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(IST)

    print(f"\n[ARIA BACKTEST] Interval: {candle_label}  |  Loaded {len(df)} candles | "
          f"{df['timestamp'].iloc[0].strftime('%Y-%m-%d')} to "
          f"{df['timestamp'].iloc[-1].strftime('%Y-%m-%d')}")
    if args.interval == "1h":
        print(f"[ARIA BACKTEST] NOTE: 1h mode — Z_WINDOW=96 means 4-day lookback, TIME_EXIT=8 means 8h hold")
    print(f"[ARIA BACKTEST] Running strategy replay...\n")

    if args.verbose:
        print("-" * 66)

    trades = run_backtest(df, verbose=args.verbose)

    if args.verbose:
        print("-" * 66)

    print_report(trades, df, candle_label=candle_label)


if __name__ == "__main__":
    main()
