"""Unit tests for AuditAccessLogger service.

Tests cover:
- log_access creates record with correct user_id, company_id, action, timestamp
- log_access with filters_applied as dict and as None
- log_access with event_count for export actions
- No update/delete methods exist on the service (append-only enforcement)

References:
    - Requirements: 11.1, 11.2, 11.3
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.models.audit_access_log import AuditAccessLog
from alcoabase.services.audit_access_logger import AuditAccessLogger


@pytest.fixture
def logger() -> AuditAccessLogger:
    """Create an AuditAccessLogger instance."""
    return AuditAccessLogger()


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession for testing."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# log_access: basic record creation
# ---------------------------------------------------------------------------


class TestLogAccessCreatesRecord:
    """Tests that log_access creates AuditAccessLog with correct fields."""

    @pytest.mark.asyncio
    async def test_creates_record_with_correct_user_id(
        self, logger: AuditAccessLogger, mock_session: AsyncMock
    ) -> None:
        """log_access creates a record with the specified user_id."""
        await logger.log_access(
            session=mock_session,
            user_id=42,
            company_id=1,
            action="view",
        )

        mock_session.add.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, AuditAccessLog)
        assert added_obj.user_id == 42

    @pytest.mark.asyncio
    async def test_creates_record_with_correct_company_id(
        self, logger: AuditAccessLogger, mock_session: AsyncMock
    ) -> None:
        """log_access creates a record with the specified company_id."""
        await logger.log_access(
            session=mock_session,
            user_id=1,
            company_id=7,
            action="view",
        )

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.company_id == 7

    @pytest.mark.asyncio
    async def test_creates_record_with_correct_action(
        self, logger: AuditAccessLogger, mock_session: AsyncMock
    ) -> None:
        """log_access creates a record with the specified action."""
        await logger.log_access(
            session=mock_session,
            user_id=1,
            company_id=1,
            action="export",
        )

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.action == "export"

    @pytest.mark.asyncio
    async def test_commits_immediately(
        self, logger: AuditAccessLogger, mock_session: AsyncMock
    ) -> None:
        """log_access commits the session immediately (fire-and-forget)."""
        await logger.log_access(
            session=mock_session,
            user_id=1,
            company_id=1,
            action="view",
        )

        mock_session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# log_access: filters_applied handling
# ---------------------------------------------------------------------------


class TestLogAccessFiltersApplied:
    """Tests for filters_applied parameter handling."""

    @pytest.mark.asyncio
    async def test_filters_applied_as_dict(
        self, logger: AuditAccessLogger, mock_session: AsyncMock
    ) -> None:
        """log_access stores filters_applied when provided as a dict."""
        filters = {"user_id": 5, "record_type": "documents", "date_start": "2025-01-01"}

        await logger.log_access(
            session=mock_session,
            user_id=1,
            company_id=1,
            action="view",
            filters_applied=filters,
        )

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.filters_applied == filters

    @pytest.mark.asyncio
    async def test_filters_applied_as_none(
        self, logger: AuditAccessLogger, mock_session: AsyncMock
    ) -> None:
        """log_access stores None when no filters are applied."""
        await logger.log_access(
            session=mock_session,
            user_id=1,
            company_id=1,
            action="view",
            filters_applied=None,
        )

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.filters_applied is None

    @pytest.mark.asyncio
    async def test_filters_applied_defaults_to_none(
        self, logger: AuditAccessLogger, mock_session: AsyncMock
    ) -> None:
        """filters_applied defaults to None when not provided."""
        await logger.log_access(
            session=mock_session,
            user_id=1,
            company_id=1,
            action="view",
        )

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.filters_applied is None


# ---------------------------------------------------------------------------
# log_access: event_count for export actions
# ---------------------------------------------------------------------------


class TestLogAccessEventCount:
    """Tests for event_count parameter handling."""

    @pytest.mark.asyncio
    async def test_event_count_for_export_action(
        self, logger: AuditAccessLogger, mock_session: AsyncMock
    ) -> None:
        """log_access stores event_count for export actions."""
        await logger.log_access(
            session=mock_session,
            user_id=1,
            company_id=1,
            action="export",
            event_count=150,
        )

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.event_count == 150

    @pytest.mark.asyncio
    async def test_event_count_none_for_view_action(
        self, logger: AuditAccessLogger, mock_session: AsyncMock
    ) -> None:
        """log_access stores None event_count for view actions."""
        await logger.log_access(
            session=mock_session,
            user_id=1,
            company_id=1,
            action="view",
            event_count=None,
        )

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.event_count is None

    @pytest.mark.asyncio
    async def test_event_count_defaults_to_none(
        self, logger: AuditAccessLogger, mock_session: AsyncMock
    ) -> None:
        """event_count defaults to None when not provided."""
        await logger.log_access(
            session=mock_session,
            user_id=1,
            company_id=1,
            action="view",
        )

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.event_count is None


# ---------------------------------------------------------------------------
# log_access: error handling
# ---------------------------------------------------------------------------


class TestLogAccessErrorHandling:
    """Tests for error handling during commit."""

    @pytest.mark.asyncio
    async def test_rollback_on_commit_failure(
        self, logger: AuditAccessLogger, mock_session: AsyncMock
    ) -> None:
        """log_access rolls back the session if commit fails."""
        mock_session.commit.side_effect = Exception("DB connection lost")

        # Should not raise — fire-and-forget pattern
        await logger.log_access(
            session=mock_session,
            user_id=1,
            company_id=1,
            action="view",
        )

        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# Immutability: no update/delete methods
# ---------------------------------------------------------------------------


class TestImmutabilityEnforcement:
    """Tests that AuditAccessLogger has no update or delete methods."""

    def test_no_update_method(self, logger: AuditAccessLogger) -> None:
        """AuditAccessLogger does not expose an update method."""
        assert not hasattr(logger, "update")
        assert not hasattr(logger, "update_access")
        assert not hasattr(logger, "update_log")

    def test_no_delete_method(self, logger: AuditAccessLogger) -> None:
        """AuditAccessLogger does not expose a delete method."""
        assert not hasattr(logger, "delete")
        assert not hasattr(logger, "delete_access")
        assert not hasattr(logger, "delete_log")

    def test_no_edit_method(self, logger: AuditAccessLogger) -> None:
        """AuditAccessLogger does not expose an edit method."""
        assert not hasattr(logger, "edit")
        assert not hasattr(logger, "modify")

    def test_only_log_access_public_method(
        self, logger: AuditAccessLogger
    ) -> None:
        """AuditAccessLogger exposes only log_access as a public method."""
        public_methods = [
            m for m in dir(logger)
            if not m.startswith("_") and callable(getattr(logger, m))
        ]
        assert public_methods == ["log_access"]
