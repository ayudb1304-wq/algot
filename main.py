"""
main.py — claudey-tr entry point
=================================
USDINR Mean Reversion Algo Trading Bot
Angel One SmartAPI + Claude AI (Haiku + Sonnet)

Usage:
    python main.py --check          Validate environment, database, and config
    python main.py --test-auth      (Phase 1) Test Angel One authentication
    python main.py --stream         (Phase 2) Stream live USDINR market data
    python main.py --signals        (Phase 3) Run strategy signal generator (no orders)
    python main.py --test-claude    (Phase 4) Test Claude MCP integration
    python main.py --paper          (Phase 6) Run full paper trading session
    python main.py --backtest       (Phase 7) Run 90-day historical backtest
"""

import argparse
import io
import sys

# Force UTF-8 output on Windows terminals
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from config.settings import (
    ANGEL_ONE_API_KEY,
    ANGEL_ONE_CLIENT_ID,
    ANGEL_ONE_PASSWORD,
    ANGEL_ONE_TOTP_SECRET,
    ANTHROPIC_API_KEY,
    ANGEL_ALGO_ID,
    DB_PATH,
    LOGS_DIR,
    REPORTS_DIR,
    TRADING_MODE,
    CAPITAL_INR,
    MAX_DAILY_LOSS_INR,
    MAX_OPS,
    CLAUDE_SIGNAL_MODEL,
    CLAUDE_BRIEFING_MODEL,
    CLAUDE_MAX_DAILY_CALLS,
    CLAUDE_MIN_CONFIDENCE,
    Z_ENTRY_THRESHOLD,
    Z_WINDOW,
    ADX_RANGING_MAX,
)
from core.audit.logger import get_logger
from core.audit.database import init_db, table_counts

log = get_logger("main")


# ── --check ───────────────────────────────────────────────────────────────────

def cmd_check() -> None:
    """Pre-flight: validate env vars, initialise DB, confirm paths are writable."""
    print()
    print("=" * 60)
    print("  claudey-tr  |  Pre-flight Check")
    print("=" * 60)

    all_ok = True

    # 1 — Environment variables
    print("\n[ENV]  Environment variables")
    env_checks = [
        ("ANGEL_ONE_API_KEY",     ANGEL_ONE_API_KEY),
        ("ANGEL_ONE_CLIENT_ID",   ANGEL_ONE_CLIENT_ID),
        ("ANGEL_ONE_PASSWORD",    ANGEL_ONE_PASSWORD),
        ("ANGEL_ONE_TOTP_SECRET", ANGEL_ONE_TOTP_SECRET),
        ("ANTHROPIC_API_KEY",     ANTHROPIC_API_KEY),
    ]
    for name, val in env_checks:
        ok = bool(val)
        icon = "✓" if ok else "✗"
        # Show only a masked preview — never log real credentials
        preview = (val[:4] + "···" + val[-2:]) if val and len(val) > 6 else ("—" if not val else val)
        status = "loaded" if ok else "MISSING ← add to .env"
        print(f"  {icon}  {name:<28} {preview:<14} {status}")
        if not ok:
            all_ok = False

    # Optional: ANGEL_ALGO_ID (not required during paper trading)
    algo_id_status = f"set ({ANGEL_ALGO_ID[:6]}···)" if ANGEL_ALGO_ID else "not set (required for LIVE trading)"
    algo_icon = "✓" if ANGEL_ALGO_ID else "!"
    print(f"  {algo_icon}  {'ANGEL_ALGO_ID':<28} {'—':<14} {algo_id_status}")

    # 2 — Database
    print(f"\n[DB]   SQLite database")
    try:
        init_db()
        counts = table_counts()
        print(f"  ✓  Schema initialised at: {DB_PATH}")
        print(f"  ✓  Tables ({len(counts)}):")
        for table, count in counts.items():
            print(f"       {'·'} {table:<20} {count} rows")
    except Exception as exc:
        print(f"  ✗  Database error: {exc}")
        all_ok = False

    # 3 — File paths
    print(f"\n[PATH] Runtime directories")
    path_checks = [
        ("DB",      DB_PATH.parent,  DB_PATH.parent.exists()),
        ("Logs",    LOGS_DIR,        LOGS_DIR.exists()),
        ("Reports", REPORTS_DIR,     REPORTS_DIR.exists()),
    ]
    for label, path, exists in path_checks:
        icon = "✓" if exists else "✗"
        print(f"  {icon}  {label:<10} {path}")
        if not exists:
            all_ok = False

    # 4 — Active configuration
    print(f"\n[CFG]  Active configuration")
    print(f"  {'Trading mode':<26} {TRADING_MODE.upper()}")
    print(f"  {'Capital':<26} ₹{CAPITAL_INR:,.0f}")
    print(f"  {'Max daily loss':<26} ₹{MAX_DAILY_LOSS_INR:,.0f}  (kill switch)")
    print(f"  {'Max OPS':<26} {MAX_OPS}  (SEBI limit: 10)")
    print(f"  {'Z-score entry threshold':<26} ±{Z_ENTRY_THRESHOLD}  (window: {Z_WINDOW} periods)")
    print(f"  {'ADX ranging max':<26} {ADX_RANGING_MAX}  (strategy pauses above 25)")
    print(f"  {'Claude signal model':<26} {CLAUDE_SIGNAL_MODEL}")
    print(f"  {'Claude briefing model':<26} {CLAUDE_BRIEFING_MODEL}")
    print(f"  {'Claude daily call cap':<26} {CLAUDE_MAX_DAILY_CALLS} Haiku calls/day")
    print(f"  {'Claude min confidence':<26} {CLAUDE_MIN_CONFIDENCE} / 100")

    # 5 — Logger
    print(f"\n[LOG]  Logger")
    log.info("Pre-flight logger check passed")
    print(f"  ✓  Console handler active")
    print(f"  ✓  JSON file handler active → {LOGS_DIR}")

    # Final verdict
    print()
    print("═" * 60)
    if all_ok:
        print("  ✓  All systems ready.")
        print()
        print("  Next step: run  python main.py --test-auth  (Phase 1)")
    else:
        print("  ✗  One or more checks FAILED. Fix the items above before proceeding.")
    print("═" * 60)
    print()

    if not all_ok:
        sys.exit(1)


