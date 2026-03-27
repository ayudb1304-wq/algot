# claudey-tr: Forex Trading Bot — Implementation Tracker

**Market:** USDINR (NSE Exchange Traded Currency Derivatives)
**Broker:** Angel One SmartAPI
**AI Engine:** Anthropic Claude (Haiku 4.5 intraday + Sonnet 4.6 morning briefing)
**Strategy:** ARIA — Adaptive Regime Intraday Algo (ORB breakout in trending + Z-score reversion in ranging)
**Capital:** ₹30,000 (after 2-week paper trading validation)
**Session:** Entries 09:15 AM – 12:00 PM IST | Exits managed until 03:15 PM IST

---

## Environment Variables Expected in `.env`

```
ANGEL_ONE_API_KEY=
ANGEL_ONE_CLIENT_ID=
ANGEL_ONE_PASSWORD=
ANGEL_ONE_TOTP_SECRET=
ANTHROPIC_API_KEY=
```

---

## Architecture Overview

```
main.py (orchestrator)
│
├── Session Manager       08:50 AM TOTP login → 11:59 PM auto-logout
├── Market Feed           WebSocket Snap Quote (5 bid/ask levels, live ticks)
├── Historical Data       5-min OHLCV candles (SQLite, 90-day rolling)
├── News Feed             RBI RSS + Reuters INR headlines
│
├── Strategy Engine — ARIA (Adaptive Regime Intraday Algo)
│   ├── Indicators        Z-score(48), EMA(9/21), RSI(14), ADX(14), ATR(10)
│   ├── Regime Detector   ADX < 18 = ranging | ADX > 25 = trending | 18-25 = sit out
│   ├── ORB Builder       Opening Range (9:00–9:15 AM, first 3 candles)
│   ├── TRENDING mode     ORB breakout + RSI/EMA momentum confirm | 2:1 R:R via ATR
│   └── RANGING mode      Z-score reversion | Long Z<-2.5 | Short Z>+2.5 | ATR stop
│
├── Claude MCP Layer
│   ├── MCP Server        Exposes 6 Angel One tools to Claude
│   ├── Haiku Agent       Signal validation per trade (~20 calls/day, ARIA 1-2 trades max)
│   └── Sonnet Agent      Morning briefing once at 09:00 AM (regime bias + ORB context)
│
├── Risk Layer
│   ├── Kill Switch       5 triggers (loss/OPS/rejections/heartbeat/Claude)
│   ├── Rate Limiter      Leaky bucket, hard cap 9 OPS
│   └── Position Manager  1-2 lots max, Kelly-lite sizing
│
├── Execution Engine      Smart limit orders + price chasing (modify if unfilled >3s)
│
├── Paper Engine          Slippage simulation (1-2 ticks), virtual fills
└── Audit DB              SQLite: sessions, orders, positions, signals, heartbeats
```

---

## Critical Constraints (Non-negotiable)

| Constraint | Value | Reason |
|---|---|---|
| Max OPS | 9 orders/second | SEBI 10 OPS threshold — stay below |
| Max daily loss | ₹600 (2% of ₹30k) | Kill switch fires, no new orders |
| RBI window | 11:30 AM – 12:30 PM | No new entries during polling |
| Session lifetime | Daily (08:50 AM login, 11:59 PM logout) | SEBI 2FA mandate |
| Order type | Limit orders only | Market/IOC banned in ETCD segment |
| Price chase timeout | 3 seconds → modify, 10 seconds → cancel | MPP compliance |
| Audit retention | 5 years | SEBI regulatory requirement |
| Claude budget | ≤ $5/month | Haiku for signals, Sonnet for briefing only |

---

## Model Cost Configuration

| Model | Use | Frequency | Est. Cost |
|---|---|---|---|
| `claude-haiku-4-5-20251001` | Signal validation | ~80 calls/day, 22 trading days | ~$1.50/mo |
| `claude-sonnet-4-6` | Morning market briefing | 1 call/day, 22 trading days | ~$0.80/mo |
| **Total** | | | **~$2.30/mo** |

---

## Go-Live Criteria (Must pass ALL before depositing ₹30k)

- [ ] 10 consecutive paper trading days with net positive P&L
- [ ] Win rate ≥ 55% over paper trading period
- [ ] Sharpe ratio ≥ 1.0 over paper trading period
- [ ] Max single-day drawdown < 1.5% in paper trading
- [ ] Claude average confidence score ≥ 65
- [ ] Zero unintended kill switch fires
- [ ] Zero RBI window violations
- [ ] Static IP solution live and whitelisted in Angel One dashboard
- [ ] Generic Algo-ID confirmed with Angel One support

---

---

# Phase 0 — Project Scaffolding ✅ COMPLETE

**Duration:** Day 1
**Completed:** 2026-03-27
**Goal:** Full directory structure, dependencies installed, `.env` verified loading correctly.

## Tasks

- [x] Create full directory structure (all folders and empty `__init__.py` files)
- [x] Write `requirements.txt` with all dependencies pinned
- [x] Write `config/settings.py` — loads all 5 env vars, validates none are missing, exports typed constants
- [x] Write `main.py` — entry point with `--check` flag that prints env status
- [x] Write `core/audit/database.py` — SQLite schema creation (6 tables)
- [x] Write `core/audit/logger.py` — structured JSON logger with IST timestamps

