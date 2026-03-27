"""
config/settings.py
==================
Central configuration for claudey-tr.
Loads all environment variables, validates they are present,
and exports typed constants used throughout the application.
"""

import os
from datetime import time
from pathlib import Path

import pytz
from dotenv import load_dotenv

# ── Project root & .env ───────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# ── Validate required environment variables ───────────────────────────────────
_REQUIRED_VARS = [
    "ANGEL_ONE_API_KEY",
    "ANGEL_ONE_CLIENT_ID",
    "ANGEL_ONE_PASSWORD",
    "ANGEL_ONE_TOTP_SECRET",
    "ANTHROPIC_API_KEY",
]


def _load_env() -> dict:
    """Load and validate all required env vars. Raises on missing."""
    values = {}
    missing = []
    for var in _REQUIRED_VARS:
        val = os.getenv(var)
        if not val:
            missing.append(var)
        values[var] = val or ""
    if missing:
        raise EnvironmentError(
            f"\n[ERROR] Missing required environment variables:\n"
            + "\n".join(f"  - {v}" for v in missing)
            + f"\n\nCheck your .env file at: {ENV_PATH}"
        )
    return values


_env = _load_env()

# ── Angel One credentials ─────────────────────────────────────────────────────
ANGEL_ONE_API_KEY     = _env["ANGEL_ONE_API_KEY"]
ANGEL_ONE_CLIENT_ID   = _env["ANGEL_ONE_CLIENT_ID"]
ANGEL_ONE_PASSWORD    = _env["ANGEL_ONE_PASSWORD"]
ANGEL_ONE_TOTP_SECRET = _env["ANGEL_ONE_TOTP_SECRET"]

# ── Anthropic credentials ─────────────────────────────────────────────────────
ANTHROPIC_API_KEY = _env["ANTHROPIC_API_KEY"]

# ── Algo ID (provided by Angel One after SEBI registration) ──────────────────
# Leave empty during paper trading. Required for live trading post April 1 2026.
ANGEL_ALGO_ID = os.getenv("ANGEL_ALGO_ID", "")

# ── Timezone ──────────────────────────────────────────────────────────────────
IST = pytz.timezone("Asia/Kolkata")

# ── Market session timings (all IST) ─────────────────────────────────────────
MARKET_OPEN       = time(9, 0)
MARKET_CLOSE      = time(15, 30)
SQUARE_OFF_TIME   = time(15, 15)    # force-close all open positions
SESSION_LOGIN_AT  = time(8, 50)     # automated TOTP login before open
SESSION_LOGOUT_AT = time(23, 59)    # mandatory daily logout (SEBI)

# ── RBI Reference Rate polling window ────────────────────────────────────────
# High structural risk: no new entries, reduce size to 0 during this window.
RBI_WINDOW_START = time(11, 30)
RBI_WINDOW_END   = time(12, 30)

# ── Instrument ────────────────────────────────────────────────────────────────
SYMBOL          = "USDINR"
TOKEN           = "1196"          # Angel One instrument token for USDINR April 2026 monthly (USDINR26APRFUT)
                                  # Roll to next month's token on last Thursday of each month
EXCHANGE        = "CDS"           # Currency Derivatives Segment
CANDLE_INTERVAL = "FIFTEEN_MINUTE"
CANDLE_MINUTES  = 15              # minutes per candle — used for ORB window maths

# ── ARIA strategy parameters — Adaptive Regime Intraday Algo ─────────────────
# Shared (both modes)
Z_WINDOW          = 96     # Z-score lookback: 96 × 15-min = 24-hour rolling window
Z_ENTRY_THRESHOLD = 2.5    # RANGING mode: |Z| must exceed this to enter
Z_EXIT_THRESHOLD  = 0.3    # RANGING mode: |Z| below this → exit
ADX_RANGING_MAX   = 18     # ADX < 18  → RANGING  (Z-score reversion active)
ADX_TRENDING_MIN  = 25     # ADX > 25  → TRENDING (ORB breakout active)
                            # 18 ≤ ADX ≤ 25 → NEUTRAL (sit out today)