# ── Phase stubs (implemented in later phases) ─────────────────────────────────

def cmd_test_auth() -> None:
    """Phase 1: Test the full Angel One authentication cycle."""
    print()
    print("=" * 60)
    print("  claudey-tr  |  Phase 1 — Authentication Test")
    print("=" * 60)

    from core.auth.angel_auth import get_profile, login, logout

    print("\n[AUTH] Generating TOTP and calling Angel One...")
    try:
        session = login()
    except RuntimeError as exc:
        print(f"\n  [FAIL] {exc}")
        sys.exit(1)

    print(f"  ✓  Login successful")
    print(f"  ✓  Session ID:   {session.session_id}")
    print(f"  ✓  Public IP:    {session.public_ip}")
    print(f"  ✓  JWT prefix:   {session.jwt_token[:14]}...")
    print(f"  ✓  Feed token:   {session.feed_token[:8]}...")

    print("\n[AUTH] Fetching account profile...")
    profile = get_profile(session)
    if profile:
        print(f"  ✓  Name:         {profile.get('name', 'N/A')}")
        print(f"  ✓  Client code:  {profile.get('clientcode', 'N/A')}")
        print(f"  ✓  Email:        {profile.get('email', 'N/A')}")
    else:
        print("  !  Profile fetch returned empty (login still valid)")

    print("\n[AUTH] Logging out...")
    logout(session)
    print("  ✓  Logout complete — session marked closed in DB")

    print("\n[AUTH] Verifying DB record...")
    from core.audit.database import get_connection
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id=?", (session.session_id,)
        ).fetchone()
    print(f"  ✓  sessions[{session.session_id}].status = '{row['status']}'")
    print(f"  ✓  logout_time   = {row['logout_time']}")
    print(f"  ✓  token stored  = '{row['token_hash']}' (prefix only, not full JWT)")

    print()
    print("=" * 60)
    print("  ✓  Phase 1 auth test PASSED.")
    print("  Next step: python main.py --stream  (Phase 2)")
    print("=" * 60)
    print()


