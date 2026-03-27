"""
core/audit/database.py
======================
SQLite database layer for claudey-tr.

Creates all 8 tables on first run. Safe to call init_db()
on every startup — uses IF NOT EXISTS throughout.

Tables:
    sessions    — authentication events (login/logout)
    signals     — every strategy signal candidate (executed or not)
    orders      — every order placed (paper or live)
    positions   — open and closed positions with P&L
    heartbeats  — periodic system health snapshots
    daily_pnl   — end-of-day summary per trading session
    candles     — OHLCV candle data (5-min bars, 90-day rolling)
    news        — RSS news headlines with RBI-flag marker

SEBI requires a 5-year audit trail. This DB is append-only by design:
records are never deleted, only updated (status fields).
"""

import json
import sqlite3
from datetime import datetime
from typing import Optional

import pytz

from config.settings import DB_PATH, IST

# ── Connection ────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """
    Open a SQLite connection with:
    - Row factory (access columns by name: row["symbol"])
    - WAL journal mode (better read performance during live data)
    - Foreign key enforcement

    DB_PATH is resolved at call time so test monkeypatching works correctly.
    """
    from config.settings import DB_PATH as _path
    conn = sqlite3.connect(str(_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    login_time   TEXT    NOT NULL,          -- IST ISO timestamp
    logout_time  TEXT,                      -- NULL until logout
    token_hash   TEXT,                      -- first 8 chars of JWT (not full token)
    ip_address   TEXT,
    status       TEXT    NOT NULL DEFAULT 'active'
    -- status values: active | logged_out | expired | error
);

CREATE TABLE IF NOT EXISTS signals (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp          TEXT    NOT NULL,
    symbol             TEXT    NOT NULL DEFAULT 'USDINR',
    z_score            REAL    DEFAULT 0.0,
    adx                REAL    DEFAULT 0.0,
    rsi                REAL    DEFAULT 0.0,
    atr                REAL    DEFAULT 0.0,
    ltp                REAL    DEFAULT 0.0,
    volume             INTEGER DEFAULT 0,
    regime             TEXT    DEFAULT '',
    action             TEXT    NOT NULL,    -- LONG | SHORT | EXIT | SKIP
    filters_passed     TEXT    DEFAULT '[]',  -- JSON array of filter names
    filters_failed     TEXT    DEFAULT '[]',  -- JSON array of filter names
    claude_confidence  INTEGER DEFAULT 0,
    claude_reasoning   TEXT    DEFAULT '',
    claude_action      TEXT    DEFAULT '',   -- EXECUTE | SKIP | WAIT | PENDING
    executed           INTEGER DEFAULT 0    -- 0 = not executed, 1 = executed
);

CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id       INTEGER,
    symbol          TEXT    NOT NULL DEFAULT 'USDINR',
    order_type      TEXT    NOT NULL,       -- BUY | SELL
    qty             INTEGER NOT NULL,
    price           REAL    NOT NULL,       -- limit price sent
    fill_price      REAL,                   -- actual fill price (NULL if unfilled)
    status          TEXT    NOT NULL,       -- pending | filled | modified | cancelled | rejected
    algo_id         TEXT    DEFAULT '',     -- SEBI Generic Algo-ID
    broker_order_id TEXT    DEFAULT '',     -- Angel One order ID
    timestamp       TEXT    NOT NULL,
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);

CREATE TABLE IF NOT EXISTS positions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT    NOT NULL DEFAULT 'USDINR',
    lots          INTEGER NOT NULL,
    avg_price     REAL    NOT NULL,
    mtm_pnl       REAL    DEFAULT 0.0,     -- mark-to-market (unrealized)
    realized_pnl  REAL    DEFAULT 0.0,     -- locked in on close
    opened_at     TEXT    NOT NULL,
    closed_at     TEXT,                    -- NULL while open
    status        TEXT    NOT NULL DEFAULT 'open'
    -- status values: open | closed
);

CREATE TABLE IF NOT EXISTS heartbeats (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT    NOT NULL,
    ws_status           TEXT    NOT NULL,   -- connected | disconnected | reconnecting
    api_status          TEXT    NOT NULL,   -- ok | error
    ip_address          TEXT    DEFAULT '',
    ops_current         REAL    DEFAULT 0.0,
    claude_calls_today  INTEGER DEFAULT 0,
    notes               TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    date                  TEXT    NOT NULL UNIQUE,  -- YYYY-MM-DD
    mode                  TEXT    NOT NULL DEFAULT 'paper',
    gross_pnl             REAL    DEFAULT 0.0,
    net_pnl               REAL    DEFAULT 0.0,
    trades                INTEGER DEFAULT 0,
    wins                  INTEGER DEFAULT 0,
    losses                INTEGER DEFAULT 0,
    max_drawdown          REAL    DEFAULT 0.0,
    sharpe_ratio          REAL    DEFAULT 0.0,
    claude_calls          INTEGER DEFAULT 0,
    claude_avg_confidence REAL    DEFAULT 0.0,
    kill_switch_fires     INTEGER DEFAULT 0,
    rbi_window_violations INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS candles (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol    TEXT    NOT NULL DEFAULT 'USDINR',
    interval  TEXT    NOT NULL DEFAULT 'FIVE_MINUTE',
    timestamp TEXT    NOT NULL,
    open      REAL    NOT NULL,
    high      REAL    NOT NULL,
    low       REAL    NOT NULL,
    close     REAL    NOT NULL,
    volume    INTEGER NOT NULL DEFAULT 0,
    UNIQUE(symbol, interval, timestamp)
);

CREATE TABLE IF NOT EXISTS news (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    headline    TEXT    NOT NULL,
    url         TEXT    DEFAULT '',
    is_rbi_flag INTEGER DEFAULT 0,
    UNIQUE(headline, source)
);
"""


