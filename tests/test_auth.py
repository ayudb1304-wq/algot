"""
tests/test_auth.py
==================
Tests for Angel One authentication (angel_auth + session_manager).

Unit tests: fully mocked, no API calls, run in CI.
Integration test: real API call, run manually only.

Run unit tests:
    pytest tests/test_auth.py -v

Run integration test:
    pytest tests/test_auth.py -m integration -v
"""

from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_login_response():
    """Minimal valid Angel One generateSession response."""
    return {
        "status": True,
        "message": "SUCCESS",
        "errorcode": "",
        "data": {
            "jwtToken":     "Bearer eyTestJWTToken123456",
            "refreshToken": "refreshTestToken",
            "feedToken":    "feedTestToken",
            "clientcode":   "TEST001",
            "name":         "Test User",
        },
    }


def _mock_profile_response():
    return {
        "status": True,
        "data": {
            "clientcode": "TEST001",
            "name":       "Test User",
            "email":      "test@example.com",
        },
    }


# ── TOTP ──────────────────────────────────────────────────────────────────────

class TestTOTP:
    def test_generates_six_digit_string(self):
        """TOTP output must be exactly 6 numeric digits."""
        from core.auth.angel_auth import _generate_totp
        totp = _generate_totp()
        assert len(totp) == 6, f"Expected 6 digits, got: {totp!r}"
        assert totp.isdigit(), f"TOTP should be numeric, got: {totp!r}"

    def test_returns_string_type(self):
        from core.auth.angel_auth import _generate_totp
        assert isinstance(_generate_totp(), str)


# ── IP check ──────────────────────────────────────────────────────────────────

class TestIPCheck:
    def test_returns_ip_on_success(self):
        with patch("requests.get") as mock_get:
            mock_get.return_value.text = "203.0.113.42"
            from core.auth.angel_auth import _get_public_ip
            assert _get_public_ip() == "203.0.113.42"

    def test_returns_unknown_on_network_error(self):
        """Must not raise — returns 'unknown' so the bot continues."""
        with patch("requests.get", side_effect=ConnectionError("network down")):
            from core.auth.angel_auth import _get_public_ip
            assert _get_public_ip() == "unknown"

    def test_returns_unknown_on_timeout(self):
        with patch("requests.get", side_effect=TimeoutError("timeout")):
            from core.auth.angel_auth import _get_public_ip
            assert _get_public_ip() == "unknown"


# ── Login ─────────────────────────────────────────────────────────────────────