def cmd_stream(args) -> None:
    """Phase 2: Stream live USDINR data, backfill candles, poll news."""
    import time as _time

    import core.auth.session_manager as _sm
    from core.data.historical import backfill, count_candles, fetch_today
    from core.data.market_feed import (
        MarketFeed,
        is_market_hours,
        is_rbi_window,
        minutes_until_rbi_window,
    )
    from core.data.news_feed import NewsFeed, latest_headline, latest_headline_age_minutes
    from core.audit.database import init_db

    init_db()

    print()
    print("=" * 60)
    print("  claudey-tr  |  Phase 2 — Market Data Stream")
    print("=" * 60)

    # ── Auth ──────────────────────────────────────────────────────
    print("\n[AUTH] Logging in to Angel One...")
    session = _sm.manual_login()      # registers session globally for all modules
    print(f"  ✓  Authenticated | IP: {session.public_ip}")

    # ── Historical backfill ───────────────────────────────────────
    existing = count_candles()
    if existing < 100:
        print(f"\n[DATA] Only {existing} candles in DB — running 90-day backfill...")
        print("       (this makes ~3 API calls, takes ~5 seconds)")
        n = backfill(days=90)
        print(f"  ✓  Backfill complete | {n} candles fetched | total: {count_candles()}")
    else:
        print(f"\n[DATA] {existing} candles already in DB — fetching today's data...")
        n = fetch_today()
        print(f"  ✓  Today's candles fetched | {n} new | total: {count_candles()}")

    # ── News feed ─────────────────────────────────────────────────
    print("\n[NEWS] Starting news feed (RBI + Economic Times)...")
    news_feed = NewsFeed()
    news_feed.start()
    _time.sleep(2)    # let the initial poll complete
    headline = latest_headline()
    age      = latest_headline_age_minutes()
    if headline:
        age_str = f"{age} min ago" if age is not None else "just now"
        print(f"  ✓  Latest: \"{headline[:65]}...\" ({age_str})")
    else:
        print("  !  No news stored yet (feeds may be unreachable or empty)")

    # ── WebSocket ─────────────────────────────────────────────────
    if not is_market_hours():
        print("\n[FEED] Market is CLOSED (09:00–15:30 IST).")
        print("       WebSocket will connect but may not receive live ticks.")
        print("       Run during market hours for live data.\n")

    print("\n[FEED] Connecting WebSocket (USDINR Snap Quote mode 3)...")
    feed = MarketFeed()
    feed.start(session)
    _time.sleep(3)    # allow connection + subscription to complete

    # ── Stream loop ───────────────────────────────────────────────
    timeout  = args.timeout if hasattr(args, "timeout") else 0
    deadline = _time.time() + timeout if timeout else None

    print("\n[STREAM] Live feed active. Press Ctrl+C to stop.\n")
    print("-" * 60)

    last_tick_count = 0
    stale_seconds   = 0

    try:
        while True:
            tick         = feed.get_latest_tick()
            rbi_status   = "ACTIVE  ***AVOID TRADING***" if is_rbi_window() else f"inactive (opens in {minutes_until_rbi_window()} min)"
            candle_count = count_candles()
            news_headline = latest_headline()
            news_age      = latest_headline_age_minutes()

            # Detect a dead WebSocket (no new ticks for 30s during market hours)
            current_tick_count = feed.tick_count()
            if current_tick_count == last_tick_count:
                stale_seconds += 2
            else:
                stale_seconds = 0
            last_tick_count = current_tick_count

            if tick:
                stale_note = f"  *** NO NEW TICKS {stale_seconds}s — feed may be down ***" if stale_seconds >= 30 else ""
                print(
                    f"  USDINR | "
                    f"Bid: {tick.get('bid', 0):.4f}  "
                    f"Ask: {tick.get('ask', 0):.4f}  "
                    f"LTP: {tick.get('ltp', 0):.4f}  "
                    f"Vol: {tick.get('volume', 0):,}  "
                    f"[raw={tick.get('raw_ltp', 0)}]{stale_note}"
                )
            else:
                print("  USDINR | Waiting for first tick...")

            print(f"  RBI window : {rbi_status}")
            print(f"  Candles DB : {candle_count} bars (15-min)")
            if news_headline:
                age_str = f"{news_age} min ago" if news_age is not None else "?"
                print(f"  Last news  : \"{news_headline[:55]}...\" ({age_str})")
            print()
            sys.stdout.flush()

            if deadline and _time.time() >= deadline:
                print(f"[STREAM] Timeout reached ({timeout}s). Stopping.")
                break

            _time.sleep(2)

    except KeyboardInterrupt:
        print("\n[STREAM] Interrupted by user.")

    # ── Cleanup ───────────────────────────────────────────────────
    news_feed.stop()
    feed.stop()
    _sm.manual_logout()
    print("\n  ✓  Feed stopped, session closed.\n")