## Directory Structure

```
algot/
├── .env
├── requirements.txt
├── main.py
├── IMPLEMENTATION.md
├── config/
│   └── settings.py
├── core/
│   ├── __init__.py
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── angel_auth.py
│   │   └── session_manager.py
│   ├── data/
│   │   ├── __init__.py
│   │   ├── market_feed.py
│   │   ├── historical.py
│   │   └── news_feed.py
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── indicators.py
│   │   ├── mean_reversion.py
│   │   └── regime_detector.py
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── rate_limiter.py
│   │   ├── order_manager.py
│   │   └── position_manager.py
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── kill_switch.py
│   │   └── risk_manager.py
│   ├── claude/
│   │   ├── __init__.py
│   │   ├── mcp_server.py
│   │   ├── agent.py
│   │   └── prompts.py
│   └── audit/
│       ├── __init__.py
│       ├── database.py
│       └── logger.py
├── paper_trading/
│   ├── __init__.py
│   ├── engine.py
│   ├── slippage_model.py
│   └── backtest.py
├── tests/
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_indicators.py
│   ├── test_strategy.py
│   └── test_risk.py
└── dashboard/
    ├── __init__.py
    └── monitor.py
```

## SQLite Schema (6 tables)

```sql
sessions    — id, login_time, logout_time, token_hash, ip_address, status
orders      — id, signal_id, symbol, order_type, qty, price, status, algo_id, timestamp
positions   — id, symbol, lots, avg_price, mtm_pnl, realized_pnl, opened_at, closed_at
signals     — id, timestamp, z_score, adx, rsi, ltp, action, claude_confidence, claude_reasoning
heartbeats  — id, timestamp, ws_status, api_status, ip_address
daily_pnl   — id, date, gross_pnl, net_pnl, trades, wins, losses, max_drawdown, sharpe
```

## Exit Gate — Phase 0 ✅ PASSED (2026-03-27)

```bash
python main.py --check
```
Output:
```
All 5 env vars loaded ✓
SQLite DB created with 6 tables ✓
All runtime paths writable ✓
Logger active (console + JSON file) ✓
"All systems ready." printed ✓
```

---

---

# Phase 1 — Angel One Authentication & Session Management ✅ COMPLETE

**Duration:** Days 2–4
**Completed:** 2026-03-27
**Goal:** Full automated TOTP login, session stored in SQLite, daily renewal scheduled.

## Tasks

- [x] Write `core/auth/angel_auth.py`
  - [x] TOTP generation using `pyotp` from `ANGEL_ONE_TOTP_SECRET`
  - [x] Login via SmartAPI (`generateSession`)
  - [x] Store JWT token + feed token in SQLite `sessions` table
  - [x] Public IP self-check before every login (log to `heartbeats`)
  - [x] Error handling: retry login up to 3x with 10s backoff
- [x] Write `core/auth/session_manager.py`
  - [x] Schedule login at 08:50 AM IST daily (`APScheduler`)
  - [x] Schedule logout at 11:59 PM IST daily
  - [x] Global `get_smart_connect()` / `get_feed_token()` accessors
  - [x] Thread-safe with lock, idempotent double-login guard
- [x] Write `tests/test_auth.py`
  - [x] Test: login returns valid profile JSON
  - [x] Test: token stored correctly in SQLite
  - [x] Test: logout clears session
  - [x] Test: API failure on logout still closes DB
  - [x] Test: bad TOTP / failed login retries MAX_LOGIN_RETRIES times
  - [x] Test: double manual_login reuses existing session
  - [x] Integration test: real Angel One API login → profile → logout

## Key Implementation Notes

- Angel One sessions expire daily — **never cache token across midnight**
- TOTP window = 30 seconds; generate token at login time, not stored
- `generateSession` returns: `jwtToken`, `refreshToken`, `feedToken`
- Only `jwtToken` is needed for REST API calls
- `feedToken` is needed for WebSocket authentication in Phase 2
- Static IP: for paper trading phase, dynamic IP is acceptable. Flag in logs if IP changes between sessions.

## Exit Gate — Phase 1 ✅ PASSED (2026-03-27)

```
Unit tests:        18/18 passed (0 failed)
Integration test:  PASSED — real login to AYUSH DHANRAJ BHIOGADE (AACG120065)
python main.py --test-auth: PASSED
  Login → Profile → Logout → DB verified ✓
  Public IP: 106.51.64.224 logged ✓
  Token prefix only stored in DB ✓
```

---

---

# Phase 2 — Market Data Pipeline ✅ COMPLETE

**Duration:** Days 5–8
**Completed:** 2026-03-27
**Goal:** Live USDINR tick stream running, historical candles stored, RBI window detection active.

## Tasks

- [x] Write `core/data/market_feed.py`
  - [x] Connect Angel One WebSocket (`SmartWebSocketV2`)
  - [x] Subscribe to USDINR in "Snap Quote" mode (mode 3 — 5 bid/ask levels)
  - [x] Parse tick: bid, ask, LTP, volume, timestamp (price_divisor=100)
  - [x] 5-min `_CandleBuilder` — emits completed candle on window boundary
  - [x] Tick callbacks for strategy engine
  - [x] Heartbeat to SQLite every 60 seconds
  - [x] Auto-reconnect with exponential backoff (max 5 retries)
  - [x] `is_rbi_window()`, `is_market_hours()`, `minutes_until_rbi_window()` utilities
