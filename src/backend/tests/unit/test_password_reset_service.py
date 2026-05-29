"""Unit tests for PasswordResetService.

Tests temporary password generation, password hashing, user update,
and refresh token invalidation.

References:
    - Requirement 9.1: Generate new temporary password on admin reset
    - Requirement 9.2: Hash temporary password with bcrypt
    - Requirement 9.3: Display temporary password to admin
    - Requirement 9.4: Record reset in audit trail without logging password
    - Requirement 9.5: Invalidate all refresh tokens on password reset
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.user import User
from alcoabase.services.password_reset import (
    generate_temporary_password,
    reset_password,
)


class TestGenerateTemporaryPassword:
    """Tests for generate_temporary_password function."""

    def test_returns_string(self) -> None:
        password = generate_temporary_password()
        assert isinstance(password, str)

    def test_returns_16_characters(self) -> None:
        password = generate_temporary_password()
        assert len(password) == 16

    def test_generates_unique_passwords(self) -> None:
        passwords = {generate_temporary_password() for _ in range(100)}
        # All 100 should be unique (cryptographically secure)
        assert len(passwords) == 100

    def test_url_safe_characters(self) -> None:
        """Generated password should only contain URL-safe characters."""
        password = generate_temporary_password()
        # token_urlsafe produces base64url chars: A-Z, a-z, 0-9, -, _
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in allowed for c in password)


class TestResetPassword:
    """Tests for reset_password function."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock async session for testing."""
        session = AsyncMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def mock_user(self) -> User:
        """Create a mock user for testing."""
        user = User(
            id=42,
            username="testuser",
            email="test@example.com",
            hashed_password="old_hashed_password",
            full_name="Test User",
            is_active=True,
        )
        return user

    @pytest.mark.asyncio
    async def test_returns_plaintext_password(
        self, mock_session: AsyncMock, mock_user: User
    ) -> None:
        """reset_password should return a plaintext temporary password."""
        # Mock the user query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        result = await reset_password(user_id=42, session=mock_session)

        assert isinstance(result, str)
        assert len(result) == 16

    @pytest.mark.asyncio
    async def test_updates_user_hashed_password(
        self, mock_session: AsyncMock, mock_user: User
    ) -> None:
        """reset_password should update the user's hashed_password field."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        await reset_password(user_id=42, session=mock_session)

        # The hashed_password should have been changed from the original
        assert mock_user.hashed_password != "old_hashed_password"
        # It should be a bcrypt hash (starts with $2b$)
        assert mock_user.hashed_password.startswith("$2b$")

    @pytest.mark.asyncio
    async def test_invalidates_refresh_tokens(
        self, mock_session: AsyncMock, mock_user: User
    ) -> None:
        """reset_password should revoke all active refresh tokens."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        await reset_password(user_id=42, session=mock_session)

        # session.execute should be called:
        # 1. For the user SELECT query
        # 2. For the refresh token UPDATE query
        assert mock_session.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_raises_value_error_for_missing_user(
        self, mock_session: AsyncMock
    ) -> None:
        """reset_password should raise ValueError if user not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="User with id 99 not found"):
            await reset_password(user_id=99, session=mock_session)

    @pytest.mark.asyncio
    async def test_raises_runtime_error_on_hash_failure(
        self, mock_session: AsyncMock, mock_user: User
    ) -> None:
        """reset_password should raise RuntimeError if hashing fails."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        with patch(
            "alcoabase.services.password_reset._pwd_context"
        ) as mock_ctx:
            mock_ctx.hash.side_effect = Exception("bcrypt error")

            with pytest.raises(RuntimeError, match="internal error"):
                await reset_password(user_id=42, session=mock_session)

    @pytest.mark.asyncio
    async def test_flushes_session_after_password_update(
        self, mock_session: AsyncMock, mock_user: User
    ) -> None:
        """reset_password should flush the session to persist changes."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        await reset_password(user_id=42, session=mock_session)

        # flush should be called at least twice (after password update and after token revocation)
        assert mock_session.flush.call_count >= 2

    @pytest.mark.asyncio
    async def test_returned_password_verifies_against_hash(
        self, mock_session: AsyncMock, mock_user: User
    ) -> None:
        """The returned plaintext password should verify against the stored hash."""
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        plaintext = await reset_password(user_id=42, session=mock_session)

        # The plaintext password should verify against the new hash
        assert pwd_context.verify(plaintext, mock_user.hashed_password)


class TestAuditTrailRecording:
    """Tests for audit trail recording — password value NOT logged.

    Validates Requirement 9.4: Record reset in audit trail without logging password.
    """

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock async session for testing."""
        session = AsyncMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def mock_user(self) -> User:
        """Create a mock user for testing."""
        user = User(
            id=42,
            username="testuser",
            email="test@example.com",
            hashed_password="old_hashed_password",
            full_name="Test User",
            is_active=True,
        )
        return user

    @pytest.mark.asyncio
    async def test_password_value_not_in_log_messages(
        self, mock_session: AsyncMock, mock_user: User, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The temporary password plaintext must NOT appear in any log messages."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        with caplog.at_level(logging.DEBUG, logger="alcoabase.services.password_reset"):
            plaintext = await reset_password(user_id=42, session=mock_session)

        # Verify the password plaintext does not appear in any log record
        for record in caplog.records:
            assert plaintext not in record.getMessage(), (
                f"Password plaintext found in log message: {record.getMessage()}"
            )

    @pytest.mark.asyncio
    async def test_password_hash_not_in_log_messages(
        self, mock_session: AsyncMock, mock_user: User, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The bcrypt hash must NOT appear in any log messages."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        with caplog.at_level(logging.DEBUG, logger="alcoabase.services.password_reset"):
            await reset_password(user_id=42, session=mock_session)

        hashed = mock_user.hashed_password
        for record in caplog.records:
            assert hashed not in record.getMessage(), (
                f"Password hash found in log message: {record.getMessage()}"
            )

    @pytest.mark.asyncio
    async def test_audit_log_records_user_id(
        self, mock_session: AsyncMock, mock_user: User, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The audit log should record the user_id for traceability."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        with caplog.at_level(logging.INFO, logger="alcoabase.services.password_reset"):
            await reset_password(user_id=42, session=mock_session)

        # Verify an info-level log message references the user_id
        info_messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.INFO]
        assert any("42" in msg for msg in info_messages), (
            "Expected user_id=42 to appear in audit log messages"
        )

    @pytest.mark.asyncio
    async def test_audit_log_confirms_reset_completed(
        self, mock_session: AsyncMock, mock_user: User, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The audit log should confirm the password reset was completed."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        with caplog.at_level(logging.INFO, logger="alcoabase.services.password_reset"):
            await reset_password(user_id=42, session=mock_session)

        info_messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.INFO]
        assert any("reset" in msg.lower() and "completed" in msg.lower() for msg in info_messages), (
            "Expected a log message confirming password reset completion"
        )