def cmd_signals(args) -> None:
    """Phase 3: Stream live USDINR data and print ARIA strategy signals (no orders)."""
    import time as _time

    import core.auth.session_manager as _sm
    from core.audit.database import init_db, count_candles
    from core.data.historical import backfill, fetch_today
    from core.data.market_feed import MarketFeed, is_market_hours
    from core.data.news_feed import NewsFeed
    from core.strategy.regime_adaptive import ARIAStrategy

    init_db()

    print()
    print("=" * 60)
    print("  claudey-tr  |  Phase 3 — ARIA Signal Engine")
    print("=" * 60)

    # ── Auth ──────────────────────────────────────────────────────
    print("\n[AUTH] Logging in to Angel One...")
    session = _sm.manual_login()
    print(f"  ✓  Authenticated | IP: {session.public_ip}")

    # ── Historical data ───────────────────────────────────────────
    from config.settings import CANDLE_INTERVAL
    existing = count_candles(interval=CANDLE_INTERVAL)
    if existing < 200:
        print(f"\n[DATA] Only {existing} {CANDLE_INTERVAL} candles — running backfill...")
        n = backfill(days=60)
        print(f"  ✓  Backfill done | {n} candles fetched | total: {count_candles(interval=CANDLE_INTERVAL)}")
    else:
        n = fetch_today()
        print(f"\n[DATA] {count_candles(interval=CANDLE_INTERVAL)} {CANDLE_INTERVAL} candles in DB | {n} new today")

    # ── News feed ─────────────────────────────────────────────────
    print("\n[NEWS] Starting news feed...")
    news_feed = NewsFeed()
    news_feed.start()

    # ── Strategy engine ───────────────────────────────────────────
    strategy = ARIAStrategy()
    _last_signal_ts = [None]   # mutable container for closure

    def _on_tick(tick: dict) -> None:
        """Called on every WebSocket tick — evaluate ARIA strategy."""
        ltp    = tick.get("ltp", 0.0)
        volume = tick.get("volume", 0)
        signal = strategy.evaluate(ltp=ltp, volume=volume)
        if signal is None:
            return
        _last_signal_ts[0] = tick.get("timestamp")
        icon = "▶" if signal.action in ("LONG", "SHORT") else ("✗" if signal.action == "EXIT" else "·")
        print(f"\n  [{icon}] SIGNAL: {signal.action}  "
              f"Mode={signal.strategy_mode or 'n/a'}  "
              f"@ {signal.ltp:.4f}")
        print(f"       Z={signal.z_score:+.3f}  ADX={signal.adx:.1f}  "
              f"RSI={signal.rsi:.1f}  ATR={signal.atr:.5f}  Regime={signal.regime}")
        if signal.action in ("LONG", "SHORT"):
            print(f"       Stop={signal.stop_price:.4f}  "
                  f"Target={signal.target_price:.4f if signal.target_price else 'Z-exit'}")
        if signal.filters_passed:
            print(f"       Passed : {', '.join(signal.filters_passed)}")
        if signal.filters_failed:
            print(f"       Blocked: {', '.join(signal.filters_failed)}")
        if signal.orb_high:
            print(f"       ORB    : {signal.orb_low:.4f} – {signal.orb_high:.4f}  "
                  f"width={signal.orb_high - signal.orb_low:.4f}")
        if signal.action in ("LONG", "SHORT"):
            print(f"       → Awaiting Claude validation (Phase 4)")
        sys.stdout.flush()

    # ── WebSocket ─────────────────────────────────────────────────
    if not is_market_hours():
        print("\n[FEED] Market is CLOSED — signals evaluated on stale candles.")

    print("\n[FEED] Connecting WebSocket...")
    feed = MarketFeed()
    feed.add_tick_callback(_on_tick)
    feed.start(session)
    _time.sleep(3)

    # ── Stream loop ───────────────────────────────────────────────
    timeout  = args.timeout if hasattr(args, "timeout") else 0
    deadline = _time.time() + timeout if timeout else None

    print("\n[SIGNALS] ARIA engine active. Press Ctrl+C to stop.\n")
    print("-" * 60)

    last_tick_count = 0
    stale_seconds   = 0

    try:
        while True:
            tick    = feed.get_latest_tick()
            pos     = strategy.position_side or "FLAT"
            regime  = strategy.day_regime    or "unknown"
            orb     = strategy.orb

            current_tc = feed.tick_count()
            if current_tc == last_tick_count:
                stale_seconds += 5
            else:
                stale_seconds = 0
            last_tick_count = current_tc

            if tick:
                stale = f"  *** NO NEW TICKS {stale_seconds}s ***" if stale_seconds >= 30 else ""
                orb_str = (f"built ({orb.low:.4f}–{orb.high:.4f})"
                           if orb.is_built else f"building ({orb.candles_seen}/{4} candles)")
                print(
                    f"  LTP: {tick.get('ltp', 0):.4f}  "
                    f"Bid: {tick.get('bid', 0):.4f}  "
                    f"Ask: {tick.get('ask', 0):.4f}  "
                    f"| Regime: {regime}  ORB: {orb_str}  Pos: {pos}{stale}"
                )
            else:
                print(f"  Waiting for first tick...")

            sys.stdout.flush()

            if deadline and _time.time() >= deadline:
                print(f"\n[SIGNALS] Timeout reached ({timeout}s). Stopping.")
                break
            _time.sleep(5)

    except KeyboardInterrupt:
        print("\n[SIGNALS] Interrupted by user.")

    news_feed.stop()
    feed.stop()
    _sm.manual_logout()
    print("\n  ✓  Feed stopped, session closed.\n")