- [x] Write `core/data/historical.py`
  - [x] `backfill(days=90)` — 30-day chunk fetching, upsert to SQLite
  - [x] `fetch_today()` — incremental morning update
  - [x] `get_latest_candles(n)` — returns pandas DataFrame for indicators
  - [x] `get_candles_for_backtest(from, to)` — full range for backtest engine
  - [x] Rate limit: 2s delay between chunks (conservative, avoids AB1019)
- [x] Write `core/data/news_feed.py`
  - [x] RBI + Economic Times RSS feeds (xml.etree, no extra deps)
  - [x] `_is_rbi_flag()` — 18 keywords for intervention detection
  - [x] `poll_once()` — stores new headlines, skips duplicates (UNIQUE constraint)
  - [x] `has_rbi_news(minutes)` — used by Claude signal validation
  - [x] `NewsFeed` class — background thread, 15-min poll interval
- [x] Add `candles` + `news` tables to SQLite schema
- [x] Add RBI window utilities (is_rbi_window, is_market_hours)

## USDINR Symbol Reference (Angel One)

```python
USDINR_SYMBOL = "USDINR"
USDINR_TOKEN  = "11536"       # Angel One instrument token for USDINR near-month
EXCHANGE      = "CDS"         # Currency Derivatives Segment
```

## RBI Window Logic

```python
# In config/settings.py
from datetime import time
import pytz

IST = pytz.timezone("Asia/Kolkata")
MARKET_OPEN    = time(9, 0)
MARKET_CLOSE   = time(15, 30)
RBI_WIN_START  = time(11, 30)   # Polling window — high structural risk
RBI_WIN_END    = time(12, 30)   # No new entries during this period
SQUARE_OFF_TIME = time(15, 15)  # Force close all positions 15 min before close
```

## Exit Gate — Phase 2 ✅

```bash
python main.py --stream
```
Expected output (live, updating every second):
```
[FEED] USDINR | Bid: 84.2525 | Ask: 84.2550 | LTP: 84.2537 | Vol: 142,300
[FEED] USDINR | Bid: 84.2500 | Ask: 84.2525 | LTP: 84.2512 | Vol: 143,100
[RBI ] Window: INACTIVE (next: 11:30 AM)
[DATA] Candles loaded: 2,340 bars (5-min, 90 days)
[NEWS] Last headline: "RBI seen selling dollars to cap rupee weakness" (14 min ago)
```

---

---

# Phase 3 — Mean Reversion Strategy Engine ✅ COMPLETE

**Duration:** Days 9–13
**Completed:** 2026-03-27
**Goal:** Generate LONG/SHORT/EXIT signals with full filter stack. No execution yet — signals only.

## Tasks

- [x] Write `core/strategy/indicators.py`
  - [x] `zscore(series, window=20)` — rolling Z-score
  - [x] `ema(series, span)` — exponential moving average
  - [x] `rsi(series, period=14)` — relative strength index
  - [x] `adx(high, low, close, period=14)` — average directional index
  - [x] `atr(high, low, close, period=10)` — average true range
  - [x] All functions: accept pandas Series, return pandas Series
- [x] Write `core/strategy/regime_detector.py`
  - [x] `classify_regime(adx_value)` → `"RANGING"` | `"NEUTRAL"` | `"TRENDING"`
  - [x] `is_tradeable_regime(regime)` → True only for RANGING
- [x] Write `core/strategy/mean_reversion.py`
  - [x] Signal state machine: `FLAT` → `LONG` / `SHORT` → `EXIT`
  - [x] Entry filters (ALL must pass):
    - [x] Z-score threshold crossed (< -1.5 or > +1.5)
    - [x] Regime = RANGING (ADX < 20)
    - [x] NOT in RBI window
    - [x] ATR < 1.5× 10-day ATR average
    - [x] Volume > 50% of 5-day average
  - [x] Exit logic:
    - [x] Z-score reverts to |Z| < 0.3
    - [x] Time-based exit: position open > 12 candles (60 min)
    - [x] Square-off all positions at 15:15 IST regardless
  - [x] Store every signal candidate in SQLite `signals` table (even if filtered out)
  - [x] Emit `SignalEvent` to Claude layer for validation

## Signal Object Schema

```python
@dataclass
class SignalEvent:
    timestamp: datetime
    symbol: str             # "USDINR"
    action: str             # "LONG" | "SHORT" | "EXIT" | "SKIP"
    z_score: float
    adx: float
    rsi: float
    atr: float
    ltp: float
    volume: int
    regime: str
    filters_passed: list[str]
    filters_failed: list[str]
    claude_confidence: int   # 0 until Claude validates
    claude_reasoning: str    # empty until Claude validates
```

## Strategy Parameters (tunable in `config/settings.py`)

```python
Z_ENTRY_THRESHOLD  = 1.5    # |Z| > 1.5 triggers signal
Z_EXIT_THRESHOLD   = 0.3    # |Z| < 0.3 triggers exit
Z_WINDOW           = 20     # rolling periods for Z-score
ADX_RANGING_MAX    = 20     # ADX below this = ranging market
ADX_TRENDING_MIN   = 25     # ADX above this = trending (pause strategy)
ATR_MULTIPLIER     = 1.5    # max ATR vs 10-day avg
VOLUME_THRESHOLD   = 0.50   # min volume vs 5-day avg
TIME_EXIT_CANDLES  = 12     # max 12 × 5min = 60 minutes
```

