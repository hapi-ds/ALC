"""Unit tests for AuthService JWT token management and password verification.

Tests cover:
- Task 2.3: Auth service unit tests
  - Token creation returns valid JWTs with correct claims
  - Password verification with correct and incorrect passwords
  - Refresh token revocation marks token as revoked
  - Expired token detection

References:
    - Design: .kiro/specs/auth-session-frontend/design.md
    - Requirements: 2.1, 2.2, 5.1
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jose import jwt

from alcoabase.services.auth_service import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    AuthService,
    _pwd_context,
)

# ---------------------------------------------------------------------------
# bcrypt compatibility patch (bcrypt 5.x + passlib 1.7.4)
# ---------------------------------------------------------------------------
import bcrypt as _bcrypt_lib

_original_hashpw = _bcrypt_lib.hashpw
_original_checkpw = _bcrypt_lib.checkpw


def _safe_hashpw(password: bytes, salt: bytes) -> bytes:
    if isinstance(password, str):
        password = password.encode("utf-8")
    return _original_hashpw(password[:72], salt)


def _safe_checkpw(password: bytes, hashed_password: bytes) -> bool:
    if isinstance(password, str):
        password = password.encode("utf-8")
    return _original_checkpw(password[:72], hashed_password)


_bcrypt_lib.hashpw = _safe_hashpw
_bcrypt_lib.checkpw = _safe_checkpw


# ---------------------------------------------------------------------------
# Test Constants
# ---------------------------------------------------------------------------

TEST_SECRET_KEY = "test-secret-key-for-unit-tests"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_service():
    """Create an AuthService instance with a mocked settings object."""
    with patch("alcoabase.services.auth_service.get_settings") as mock_settings:
        settings = MagicMock()
        settings.secret_key = TEST_SECRET_KEY
        mock_settings.return_value = settings
        service = AuthService()
    return service


@pytest.fixture
def async_session():
    """Create a mock AsyncSession for database operations."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


# ===========================================================================
# Test: create_access_token returns valid JWT with correct claims
# Validates: Requirement 2.1
# ===========================================================================


class TestCreateAccessToken:
    """Tests for AuthService.create_access_token."""

    def test_returns_valid_jwt_with_correct_claims(self, auth_service):
        """Access token contains sub, username, exp, iat, type='access'."""
        token = auth_service.create_access_token(user_id=42, username="alice")

        payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=[ALGORITHM])

        assert payload["sub"] == "42"
        assert payload["username"] == "alice"
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    def test_exp_is_15_minutes_from_now(self, auth_service):
        """Access token expires approximately 15 minutes from creation."""
        before = datetime.now(timezone.utc)
        token = auth_service.create_access_token(user_id=1, username="bob")
        after = datetime.now(timezone.utc)

        payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=[ALGORITHM])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

        # JWT exp is integer seconds, so allow 1 second tolerance
        expected_min = before + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES) - timedelta(seconds=1)
        expected_max = after + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES) + timedelta(seconds=1)

        assert expected_min <= exp <= expected_max

    def test_sub_is_string_representation_of_user_id(self, auth_service):
        """The sub claim is the user_id converted to string."""
        token = auth_service.create_access_token(user_id=999, username="charlie")
        payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=[ALGORITHM])

        assert payload["sub"] == "999"
        assert isinstance(payload["sub"], str)


# ===========================================================================
# Test: create_refresh_token returns valid JWT with correct claims and stores in DB
# Validates: Requirement 2.2
# ===========================================================================


class TestCreateRefreshToken:
    """Tests for AuthService.create_refresh_token."""

    @pytest.mark.asyncio
    async def test_returns_valid_jwt_with_correct_claims(
        self, auth_service, async_session
    ):
        """Refresh token contains sub, exp, iat, jti, type='refresh'."""
        token = await auth_service.create_refresh_token(
            session=async_session, user_id=42
        )

        payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=[ALGORITHM])

        assert payload["sub"] == "42"
        assert payload["type"] == "refresh"
        assert "exp" in payload
        assert "iat" in payload
        assert "jti" in payload

    @pytest.mark.asyncio
    async def test_jti_is_uuid_format(self, auth_service, async_session):
        """The jti claim is a valid UUID4 string."""
        token = await auth_service.create_refresh_token(
            session=async_session, user_id=1
        )

        payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload["jti"]

        # UUID4 format: 8-4-4-4-12 hex characters
        parts = jti.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    @pytest.mark.asyncio
    async def test_stores_token_in_database(self, auth_service, async_session):
        """Refresh token is stored in the database via session.add and flush."""
        await auth_service.create_refresh_token(session=async_session, user_id=42)

        # Verify session.add was called with a RefreshToken instance
        async_session.add.assert_called_once()
        db_token = async_session.add.call_args[0][0]

        assert db_token.user_id == 42
        assert db_token.jti is not None
        assert db_token.expires_at is not None

        # Verify flush was called to persist
        async_session.flush.assert_awaited_once()