def _not_yet(flag: str, phase: str) -> None:
    print(f"\n  '{flag}' will be available after {phase} is complete.")
    print(f"  Check IMPLEMENTATION.md for current phase status.\n")
    sys.exit(0)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="claudey-tr",
        description="USDINR Mean Reversion Algo Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate environment, database, and configuration",
    )
    parser.add_argument(
        "--test-auth",
        action="store_true",
        help="(Phase 1) Test Angel One TOTP authentication",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="(Phase 2) Stream live USDINR market data via WebSocket",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="Auto-stop after N seconds (use with --stream for testing; 0 = run until Ctrl+C)",
    )
    parser.add_argument(
        "--signals",
        action="store_true",
        help="(Phase 3) Run strategy engine in signal-only mode (no orders)",
    )
    parser.add_argument(
        "--test-claude",
        action="store_true",
        help="(Phase 4) Test Claude MCP integration end-to-end",
    )
    parser.add_argument(
        "--paper",
        action="store_true",
        help="(Phase 6) Run a full paper trading session",
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="(Phase 7) Run 90-day historical backtest and print report",
    )

    args = parser.parse_args()

    if args.check:
        cmd_check()
    elif args.test_auth:
        cmd_test_auth()
    elif args.stream:
        cmd_stream(args)
    elif args.signals:
        cmd_signals(args)
    elif args.test_claude:
        _not_yet("--test-claude", "Phase 4")
    elif args.paper:
        _not_yet("--paper", "Phase 6")
    elif args.backtest:
        _not_yet("--backtest", "Phase 7")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