## Key Implementation Notes

- Exit checks run before entry checks — open positions always get an exit opportunity even if indicators are NaN
- zscore returns 0.0 for zero-std (flat) series (not NaN), preserving NaN only for insufficient data rows
- ADX NaN → NEUTRAL regime (conservative: no entries when data is ambiguous)
- Exits fire on z_reversion OR time_exit OR eod_exit (any one condition sufficient)
- SKIP signals are stored to SQLite just like LONG/SHORT/EXIT (full audit trail)

## Exit Gate — Phase 3 ✅ PASSED (2026-03-27)

```
Unit tests: 46/46 passed (0 failed)
  TestZscore           6/6  — zscore edge cases incl. flat series
  TestEMA              4/4  — ema correctness
  TestRSI              5/5  — rsi range, nan handling
  TestADX              4/4  — regime detection, trending vs ranging
  TestATR              4/4  — volatility filter
  TestRegimeDetector  11/11 — all boundary conditions, NaN/None inputs
  TestMeanReversion   12/12 — entry filters, exit triggers, DB storage, state machine
python main.py --signals: wired up and ready (signals on live ticks)
```

---

---

# Phase 3.5 — ARIA Strategy (Adaptive Regime Intraday Algo)

**Duration:** Days 14–16
**Goal:** Replace pure mean reversion with a regime-switching strategy that profits in
both trending and ranging markets. Validated by offline backtest before Phase 4.

## Why ARIA?

Offline backtesting (Jan–Mar 2026, 14,024 candles) exposed three fatal flaws in the
pure mean-reversion approach:

| Flaw | Evidence | Fix in ARIA |
|---|---|---|
| Counter-trend SHORTs in macro uptrend | SHORT trades: net −₹1,875 (28 trades) | ORB breakout trades WITH the trend |
| Z=1.5 on 100-min window = noise | 287 trades, avg ₹33 win vs ₹47 loss | Z=2.5 on 240-min window, max 2 trades/day |
| Unbounded losses on time exit | Single trade −₹357 (price gapped through) | ATR-based stop loss scales with volatility |
| ₹11,480 brokerage on 287 trades | Net wiped out even with positive gross | 1–2 trades/day → ~₹880/month brokerage |

## ARIA Signal Flow

```
9:00–9:15 AM  ── CALIBRATION ─────────────────────────────────────────────────
  Record ORB high = max(high) of first 3 candles
  Record ORB low  = min(low)  of first 3 candles
  Compute ADX(14) → classify day regime

9:15–12:00 PM ── ENTRY WINDOW (max 2 trades) ──────────────────────────────────

  ADX > 25 → TRENDING MODE → ORB Breakout
    LONG  : price > ORB_high AND RSI(14) > 50 AND EMA(9) > EMA(21)
    SHORT : price < ORB_low  AND RSI(14) < 50 AND EMA(9) < EMA(21)
    Stop  : entry ± 1.5 × ATR(10)
    Target: entry ± 3.0 × ATR(10)   → 2:1 R:R, needs only 35% win rate

  ADX < 18 → RANGING MODE → Z-score Reversion
    LONG  : Z(48) < −2.5
    SHORT : Z(48) > +2.5
    Stop  : entry ± 1.5 × ATR(10)
    Exit  : |Z| < 0.3  OR  12 candles (60 min)

  18 ≤ ADX ≤ 25 → NEUTRAL → SIT OUT (no new positions today)

12:00 PM ─── ENTRY WINDOW CLOSES (exits still managed) ──────────────────────
3:15 PM  ─── EOD SQUARE-OFF ─────────────────────────────────────────────────
```

## New Files

- `core/strategy/regime_adaptive.py` — `ARIAStrategy` class (ORBState, _PositionState, evaluate)

## Modified Files

- `core/strategy/mean_reversion.py` — `SignalEvent` extended with `stop_price`, `target_price`,
  `strategy_mode`, `orb_high`, `orb_low` (all Optional, backward compatible)
- `config/settings.py` — ARIA parameters added (see below)
- `scripts/backtest_offline.py` — Uses `ARIAStrategy`, session filter, ORB/stop/target logic

## ARIA Parameters (`config/settings.py`)

```python
# ── ARIA strategy parameters ────────────────────────────────────────────────
ORB_CANDLES           = 3     # first N × 5-min candles define Opening Range (15 min)
ENTRY_SESSION_END     = time(12, 0)   # no new entries after 12:00 PM IST
MAX_DAILY_TRADES      = 2     # max trades per day (quality over quantity)
EMA_FAST_SPAN         = 9     # fast EMA for momentum confirmation
EMA_SLOW_SPAN         = 21    # slow EMA for momentum confirmation
ATR_STOP_MULTIPLIER   = 1.5   # stop loss = entry ± 1.5 × ATR
ATR_TARGET_MULTIPLIER = 3.0   # profit target = entry ± 3.0 × ATR  (2:1 R:R)
```

## SignalEvent Extensions