class TestLogin:
    @patch("core.auth.angel_auth._get_public_ip", return_value="1.2.3.4")
    @patch("core.auth.angel_auth._generate_totp",  return_value="123456")
    @patch("core.auth.angel_auth.SmartConnect")
    def test_successful_login_returns_session_data(self, MockSC, mock_totp, mock_ip, fresh_db):
        mock_obj = MagicMock()
        mock_obj.generateSession.return_value = _mock_login_response()
        MockSC.return_value = mock_obj

        from core.auth.angel_auth import login
        session = login()

        assert session.jwt_token     == "Bearer eyTestJWTToken123456"
        assert session.refresh_token == "refreshTestToken"
        assert session.feed_token    == "feedTestToken"
        assert session.public_ip     == "1.2.3.4"
        assert session.session_id is not None

    @patch("core.auth.angel_auth._get_public_ip", return_value="1.2.3.4")
    @patch("core.auth.angel_auth._generate_totp",  return_value="123456")
    @patch("core.auth.angel_auth.SmartConnect")
    def test_login_writes_session_to_db(self, MockSC, mock_totp, mock_ip, fresh_db):
        """SQLite sessions table must have a row after login."""
        mock_obj = MagicMock()
        mock_obj.generateSession.return_value = _mock_login_response()
        MockSC.return_value = mock_obj

        from core.auth.angel_auth import login
        from core.audit.database import get_connection
        session = login()

        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id=?", (session.session_id,)
            ).fetchone()

        assert row is not None
        assert row["status"]     == "active"
        assert row["ip_address"] == "1.2.3.4"

    @patch("core.auth.angel_auth._get_public_ip", return_value="1.2.3.4")
    @patch("core.auth.angel_auth._generate_totp",  return_value="123456")
    @patch("core.auth.angel_auth.SmartConnect")
    def test_full_token_never_stored_in_db(self, MockSC, mock_totp, mock_ip, fresh_db):
        """The full JWT must never be written to disk — only the 8-char prefix."""
        mock_obj = MagicMock()
        mock_obj.generateSession.return_value = _mock_login_response()
        MockSC.return_value = mock_obj

        from core.auth.angel_auth import login
        from core.audit.database import get_connection
        session = login()

        full_token = "Bearer eyTestJWTToken123456"

        with get_connection() as conn:
            row = conn.execute(
                "SELECT token_hash FROM sessions WHERE id=?", (session.session_id,)
            ).fetchone()

        assert row["token_hash"] != full_token
        assert len(row["token_hash"]) == 8

    @patch("core.auth.angel_auth._get_public_ip", return_value="1.2.3.4")
    @patch("core.auth.angel_auth._generate_totp",  return_value="123456")
    @patch("core.auth.angel_auth.SmartConnect")
    def test_failed_login_retries_max_times(self, MockSC, mock_totp, mock_ip, fresh_db):
        """Login must retry exactly MAX_LOGIN_RETRIES times before raising."""
        mock_obj = MagicMock()
        mock_obj.generateSession.return_value = {"status": False, "message": "Invalid TOTP"}
        MockSC.return_value = mock_obj

        from core.auth.angel_auth import login, MAX_LOGIN_RETRIES
        with patch("core.auth.angel_auth.time.sleep"):   # don't actually wait
            with pytest.raises(RuntimeError, match="login failed after"):
                login()

        assert mock_obj.generateSession.call_count == MAX_LOGIN_RETRIES

    @patch("core.auth.angel_auth._get_public_ip", return_value="1.2.3.4")
    @patch("core.auth.angel_auth._generate_totp",  return_value="123456")
    @patch("core.auth.angel_auth.SmartConnect")
    def test_exception_during_login_retries(self, MockSC, mock_totp, mock_ip, fresh_db):
        """Network exceptions mid-login should trigger retries, not immediate crash."""
        mock_obj = MagicMock()
        mock_obj.generateSession.side_effect = ConnectionError("timeout")
        MockSC.return_value = mock_obj

        from core.auth.angel_auth import login, MAX_LOGIN_RETRIES
        with patch("core.auth.angel_auth.time.sleep"):
            with pytest.raises(RuntimeError):
                login()

        assert mock_obj.generateSession.call_count == MAX_LOGIN_RETRIES


# ── Logout ────────────────────────────────────────────────────────────────────

class TestLogout:
    @patch("core.auth.angel_auth._get_public_ip", return_value="1.2.3.4")
    @patch("core.auth.angel_auth._generate_totp",  return_value="123456")
    @patch("core.auth.angel_auth.SmartConnect")
    def test_logout_marks_session_closed(self, MockSC, mock_totp, mock_ip, fresh_db):
        mock_obj = MagicMock()
        mock_obj.generateSession.return_value = _mock_login_response()
        MockSC.return_value = mock_obj

        from core.auth.angel_auth import login, logout
        from core.audit.database import get_connection
        session = login()
        logout(session)

        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id=?", (session.session_id,)
            ).fetchone()

        assert row["status"]      == "logged_out"
        assert row["logout_time"] is not None

    @patch("core.auth.angel_auth._get_public_ip", return_value="1.2.3.4")
    @patch("core.auth.angel_auth._generate_totp",  return_value="123456")
    @patch("core.auth.angel_auth.SmartConnect")
    def test_logout_db_closed_even_if_api_fails(self, MockSC, mock_totp, mock_ip, fresh_db):
        """DB session must be marked closed even if terminateSession raises."""
        mock_obj = MagicMock()
        mock_obj.generateSession.return_value = _mock_login_response()
        mock_obj.terminateSession.side_effect = Exception("API error")
        MockSC.return_value = mock_obj

        from core.auth.angel_auth import login, logout
        from core.audit.database import get_connection
        session = login()
        logout(session)   # must not raise

        with get_connection() as conn:
            row = conn.execute(
                "SELECT status FROM sessions WHERE id=?", (session.session_id,)
            ).fetchone()
        assert row["status"] == "logged_out"


