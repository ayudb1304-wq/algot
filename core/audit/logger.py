"""
core/audit/logger.py
====================
Structured logging for claudey-tr.

Console output  →  human-readable, colour-coded by level
File output     →  JSON lines at logs/YYYY-MM-DD.log (IST date)

Usage:
    from core.audit.logger import get_logger
    log = get_logger("strategy")
    log.info("Signal generated")
    log.warning("RBI window active — skipping entry")
    log.error("WebSocket disconnected")
"""

import io
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pytz

from config.settings import LOGS_DIR, IST

# Enable UTF-8 on Windows stdout so box/emoji chars don't crash
if hasattr(sys.stdout, "buffer") and sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ── Custom formatters ─────────────────────────────────────────────────────────

class _ISTFormatter(logging.Formatter):
    """Base formatter that stamps records with IST time."""

    def formatTime(self, record: logging.LogRecord, datefmt=None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=IST)
        return dt.strftime("%Y-%m-%d %H:%M:%S IST")


class _JSONFileFormatter(_ISTFormatter):
    """Writes each log record as a single JSON line (machine-readable)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts":     self.formatTime(record),
            "level":  record.levelname,
            "logger": record.name,
            "msg":    record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Any extra fields passed via record.__dict__ are included
        for key, val in record.__dict__.items():
            if key.startswith("x_"):          # convention: extra fields prefixed x_
                payload[key[2:]] = val
        return json.dumps(payload, ensure_ascii=False)


class _ConsoleFormatter(_ISTFormatter):
    """Colour-coded console output (colours disabled automatically on Windows)."""

    _COLOURS = {
        "DEBUG":    "\033[36m",   # cyan
        "INFO":     "\033[32m",   # green
        "WARNING":  "\033[33m",   # yellow
        "ERROR":    "\033[31m",   # red
        "CRITICAL": "\033[35m",   # magenta
    }
    _RESET = "\033[0m"

    # Disable ANSI colours on Windows terminals that don't support them
    _USE_COLOUR = sys.platform != "win32"

    def format(self, record: logging.LogRecord) -> str:
        ts  = self.formatTime(record)
        tag = f"[{record.name.upper():<12}]"
        msg = record.getMessage()
        suffix = ""
        if record.exc_info:
            suffix = "\n" + self.formatException(record.exc_info)
        if self._USE_COLOUR:
            colour = self._COLOURS.get(record.levelname, "")
            return f"{colour}{ts} {tag} {msg}{suffix}{self._RESET}"
        # Plain output for Windows
        return f"{ts} {tag} {msg}{suffix}"


# ── Root logger setup ─────────────────────────────────────────────────────────

def _log_file_path() -> Path:
    date_str = datetime.now(IST).strftime("%Y-%m-%d")
    return LOGS_DIR / f"{date_str}.log"


def _configure_root_logger() -> None:
    """Configure root logger once. Safe to call multiple times (idempotent)."""
    root = logging.getLogger()
    if root.handlers:
        return  # already configured — don't add duplicate handlers

    root.setLevel(logging.DEBUG)

    # Console: INFO and above, human-readable
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(_ConsoleFormatter())
    root.addHandler(console_handler)

    # File: DEBUG and above, JSON lines
    file_handler = logging.FileHandler(str(_log_file_path()), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_JSONFileFormatter())
    root.addHandler(file_handler)


_configure_root_logger()


# ── Public API ────────────────────────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger for the given module.

    Naming convention:
        get_logger("auth")       → authentication events
        get_logger("feed")       → market data feed
        get_logger("strategy")   → signal generation
        get_logger("claude")     → Claude API calls
        get_logger("risk")       → risk management & kill switch
        get_logger("execution")  → order placement
        get_logger("paper")      → paper trading engine
        get_logger("main")       → entry point / orchestrator
    """
    return logging.getLogger(name)