```python
@dataclass
class SignalEvent:
    # ... existing fields ...
    stop_price:    Optional[float] = None   # ATR-based stop — used by execution + exit logic
    target_price:  Optional[float] = None  # ATR-based target (TRENDING mode only)
    strategy_mode: str             = ""    # "TRENDING_ORB" | "RANGING_ZSCORE" | ""
    orb_high:      Optional[float] = None  # passed to Claude for context
    orb_low:       Optional[float] = None  # passed to Claude for context
```

## Backtest Acceptance Criteria (Phase 3.5)

Before proceeding to Phase 4, the ARIA backtest over the Jan–Mar 2026 period must show:

| Metric | Minimum |
|---|---|
| Net P&L | Positive (any amount) |
| Trades | 15–40 (1–2/day, not zero) |
| Brokerage | < ₹2,000 (confirms trade count is controlled) |
| Avg win / Avg loss ratio | > 1.0 |

## Exit Gate — Phase 3.5

```bash
python scripts/backtest_offline.py --from 2026-01-05 --to 2026-03-27
```
Expected:
```
Trades         ~20–35
Net P&L        PROFITABLE
Exit reasons   mix of target_hit, z_revert, stop_loss, time_exit
Brokerage      < ₹2,000
```

---

---

# Phase 4 — Claude MCP Integration

**Duration:** Days 14–17
**Goal:** Claude validates every signal. Haiku for intraday decisions, Sonnet for daily briefing.

## Tasks

- [ ] Write `core/claude/mcp_server.py`
  - [ ] FastMCP server exposing 6 tools to Claude:
    - [ ] `get_usdinr_ltp()` → current bid/ask/LTP from SQLite ticks
    - [ ] `get_indicators(symbol)` → latest Z-score, RSI, ADX, ATR values
    - [ ] `get_recent_news(n=5)` → last N headlines from SQLite news table
    - [ ] `get_rbi_window_status()` → bool + minutes until window
    - [ ] `get_position_summary()` → open lots, unrealized P&L
    - [ ] `get_daily_pnl()` → today's realized P&L and trade count
  - [ ] MCP server runs as local subprocess (stdio transport)
- [ ] Write `core/claude/prompts.py`
  - [ ] `SIGNAL_VALIDATION_PROMPT` — Haiku template (see below)
  - [ ] `MORNING_BRIEFING_PROMPT` — Sonnet template (see below)
  - [ ] Output schema enforced via `response_format` / structured JSON instruction
- [ ] Write `core/claude/agent.py`
  - [ ] `validate_signal(signal: SignalEvent) → ClaudeDecision` (Haiku, async)
  - [ ] `morning_briefing() → MarketContext` (Sonnet, called once at 09:00 AM)
  - [ ] Timeout: 5 seconds max per call → fallback = `SKIP` on timeout
  - [ ] Daily call counter with hard cap (80 Haiku + 1 Sonnet per day)
  - [ ] Cost tracker: log estimated $ per call to `heartbeats` table
- [ ] Integrate Claude decision into `core/strategy/mean_reversion.py`
  - [ ] Signal only becomes order if `action == "EXECUTE"` and `confidence >= 65`
  - [ ] `WAIT` → re-evaluate on next candle close (max 2 retries)
  - [ ] `SKIP` → discard signal, log reason

## Claude Decision Schema

```python
@dataclass
class ClaudeDecision:
    action: str           # "EXECUTE" | "SKIP" | "WAIT"
    confidence: int       # 0–100
    reasoning: str        # brief explanation (1-2 sentences)
    risk_override: bool   # True = Claude detected high-risk condition
    news_flag: bool       # True = relevant news detected in last 2 hours
```

## Prompt Templates

### Haiku — Signal Validation (every trade)

```
You are a senior quantitative analyst specializing in Indian currency derivatives (ETCD).
You are validating an ARIA (Adaptive Regime Intraday Algo) signal for USDINR.

Strategy mode today: {strategy_mode}   (TRENDING_ORB or RANGING_ZSCORE)

Current market data:
- LTP: {ltp} | Bid: {bid} | Ask: {ask}
- Z-score (48-period): {z_score}
- RSI (14): {rsi}
- ADX (14): {adx}  → regime: {regime}
- ATR (10): {atr}
- Proposed action: {action} (LONG / SHORT)
- Stop price: {stop_price} | Target price: {target_price}
- ORB high: {orb_high} | ORB low: {orb_low}
- RBI polling window active: {rbi_window}

Last 5 news headlines:
{news_headlines}

Validation rules:
1. RBI window active → mandatory SKIP regardless of signal
2. Any headline mentioning RBI intervention or emergency rate action in last 2 hours → reduce confidence by 30
3. TRENDING_ORB mode: if ADX < 20, regime may have shifted → recommend WAIT
4. TRENDING_ORB mode: if price has already moved > 2× ATR from ORB level → SKIP (chasing)
5. RANGING_ZSCORE mode: if Z < -4.0 or Z > +4.0 → WAIT (potential structural break)
6. RANGING_ZSCORE mode: if ADX > 22 → SKIP (trending market, mean reversion unreliable)
7. Any headline mentioning FOMC, US CPI, or major macro event in next 2 hours → reduce confidence by 20

Respond ONLY with valid JSON:
{
  "action": "EXECUTE" | "SKIP" | "WAIT",
  "confidence": <0-100>,
  "reasoning": "<max 20 words>",
  "risk_override": <true/false>,
  "news_flag": <true/false>
}
```

### Sonnet — Morning Briefing (once at 09:00 AM)