# ── Session manager ───────────────────────────────────────────────────────────

class TestSessionManager:
    def setup_method(self):
        """Reset session manager state before each test."""
        import core.auth.session_manager as sm
        sm._session = None

    @patch("core.auth.angel_auth._get_public_ip", return_value="1.2.3.4")
    @patch("core.auth.angel_auth._generate_totp",  return_value="123456")
    @patch("core.auth.angel_auth.SmartConnect")
    def test_not_authenticated_before_login(self, MockSC, mock_totp, mock_ip):
        import core.auth.session_manager as sm
        assert sm.is_authenticated() is False

    @patch("core.auth.angel_auth._get_public_ip", return_value="1.2.3.4")
    @patch("core.auth.angel_auth._generate_totp",  return_value="123456")
    @patch("core.auth.angel_auth.SmartConnect")
    def test_authenticated_after_manual_login(self, MockSC, mock_totp, mock_ip, fresh_db):
        mock_obj = MagicMock()
        mock_obj.generateSession.return_value = _mock_login_response()
        MockSC.return_value = mock_obj

        import core.auth.session_manager as sm
        sm.manual_login()

        assert sm.is_authenticated() is True
        assert sm.get_smart_connect() is mock_obj
        sm.manual_logout()

    @patch("core.auth.angel_auth._get_public_ip", return_value="1.2.3.4")
    @patch("core.auth.angel_auth._generate_totp",  return_value="123456")
    @patch("core.auth.angel_auth.SmartConnect")
    def test_not_authenticated_after_logout(self, MockSC, mock_totp, mock_ip, fresh_db):
        mock_obj = MagicMock()
        mock_obj.generateSession.return_value = _mock_login_response()
        MockSC.return_value = mock_obj

        import core.auth.session_manager as sm
        sm.manual_login()
        sm.manual_logout()

        assert sm.is_authenticated() is False

    def test_get_smart_connect_raises_before_login(self):
        import core.auth.session_manager as sm
        with pytest.raises(RuntimeError, match="Not authenticated"):
            sm.get_smart_connect()

    def test_get_feed_token_raises_before_login(self):
        import core.auth.session_manager as sm
        with pytest.raises(RuntimeError, match="Not authenticated"):
            sm.get_feed_token()

    @patch("core.auth.angel_auth._get_public_ip", return_value="1.2.3.4")
    @patch("core.auth.angel_auth._generate_totp",  return_value="123456")
    @patch("core.auth.angel_auth.SmartConnect")
    def test_double_login_reuses_session(self, MockSC, mock_totp, mock_ip, fresh_db):
        """Calling manual_login() twice should not create two sessions."""
        mock_obj = MagicMock()
        mock_obj.generateSession.return_value = _mock_login_response()
        MockSC.return_value = mock_obj

        import core.auth.session_manager as sm
        s1 = sm.manual_login()
        s2 = sm.manual_login()   # should reuse existing session

        assert s1.session_id == s2.session_id
        assert mock_obj.generateSession.call_count == 1   # only one real login
        sm.manual_logout()


# ── Integration test (real API — run manually) ────────────────────────────────

@pytest.mark.integration
class TestRealAngelOneLogin:
    def test_full_login_profile_logout_cycle(self):
        """
        INTEGRATION — makes real Angel One API calls.
        Run with: pytest tests/test_auth.py -m integration -v
        """
        from core.auth.angel_auth import get_profile, login, logout

        session = login()

        assert session.jwt_token.startswith("Bearer "), \
            f"Unexpected token format: {session.jwt_token[:20]}..."
        assert len(session.feed_token) > 0, "Feed token should not be empty"
        assert session.session_id is not None

        profile = get_profile(session)
        assert "clientcode" in profile, f"Profile missing clientcode: {profile}"
        print(f"\n  Logged in as: {profile.get('name')} ({profile.get('clientcode')})")
        print(f"  Public IP:    {session.public_ip}")

        logout(session)

        from core.audit.database import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT status FROM sessions WHERE id=?", (session.session_id,)
            ).fetchone()
        assert row["status"] == "logged_out"
        print("  Session closed and DB updated correctly.")