def init_db() -> None:
    """
    Create all 8 tables if they don't already exist.
    Safe to call on every startup.
    """
    with get_connection() as conn:
        conn.executescript(_SCHEMA)


# ── Utility ───────────────────────────────────────────────────────────────────

def _now() -> str:
    """Current IST time as ISO 8601 string."""
    return datetime.now(IST).isoformat()


def _today() -> str:
    """Current IST date as YYYY-MM-DD string."""
    return datetime.now(IST).strftime("%Y-%m-%d")


def table_counts() -> dict:
    """
    Return row count for each table.
    Used by --check to verify the schema is intact.
    """
    tables = ["sessions", "signals", "orders", "positions",
              "heartbeats", "daily_pnl", "candles", "news"]
    counts = {}
    with get_connection() as conn:
        for table in tables:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[table] = row[0]
    return counts


# ── sessions ──────────────────────────────────────────────────────────────────

def insert_session(token_hash: str, ip_address: str) -> int:
    """Log a new login event. Returns the new session row ID."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (login_time, token_hash, ip_address, status) "
            "VALUES (?, ?, ?, 'active')",
            (_now(), token_hash, ip_address),
        )
        return cur.lastrowid


def close_session(session_id: int, status: str = "logged_out") -> None:
    """Mark a session as closed with a logout timestamp."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE sessions SET logout_time=?, status=? WHERE id=?",
            (_now(), status, session_id),
        )


def get_active_session() -> Optional[sqlite3.Row]:
    """Return the current active session row, or None."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM sessions WHERE status='active' ORDER BY id DESC LIMIT 1"
        ).fetchone()


# ── heartbeats ────────────────────────────────────────────────────────────────

def insert_heartbeat(
    ws_status: str,
    api_status: str,
    ip_address: str = "",
    ops: float = 0.0,
    claude_calls: int = 0,
    notes: str = "",
) -> int:
    """Log a system health snapshot. Returns new row ID."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO heartbeats "
            "(timestamp, ws_status, api_status, ip_address, ops_current, claude_calls_today, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), ws_status, api_status, ip_address, ops, claude_calls, notes),
        )
        return cur.lastrowid


# ── signals ───────────────────────────────────────────────────────────────────

def insert_signal(
    symbol: str,
    action: str,
    z_score: float = 0.0,
    adx: float = 0.0,
    rsi: float = 0.0,
    atr: float = 0.0,
    ltp: float = 0.0,
    volume: int = 0,
    regime: str = "",
    filters_passed: list = None,
    filters_failed: list = None,
) -> int:
    """Log a signal candidate (whether executed or not). Returns new row ID."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO signals "
            "(timestamp, symbol, z_score, adx, rsi, atr, ltp, volume, "
            " regime, action, filters_passed, filters_failed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _now(), symbol, z_score, adx, rsi, atr, ltp, volume,
                regime, action,
                json.dumps(filters_passed or []),
                json.dumps(filters_failed or []),
            ),
        )
        return cur.lastrowid


def update_signal_claude(
    signal_id: int,
    confidence: int,
    reasoning: str,
    claude_action: str,
) -> None:
    """Attach Claude's validation decision to an existing signal row."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE signals "
            "SET claude_confidence=?, claude_reasoning=?, claude_action=? "
            "WHERE id=?",
            (confidence, reasoning, claude_action, signal_id),
        )


def mark_signal_executed(signal_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE signals SET executed=1 WHERE id=?", (signal_id,)
        )


# ── orders ────────────────────────────────────────────────────────────────────