```
You are a senior FX strategist for Indian currency derivatives.
Provide a pre-market briefing for USDINR ARIA algo trading today.

ARIA strategy: regime-adaptive — uses ORB breakout in trending markets,
Z-score reversion in ranging markets, sits out when ambiguous.

Today's context:
{overnight_news_summary}

Historical context:
- Yesterday's USDINR range: {prev_low} – {prev_high}
- Yesterday's close: {prev_close}
- 5-day ATR (5-min): {atr_5d}
- Current ADX (14): {adx_current}  → expected regime: {expected_regime}
- Current 48-period Z-score: {z_score}

Respond ONLY with valid JSON:
{
  "trading_bias": "NEUTRAL" | "BULLISH_USD" | "BEARISH_USD",
  "expected_regime": "TRENDING" | "RANGING" | "NEUTRAL",
  "recommended_z_threshold": <2.0–3.5>,
  "orb_watch_levels": {"support": <price>, "resistance": <price>},
  "avoid_windows": ["HH:MM-HH:MM", ...],
  "risk_level": "LOW" | "MEDIUM" | "HIGH",
  "key_levels": {"support": <price>, "resistance": <price>},
  "briefing_summary": "<max 40 words>"
}
```

## Exit Gate — Phase 4 ✅

```bash
python main.py --test-claude
```
Expected output:
```
[CLAUDE] Morning briefing (Sonnet)...
{
  "trading_bias": "NEUTRAL",
  "recommended_z_threshold": 1.6,
  "avoid_windows": ["11:30-12:30"],
  "risk_level": "MEDIUM",
  "key_levels": {"support": 84.10, "resistance": 84.50},
  "briefing_summary": "RBI likely passive today. Range-bound session expected."
}

[CLAUDE] Validating test signal (Haiku)...
{
  "action": "EXECUTE",
  "confidence": 74,
  "reasoning": "No RBI news, Z-score in normal reversion zone, ADX ranging.",
  "risk_override": false,
  "news_flag": false
}
[CLAUDE] Estimated cost this call: $0.000018
[CLAUDE] Daily call budget remaining: 79/80
```

---

---

# Phase 5 — Risk Management & Kill Switch

**Duration:** Days 18–20
**Goal:** All safety systems active. No order can bypass the risk layer.

## Tasks

- [ ] Write `core/execution/rate_limiter.py`
  - [ ] Leaky bucket implementation (not token bucket)
  - [ ] `RATE = 9` — steady-state OPS ceiling
  - [ ] `BURST = 3` — max simultaneous order burst allowed
  - [ ] `acquire()` → blocks if rate exceeded, raises `RateLimitError` if queue full
  - [ ] OPS counter exposed for kill switch monitoring
- [ ] Write `core/risk/kill_switch.py`
  - [ ] State machine: `ACTIVE` → `SUSPENDED` → `EMERGENCY_STOP`
  - [ ] Trigger 1: `consecutive_rejections >= 5`
  - [ ] Trigger 2: `ops_per_second >= 9` (rate limiter breach)
  - [ ] Trigger 3: `daily_loss_pct >= 2.0` (₹600 on ₹30k capital)
  - [ ] Trigger 4: `ws_heartbeat_gap_seconds >= 5`
  - [ ] Trigger 5: `claude_timeout_streak >= 3`
  - [ ] On `EMERGENCY_STOP`: cancel all pending orders → close all open positions → log → halt
  - [ ] Manual resume requires `--reset-kill-switch` flag (no auto-resume)
- [ ] Write `core/risk/risk_manager.py`
  - [ ] Real-time daily P&L tracker (MTM + realized)
  - [ ] Position limit enforcer: max 2 open lots at any time
  - [ ] OTR (Order-to-Trade Ratio) counter — flag if > 10:1 ratio
  - [ ] Pre-order checklist: margin check before every order
- [ ] Write `core/execution/position_manager.py`
  - [ ] Track open positions in SQLite
  - [ ] MTM P&L update on every tick
  - [ ] Auto square-off at 15:15 IST
- [ ] Write `core/execution/order_manager.py`
  - [ ] Smart limit order placement
  - [ ] Price chasing: if unfilled after 3s → modify to current best bid/ask
  - [ ] Cancel if still unfilled after 10s (log as missed opportunity)
  - [ ] Algo-ID tag appended to every order (Generic ID from Angel One)
  - [ ] All orders go through `risk_manager.pre_order_check()` before placement

## Kill Switch Trigger Reference

| Trigger | Threshold | Action |
|---|---|---|
| Consecutive RMS rejections | 5 in a row | EMERGENCY_STOP |
| Orders per second | ≥ 9 OPS | SUSPENDED (60s cooldown) |
| Daily MTM loss | ≥ 2% of capital (₹600) | EMERGENCY_STOP |
| WebSocket heartbeat gap | ≥ 5 seconds | SUSPENDED → reconnect |
| Claude timeout streak | 3 consecutive timeouts | SUSPENDED, skip Claude 30 min |

## Position Sizing Rules

```python
# Base configuration for ₹30,000 capital
BASE_LOTS           = 1       # default position size
MAX_LOTS            = 2       # never exceed this
HIGH_CONFIDENCE_MIN = 80      # Claude confidence for 2-lot trades
RBI_WINDOW_LOTS     = 0       # zero new entries during RBI window
LOSS_REDUCTION_PCT  = 1.5     # reduce to 1 lot after 1.5% daily loss
KILL_SWITCH_PCT     = 2.0     # emergency stop at 2% daily loss
```