TIME_EXIT_CANDLES = 8      # Max hold: 8 candles × 15 min = 2 hours
ATR_MULTIPLIER    = 1.5    # ATR spike filter: skip entry if ATR > 1.5× rolling mean
VOLUME_THRESHOLD  = 0.50   # Volume filter: skip if vol < 50% of 5-candle avg

# ARIA-specific
ORB_CANDLES           = 4      # first N × 15-min candles build Opening Range (1 hour, 9:00–10:00)
ORB_MIN_BREAKOUT_ATR  = 0.5    # ORB breakout must clear ORB high/low by 0.5 × ATR(10)
ENTRY_SESSION_END     = time(12, 0)   # no new entries after 12:00 PM IST
MAX_DAILY_TRADES      = 2      # max trades per session — quality over quantity
EMA_FAST_SPAN         = 9      # fast EMA for short-term momentum confirmation
EMA_SLOW_SPAN         = 21     # slow EMA for short-term momentum confirmation
EMA_DIRECTION_SPAN    = 200    # macro trend gate: 200 × 15-min ≈ 50-hour trend EMA
ATR_STOP_MULTIPLIER   = 1.5    # stop loss = entry ± 1.5 × ATR(10)
ATR_TARGET_MULTIPLIER = 3.0    # profit target = entry ± 3.0 × ATR(10) → 2:1 R:R

# ── Risk management ───────────────────────────────────────────────────────────
CAPITAL_INR              = 30_000.0   # starting capital in INR
MAX_DAILY_LOSS_PCT        = 2.0        # kill switch fires at this % loss
MAX_DAILY_LOSS_INR        = CAPITAL_INR * MAX_DAILY_LOSS_PCT / 100  # ₹600
LOSS_REDUCTION_PCT        = 1.5        # drop to 1 lot after this % daily loss
BASE_LOTS                 = 1          # default position size (1 lot = $1,000)
MAX_LOTS                  = 2          # never open more than this
HIGH_CONFIDENCE_MIN       = 80         # Claude confidence needed for 2-lot trades
MAX_CONSECUTIVE_REJECTIONS = 5         # kill switch trigger
WS_HEARTBEAT_MAX_GAP_SEC  = 5          # WebSocket silence → kill switch

# ── Rate limiting (SEBI compliance) ──────────────────────────────────────────
MAX_OPS        = 9    # hard ceiling; SEBI limit is 10, we stay at 9
BURST_CAPACITY = 3    # leaky bucket burst allowance before throttling

# ── Order execution ───────────────────────────────────────────────────────────
ORDER_MODIFY_TIMEOUT_SEC = 3     # seconds before modifying unfilled limit order
ORDER_CANCEL_TIMEOUT_SEC = 10    # seconds before cancelling unfilled order

# ── Claude models & budget ────────────────────────────────────────────────────
CLAUDE_SIGNAL_MODEL    = "claude-haiku-4-5-20251001"  # intraday signal validation
CLAUDE_BRIEFING_MODEL  = "claude-sonnet-4-6"           # morning briefing (once/day)
CLAUDE_SIGNAL_TIMEOUT  = 5.0     # seconds → timeout triggers SKIP
CLAUDE_MAX_DAILY_CALLS = 80      # hard cap on Haiku calls per day
CLAUDE_MIN_CONFIDENCE  = 65      # minimum confidence score to execute a signal

# ── File paths ────────────────────────────────────────────────────────────────
DB_PATH     = ROOT_DIR / "data"    / "claudey_tr.db"
LOGS_DIR    = ROOT_DIR / "logs"
REPORTS_DIR = ROOT_DIR / "reports"

# Ensure runtime directories exist
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Trading mode ──────────────────────────────────────────────────────────────
# Override with TRADING_MODE=live in .env when ready for live deployment.
TRADING_MODE = os.getenv("TRADING_MODE", "paper")   # "paper" | "live"
