"""
tests/conftest.py
=================
Shared pytest configuration and fixtures.

Markers:
    integration — requires real Angel One credentials; skip in normal test runs.
                  Run with: pytest -m integration -v

Fixtures:
    fresh_db    — gives each test an isolated in-memory SQLite database.
"""

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that make real API calls (run manually only)",
    )


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """
    Redirect DB_PATH to a temp file for the duration of one test.
    Because database.get_connection() resolves DB_PATH at call time
    (lazy import), monkeypatching config.settings.DB_PATH is sufficient.
    """
    db_file = tmp_path / "test_claudey_tr.db"
    monkeypatch.setattr("config.settings.DB_PATH", db_file)

    from core.audit.database import init_db
    init_db()
    yield db_file
