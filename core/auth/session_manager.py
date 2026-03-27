"""
core/auth/session_manager.py
============================
Global session lifecycle manager.

Provides a single authenticated SmartConnect object accessible to all modules.
Schedules the mandatory daily login (08:50 AM) and logout (11:59 PM) per SEBI rules.

Usage from other modules:
    from core.auth.session_manager import get_smart_connect, get_feed_token

    smart = get_smart_connect()   # raises if not authenticated
    feed  = get_feed_token()      # needed for WebSocket (Phase 2)
"""

import threading
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import IST, SESSION_LOGIN_AT, SESSION_LOGOUT_AT
from core.audit.logger import get_logger
from core.auth.angel_auth import SessionData, login, logout

log = get_logger("auth")

# ── Module-level state ────────────────────────────────────────────────────────
# Protected by _lock so concurrent access during scheduled jobs is safe.
_session:   Optional[SessionData]      = None
_lock:      threading.Lock             = threading.Lock()
_scheduler: Optional[BackgroundScheduler] = None


# ── Session access (used by all other modules) ────────────────────────────────

def is_authenticated() -> bool:
    """True if there is an active authenticated session."""
    return _session is not None


def get_smart_connect():
    """
    Return the authenticated SmartConnect object.

    Raises RuntimeError if not yet authenticated — callers should check
    is_authenticated() first or catch the error and wait.
    """
    if _session is None:
        raise RuntimeError(
            "Not authenticated. Call session_manager.manual_login() first, "
            "or wait for the scheduled 08:50 AM IST login."
        )
    return _session.smart_connect


def get_feed_token() -> str:
    """Return the WebSocket feed token (needed in Phase 2 for market data)."""
    if _session is None:
        raise RuntimeError("Not authenticated.")
    return _session.feed_token


def get_refresh_token() -> str:
    """Return the refresh token (needed for getProfile calls)."""
    if _session is None:
        raise RuntimeError("Not authenticated.")
    return _session.refresh_token


def get_session_id() -> Optional[int]:
    """Return the current SQLite session row ID, or None if not authenticated."""
    return _session.session_id if _session else None


# ── Login / logout ────────────────────────────────────────────────────────────

def manual_login() -> SessionData:
    """
    Authenticate immediately — bypasses the scheduler.
    Used by:
        - python main.py --test-auth
        - Initial startup if launched outside scheduled hours
        - Recovery after unexpected disconnection

    If already authenticated, returns the existing session without re-logging.
    """
    global _session
    with _lock:
        if _session is not None:
            log.info("Already authenticated — returning existing session.")
            return _session
        log.info("Manual login started.")
        _session = login()
        return _session


def manual_logout() -> None:
    """Log out immediately and clear the in-memory session."""
    global _session
    with _lock:
        if _session is None:
            log.info("No active session to log out.")
            return
        logout(_session)
        _session = None
        log.info("Session cleared.")


# ── Scheduled jobs ────────────────────────────────────────────────────────────

def _scheduled_login() -> None:
    """Triggered by APScheduler at SESSION_LOGIN_AT (08:50 AM IST, Mon-Fri)."""
    global _session
    with _lock:
        log.info("Scheduled daily login triggered.")
        try:
            _session = login()
            log.info("Scheduled login complete.")
        except Exception as exc:
            log.error(f"Scheduled login FAILED — bot will not trade today: {exc}")


def _scheduled_logout() -> None:
    """
    Triggered by APScheduler at SESSION_LOGOUT_AT (11:59 PM IST, Mon-Fri).
    SEBI mandates that all API sessions are terminated before the next trading day.
    """
    global _session
    with _lock:
        log.info("Scheduled daily logout triggered (SEBI mandatory).")
        if _session is not None:
            logout(_session)
            _session = None
        log.info("Session cleared for the night.")


# ── Scheduler ─────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """
    Start the background APScheduler for daily login/logout.
    Safe to call multiple times — idempotent.
    """
    global _scheduler
    if _scheduler and _scheduler.running:
        log.info("Scheduler already running — skipping start.")
        return

    _scheduler = BackgroundScheduler(timezone=IST)

    # Login: 08:50 AM IST, Monday to Friday
    _scheduler.add_job(
        _scheduled_login,
        CronTrigger(
            hour=SESSION_LOGIN_AT.hour,
            minute=SESSION_LOGIN_AT.minute,
            day_of_week="mon-fri",
            timezone=IST,
        ),
        id="daily_login",
        replace_existing=True,
    )

    # Logout: 11:59 PM IST, Monday to Friday
    _scheduler.add_job(
        _scheduled_logout,
        CronTrigger(
            hour=SESSION_LOGOUT_AT.hour,
            minute=SESSION_LOGOUT_AT.minute,
            day_of_week="mon-fri",
            timezone=IST,
        ),
        id="daily_logout",
        replace_existing=True,
    )

    _scheduler.start()
    log.info(
        f"Scheduler running | "
        f"login={SESSION_LOGIN_AT.strftime('%H:%M')} IST | "
        f"logout={SESSION_LOGOUT_AT.strftime('%H:%M')} IST | "
        f"Mon-Fri only"
    )


def stop_scheduler() -> None:
    """Gracefully stop the scheduler (call on application shutdown)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler stopped.")
