"""
core/auth/angel_auth.py
=======================
Angel One SmartAPI authentication.

Flow every morning:
    1. Fetch public IP and log it (SEBI static IP traceability)
    2. Generate TOTP from stored secret
    3. Call generateSession — up to 3 retries with 10s backoff
    4. Store token hash (NOT the full token) in SQLite sessions table
    5. Return SessionData with the live SmartConnect object

The full JWT is never written to disk or logs — only the first 8 characters
are stored as a reference hash for audit purposes.
"""

import time
from dataclasses import dataclass
from typing import Optional

import pyotp
import requests
from SmartApi import SmartConnect

from config.settings import (
    ANGEL_ONE_API_KEY,
    ANGEL_ONE_CLIENT_ID,
    ANGEL_ONE_PASSWORD,
    ANGEL_ONE_TOTP_SECRET,
)
from core.audit.database import close_session, insert_heartbeat, insert_session
from core.audit.logger import get_logger

log = get_logger("auth")

MAX_LOGIN_RETRIES = 3
RETRY_DELAY_SEC   = 10


@dataclass
class SessionData:
    """Holds all state returned by a successful Angel One login."""
    smart_connect:  SmartConnect
    jwt_token:      str           # full Bearer token (kept in memory only)
    refresh_token:  str
    feed_token:     str           # needed for WebSocket in Phase 2
    session_id:     int           # SQLite sessions row ID
    public_ip:      str


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_public_ip() -> str:
    """
    Return the current public IP address.
    Used for SEBI traceability logging — every order must originate from
    the registered static IP after April 1 2026.
    Returns 'unknown' on network failure rather than crashing.
    """
    try:
        resp = requests.get("https://api.ipify.org", timeout=5)
        return resp.text.strip()
    except Exception:
        return "unknown"


def _generate_totp() -> str:
    """Generate the current 6-digit TOTP from the stored TOTP secret."""
    return pyotp.TOTP(ANGEL_ONE_TOTP_SECRET).now()


def _token_prefix(jwt: str) -> str:
    """Return the first 8 characters of a JWT for audit storage only."""
    return jwt[:8] if jwt else ""


# ── Public API ────────────────────────────────────────────────────────────────

def login() -> SessionData:
    """
    Authenticate with Angel One SmartAPI.

    Retries up to MAX_LOGIN_RETRIES times on failure.
    Raises RuntimeError if all attempts are exhausted.
    """
    public_ip = _get_public_ip()
    log.info(f"Login started | ip={public_ip}")
    insert_heartbeat(
        ws_status="disconnected",
        api_status="connecting",
        ip_address=public_ip,
        notes="login attempt started",
    )

    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_LOGIN_RETRIES + 1):
        try:
            totp = _generate_totp()
            obj  = SmartConnect(api_key=ANGEL_ONE_API_KEY)
            resp = obj.generateSession(ANGEL_ONE_CLIENT_ID, ANGEL_ONE_PASSWORD, totp)

            # Angel One returns {"status": True/False, "data": {...}}
            if not resp or not resp.get("status"):
                msg = (resp or {}).get("message", "empty response")
                raise ValueError(f"Angel One rejected login: {msg}")

            data          = resp["data"]
            jwt_token     = data["jwtToken"]
            refresh_token = data["refreshToken"]
            feed_token    = data["feedToken"]

            # Store only token prefix — never the full credential
            session_id = insert_session(
                token_hash=_token_prefix(jwt_token),
                ip_address=public_ip,
            )
            insert_heartbeat(
                ws_status="connected",
                api_status="ok",
                ip_address=public_ip,
                notes=f"login success attempt={attempt}",
            )

            log.info(f"Login successful | session_id={session_id} | attempt={attempt}/{MAX_LOGIN_RETRIES}")
            return SessionData(
                smart_connect=obj,
                jwt_token=jwt_token,
                refresh_token=refresh_token,
                feed_token=feed_token,
                session_id=session_id,
                public_ip=public_ip,
            )

        except Exception as exc:
            last_error = exc
            log.warning(f"Login attempt {attempt}/{MAX_LOGIN_RETRIES} failed: {exc}")
            if attempt < MAX_LOGIN_RETRIES:
                log.info(f"Retrying in {RETRY_DELAY_SEC}s...")
                time.sleep(RETRY_DELAY_SEC)

    insert_heartbeat(
        ws_status="disconnected",
        api_status="error",
        ip_address=public_ip,
        notes=f"login failed after {MAX_LOGIN_RETRIES} attempts: {last_error}",
    )
    raise RuntimeError(
        f"Angel One login failed after {MAX_LOGIN_RETRIES} attempts. "
        f"Last error: {last_error}"
    )


def logout(session: SessionData) -> None:
    """
    Terminate the Angel One session via API and mark it closed in SQLite.
    Even if the API call fails, the DB row is always updated — we never
    leave a session marked 'active' overnight (SEBI mandate).
    """
    try:
        session.smart_connect.terminateSession(ANGEL_ONE_CLIENT_ID)
        log.info(f"Logout API call successful | session_id={session.session_id}")
    except Exception as exc:
        log.warning(f"Logout API call failed (DB will still be updated): {exc}")
    finally:
        close_session(session.session_id, status="logged_out")
        log.info(f"Session closed in DB | session_id={session.session_id}")


def get_profile(session: SessionData) -> dict:
    """
    Fetch the Angel One account profile for the active session.
    Returns an empty dict on failure rather than raising.
    """
    try:
        resp = session.smart_connect.getProfile(session.refresh_token)
        if resp and resp.get("status"):
            return resp.get("data", {})
        return {}
    except Exception as exc:
        log.error(f"getProfile failed: {exc}")
        return {}