## Exit Gate — Phase 5 ✅

```bash
python tests/test_risk.py
```
Expected output:
```
test_kill_switch_consecutive_rejections ... PASSED
test_kill_switch_daily_loss_limit       ... PASSED
test_kill_switch_ops_violation          ... PASSED
test_kill_switch_heartbeat_loss         ... PASSED
test_rate_limiter_9ops_cap              ... PASSED
test_rate_limiter_burst_allowed         ... PASSED
test_position_limit_enforced            ... PASSED
test_square_off_at_1515                 ... PASSED

8 passed in 1.42s
```

---

---

# Phase 6 — Paper Trading Engine

**Duration:** Days 21–24
**Goal:** Full bot runs in paper mode. Real market data, simulated fills, real Claude decisions.

## Tasks

- [ ] Write `paper_trading/slippage_model.py`
  - [ ] BUY fill price = `ASK + 1 tick (₹0.0025)`
  - [ ] SELL fill price = `BID - 1 tick (₹0.0025)`
  - [ ] Partial fill simulation if order size > 10% of available volume at best price
  - [ ] Brokerage deduction: ₹20 flat per executed order
  - [ ] STT + exchange charges: 0.01% per trade
- [ ] Write `paper_trading/engine.py`
  - [ ] Virtual order book (mirrors real Angel One order flow without API calls)
  - [ ] Fill simulation on every new tick
  - [ ] P&L tracking: unrealized (MTM) + realized
  - [ ] Position state synchronized with `position_manager.py`
- [ ] Write `dashboard/monitor.py`
  - [ ] Terminal dashboard (updates every 5 seconds during market hours)
  - [ ] Shows: current position, MTM P&L, daily P&L, last signal, Claude status, kill switch status
- [ ] Add daily report generator
  - [ ] Auto-runs at 15:30 IST
  - [ ] Saves to `reports/YYYY-MM-DD.json`
  - [ ] Calculates: trades, win rate, gross P&L, net P&L, max drawdown, Sharpe

## Paper Trading Dashboard Layout

```
╔══════════════════════════════════════════════════════════╗
║  claudey-tr | PAPER TRADING | 2026-04-15 11:42:33 IST   ║
╠══════════════════════════════════════════════════════════╣
║  USDINR LTP:  84.2537   Bid: 84.2525   Ask: 84.2550     ║
║  Position:    LONG 1 lot @ 84.2175  |  MTM: +₹90.50     ║
║  Z-score:     -1.84     ADX: 16.2   |  Regime: RANGING  ║
╠══════════════════════════════════════════════════════════╣
║  Today's P&L:  Gross +₹324   Net +₹244  (3 trades)      ║
║  Win/Loss:     2W / 1L       Win Rate: 66.7%             ║
║  Max Drawdown: ₹88           Daily Budget: 91% remain    ║
╠══════════════════════════════════════════════════════════╣
║  Last Signal:  LONG @ 11:38 | Claude: EXECUTE (78)       ║
║  Kill Switch:  ACTIVE (no triggers)                      ║
║  RBI Window:   INACTIVE (opens in 1h 48m)               ║
║  Claude calls: 7/80 today | Est. cost: $0.000126         ║
╚══════════════════════════════════════════════════════════╝
```

## Daily Report Schema

```json
{
  "date": "2026-04-15",
  "mode": "paper",
  "trades": 8,
  "wins": 5,
  "losses": 3,
  "win_rate": 62.5,
  "gross_pnl": 284.0,
  "net_pnl_after_costs": 204.0,
  "max_drawdown_inr": 180.0,
  "sharpe_ratio": 1.42,
  "claude_calls": 12,
  "claude_avg_confidence": 71,
  "kill_switch_fires": 0,
  "rbi_window_violations": 0,
  "signals_generated": 15,
  "signals_executed": 8,
  "signals_skipped_by_claude": 7
}
```

## Exit Gate — Phase 6 ✅

Run for minimum **10 consecutive market days** and verify:
- [ ] Win rate ≥ 55%
- [ ] Sharpe ratio ≥ 1.0
- [ ] Max single-day drawdown < ₹450 (1.5% of ₹30k)
- [ ] Claude avg confidence ≥ 65
- [ ] Kill switch: 0 unintended fires
- [ ] RBI window violations: 0
- [ ] Net P&L positive across the 10-day window

---

---

# Phase 7 — Backtesting & Live Deployment Prep

**Duration:** Days 25–28
**Goal:** Historical validation, static IP solved, live deployment checklist complete.

## Tasks

### Backtesting
- [ ] Write `paper_trading/backtest.py`
  - [ ] Replay last 90 days of 5-min USDINR candles
  - [ ] Apply same signal logic (indicators + filters)
  - [ ] Claude replaced with rule-based mock (cost control in backtesting)
  - [ ] Slippage: 1 tick per fill
  - [ ] Output: total trades, win rate, Sharpe, max drawdown, profit factor, CAGR