def insert_order(
    symbol: str,
    order_type: str,
    qty: int,
    price: float,
    signal_id: int = None,
    algo_id: str = "",
) -> int:
    """Log a new order (pending state). Returns new row ID."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO orders "
            "(signal_id, symbol, order_type, qty, price, status, algo_id, timestamp) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (signal_id, symbol, order_type, qty, price, algo_id, _now()),
        )
        return cur.lastrowid


def update_order_status(
    order_id: int,
    status: str,
    fill_price: float = None,
    broker_order_id: str = "",
) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE orders "
            "SET status=?, fill_price=?, broker_order_id=? "
            "WHERE id=?",
            (status, fill_price, broker_order_id, order_id),
        )


# ── positions ─────────────────────────────────────────────────────────────────

def insert_position(symbol: str, lots: int, avg_price: float) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO positions (symbol, lots, avg_price, opened_at) "
            "VALUES (?, ?, ?, ?)",
            (symbol, lots, avg_price, _now()),
        )
        return cur.lastrowid


def update_position_mtm(position_id: int, mtm_pnl: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE positions SET mtm_pnl=? WHERE id=?",
            (mtm_pnl, position_id),
        )


def close_position(position_id: int, realized_pnl: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE positions SET status='closed', realized_pnl=?, closed_at=? WHERE id=?",
            (realized_pnl, _now(), position_id),
        )


def get_open_positions() -> list:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM positions WHERE status='open'"
        ).fetchall()


# ── daily_pnl ─────────────────────────────────────────────────────────────────

def get_or_create_daily_pnl(mode: str = "paper") -> sqlite3.Row:
    """Return today's daily_pnl row, creating it if it doesn't exist."""
    date = _today()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM daily_pnl WHERE date=?", (date,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO daily_pnl (date, mode) VALUES (?, ?)",
                (date, mode),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM daily_pnl WHERE date=?", (date,)
            ).fetchone()
        return row


def update_daily_pnl(date: str, **kwargs) -> None:
    """
    Update any column(s) in daily_pnl for a given date.
    Example: update_daily_pnl("2026-04-01", trades=5, wins=3, gross_pnl=240.0)
    """
    if not kwargs:
        return
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [date]
    with get_connection() as conn:
        conn.execute(f"UPDATE daily_pnl SET {cols} WHERE date=?", vals)


# ── candles ───────────────────────────────────────────────────────────────────

def upsert_candle(candle: dict) -> None:
    """
    Insert or replace a candle row.
    The UNIQUE(symbol, interval, timestamp) constraint ensures no duplicates
    when re-fetching historical data or replaying the same candle.
    """
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO candles
               (symbol, interval, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                candle["symbol"],
                candle["interval"],
                candle["timestamp"],
                candle["open"],
                candle["high"],
                candle["low"],
                candle["close"],
                candle["volume"],
            ),
        )


def count_candles(symbol: str = "USDINR", interval: str = None) -> int:
    """Return total stored candles for a given symbol/interval (or all intervals if interval=None)."""
    with get_connection() as conn:
        if interval:
            row = conn.execute(
                "SELECT COUNT(*) FROM candles WHERE symbol=? AND interval=?",
                (symbol, interval),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM candles WHERE symbol=?",
                (symbol,),
            ).fetchone()
    return row[0]


def clear_candles(symbol: str = "USDINR", interval: str = None) -> int:
    """
    Delete candle rows for a given symbol (and optionally interval).
    Returns number of rows deleted.
    Leaves all other audit tables (sessions, signals, orders, etc.) untouched.
    """
    with get_connection() as conn:
        if interval:
            cur = conn.execute(
                "DELETE FROM candles WHERE symbol=? AND interval=?",
                (symbol, interval),
            )
        else:
            cur = conn.execute(
                "DELETE FROM candles WHERE symbol=?",
                (symbol,),
            )
        return cur.rowcount


# ── news ──────────────────────────────────────────────────────────────────────

def insert_news_item(
    source: str,
    headline: str,
    url: str = "",
    is_rbi_flag: int = 0,
) -> bool:
    """
    Insert a news headline. Returns True if the row is new, False if duplicate.
    The UNIQUE(headline, source) constraint silently ignores duplicates via
    INSERT OR IGNORE so re-polling the same feed is safe.
    """
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO news
               (timestamp, source, headline, url, is_rbi_flag)
               VALUES (?, ?, ?, ?, ?)""",
            (_now(), source, headline, url, is_rbi_flag),
        )
        return cur.rowcount > 0   # True = new row inserted


def get_recent_news(n: int = 5) -> list:
    """Return the last N news items as a list of sqlite3.Row objects."""
    with get_connection() as conn:
        return conn.execute(
            """SELECT timestamp, source, headline, url, is_rbi_flag
               FROM news ORDER BY timestamp DESC LIMIT ?""",
            (n,),
        ).fetchall()