# ===========================================================================
# Test: verify_password with correct and incorrect passwords
# Validates: Requirement 2.1
# ===========================================================================


class TestVerifyPassword:
    """Tests for AuthService.verify_password."""

    def test_returns_true_for_correct_password(self, auth_service):
        """verify_password returns True when password matches hash."""
        plain = "SecureP@ss123!"
        hashed = _pwd_context.hash(plain)

        assert auth_service.verify_password(plain, hashed) is True

    def test_returns_false_for_incorrect_password(self, auth_service):
        """verify_password returns False when password does not match hash."""
        hashed = _pwd_context.hash("CorrectPassword1!")

        assert auth_service.verify_password("WrongPassword1!", hashed) is False

    def test_returns_false_for_empty_password(self, auth_service):
        """verify_password returns False for empty string against a valid hash."""
        hashed = _pwd_context.hash("SomePassword1!")

        assert auth_service.verify_password("", hashed) is False


# ===========================================================================
# Test: revoke_refresh_token marks token as revoked
# Validates: Requirement 2.2
# ===========================================================================


class TestRevokeRefreshToken:
    """Tests for AuthService.revoke_refresh_token."""

    @pytest.mark.asyncio
    async def test_sets_revoked_at_timestamp(self, auth_service, async_session):
        """Revoking a token sets the revoked_at field to current UTC time."""
        # Mock the database query to return a token
        mock_token = MagicMock()
        mock_token.revoked_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_token
        async_session.execute.return_value = mock_result

        before = datetime.now(timezone.utc)
        result = await auth_service.revoke_refresh_token(
            session=async_session, jti="test-jti-123"
        )
        after = datetime.now(timezone.utc)

        assert result is True
        assert mock_token.revoked_at is not None
        assert before <= mock_token.revoked_at <= after
        async_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_token_not_found(
        self, auth_service, async_session
    ):
        """Revoking a non-existent token returns False."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        async_session.execute.return_value = mock_result

        result = await auth_service.revoke_refresh_token(
            session=async_session, jti="nonexistent-jti"
        )

        assert result is False


# ===========================================================================
# Test: Expired token detection
# Validates: Requirement 5.1
# ===========================================================================


class TestDecodeAccessToken:
    """Tests for AuthService.decode_access_token."""

    def test_returns_payload_for_valid_token(self, auth_service):
        """decode_access_token returns the payload for a valid access token."""
        token = auth_service.create_access_token(user_id=1, username="alice")

        payload = auth_service.decode_access_token(token)

        assert payload is not None
        assert payload["sub"] == "1"
        assert payload["username"] == "alice"
        assert payload["type"] == "access"

    def test_returns_none_for_expired_token(self, auth_service):
        """decode_access_token returns None for an expired token."""
        # Create a token that expired 1 hour ago
        now = datetime.now(timezone.utc)
        expired_payload = {
            "sub": "1",
            "username": "alice",
            "exp": now - timedelta(hours=1),
            "iat": now - timedelta(hours=2),
            "type": "access",
        }
        expired_token = jwt.encode(
            expired_payload, TEST_SECRET_KEY, algorithm=ALGORITHM
        )

        result = auth_service.decode_access_token(expired_token)

        assert result is None

    def test_returns_none_for_invalid_signature(self, auth_service):
        """decode_access_token returns None for a token signed with wrong key."""
        payload = {
            "sub": "1",
            "username": "alice",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc),
            "type": "access",
        }
        bad_token = jwt.encode(payload, "wrong-secret-key", algorithm=ALGORITHM)

        result = auth_service.decode_access_token(bad_token)

        assert result is None


class TestDecodeRefreshToken:
    """Tests for AuthService.decode_refresh_token."""

    @pytest.mark.asyncio
    async def test_returns_none_for_token_with_wrong_type(
        self, auth_service, async_session
    ):
        """decode_refresh_token returns None for an access token (wrong type)."""
        # Create an access token and try to decode it as refresh
        access_token = auth_service.create_access_token(
            user_id=1, username="alice"
        )

        result = auth_service.decode_refresh_token(access_token)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_payload_for_valid_refresh_token(
        self, auth_service, async_session
    ):
        """decode_refresh_token returns payload for a valid refresh token."""
        token = await auth_service.create_refresh_token(
            session=async_session, user_id=1
        )

        payload = auth_service.decode_refresh_token(token)

        assert payload is not None
        assert payload["sub"] == "1"
        assert payload["type"] == "refresh"
        assert "jti" in payload

    def test_returns_none_for_expired_refresh_token(self, auth_service):
        """decode_refresh_token returns None for an expired refresh token."""
        now = datetime.now(timezone.utc)
        expired_payload = {
            "sub": "1",
            "exp": now - timedelta(hours=1),
            "iat": now - timedelta(days=8),
            "jti": "some-jti-value",
            "type": "refresh",
        }
        expired_token = jwt.encode(
            expired_payload, TEST_SECRET_KEY, algorithm=ALGORITHM
        )

        result = auth_service.decode_refresh_token(expired_token)

        assert result is None