### Infrastructure
- [ ] Solve static IP (choose one):
  - [ ] **Option A:** Request static IP from ISP (Jio/Airtel/ACT — ~₹100-200/mo addon)
  - [ ] **Option B:** Deploy bot to DigitalOcean/Vultr VPS (~$4-6/mo, recommended for reliability)
  - [ ] Whitelist chosen static IP in Angel One SmartAPI dashboard
  - [ ] Verify IP self-check passes before any live order
- [ ] Confirm Generic Algo-ID with Angel One support (mandatory post April 1, 2026)
  - [ ] Email Angel One support requesting Generic Algo-ID for retail automated trading
  - [ ] Add Algo-ID to `config/settings.py` as `ANGEL_ALGO_ID`
  - [ ] Verify it tags correctly in test order placement

### Final Checks
- [ ] Run `python tests/test_auth.py` — all pass
- [ ] Run `python tests/test_indicators.py` — all pass
- [ ] Run `python tests/test_strategy.py` — all pass
- [ ] Run `python tests/test_risk.py` — all pass
- [ ] Run backtest: report generated with metrics meeting thresholds
- [ ] Manual kill switch test: fire and verify all positions closed
- [ ] TOTP automation tested for 3 consecutive days (08:50 AM login)
- [ ] Dashboard visible and updating correctly

## Backtest Acceptance Criteria

| Metric | Minimum Threshold |
|---|---|
| Win rate | ≥ 55% |
| Sharpe ratio | ≥ 1.0 |
| Max drawdown | ≤ 8% of capital |
| Profit factor | ≥ 1.3 |
| Total trades (90 days) | ≥ 150 (confirms strategy is active) |

## Live Deployment Checklist

```
INFRASTRUCTURE
  [ ] Static IP active and confirmed
  [ ] IP whitelisted in Angel One SmartAPI dashboard
  [ ] Bot tested from static IP (test-auth passes from that IP)

COMPLIANCE
  [ ] Generic Algo-ID received from Angel One → set in .env as ANGEL_ALGO_ID
  [ ] TOTP automation stable (3-day test run)
  [ ] Daily logout at 11:59 PM confirmed

CAPITAL & RISK
  [ ] ₹30,000 deposited in Angel One trading account
  [ ] USDINR margin confirmed (~₹2,100 per lot)
  [ ] Kill switch tested and verified
  [ ] Max daily loss = ₹600 hard-coded and confirmed
  [ ] Start with 1 lot only for first 5 live trading days

MONITORING
  [ ] Dashboard running and updating
  [ ] Kill switch fire sends alert (Telegram bot or email)
  [ ] Daily P&L report emailed/logged at 15:30 IST
  [ ] All paper trading logs archived

GO/NO-GO DECISION
  [ ] All above items checked
  [ ] Paper trading phase criteria met (10 days, all metrics green)
  [ ] Backtest criteria met
  → READY FOR LIVE TRADING
```

## Exit Gate — Phase 7 ✅

```bash
python paper_trading/backtest.py --days 90 --report
```
Expected output:
```
Backtest: USDINR Mean Reversion | 2025-10-01 → 2025-12-31
Total trades:      187
Win rate:          61.0%
Gross P&L:         ₹12,840
Net P&L:           ₹9,240  (after costs)
Sharpe ratio:      1.38
Max drawdown:      ₹1,820  (6.1% of ₹30k)
Profit factor:     1.54
Monthly avg P&L:   ₹3,080

All thresholds met. Strategy approved for live deployment.
```

---

---

## Known Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Dynamic IP rejects orders after April 1 | High | Critical | Static IP solution in Phase 7 |
| ORB false breakout (price breaks then reverses) | Medium | Medium | ATR stop limits loss; momentum confirmation (RSI+EMA) reduces false breaks |
| ADX misclassifies regime at open (only 3 candles) | Medium | Medium | NEUTRAL band (18–25) forces sit-out on ambiguous days |
| RBI structural rupee move during RANGING trade | Medium | High | ATR stop fires; kill switch halts on 2% daily loss |
| Claude API timeout during market hours | Low | Medium | 5s timeout with SKIP fallback, no order placed |
| Angel One WebSocket disconnect mid-trade | Medium | High | Auto-reconnect + position (incl. stop/target) synced from SQLite |
| TOTP generation fails at 08:50 AM | Low | High | 3-retry logic, fallback alert |
| Monthly Claude budget exceeded | Low | Low | Max 2 trades/day → ~20 Haiku calls/day; hard cap at 80 |
| Runaway order loop | Very Low | Critical | Kill switch Trigger 1 + 2 catch this |
| Ranging market generates zero ORB trades | Low | Low | Strategy correctly idles; RANGING mode still active |

---

## Tech Stack Reference

| Component | Library/Tool | Version |
|---|---|---|
| Broker API | `smartapi-python` | latest |
| TOTP | `pyotp` | ≥ 2.9 |
| Claude | `anthropic` | ≥ 0.40 |
| MCP Server | `fastmcp` | latest |
| Indicators | `pandas`, `numpy` | latest stable |
| Database | `sqlite3`, `aiosqlite` | stdlib + latest |
| Scheduling | `APScheduler` | ≥ 3.10 |
| Async | `asyncio` | stdlib |
| Environment | `python-dotenv` | latest |
| Testing | `pytest`, `pytest-asyncio` | latest |
| Timezone | `pytz` | latest |

---

*Last updated: 2026-03-27 | Status: Phase 3.5 in progress — ARIA strategy build*
