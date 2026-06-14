"""Unit tests for log_document_access function.

Tests cover:
- log_document_access creates record with correct fields
- action validation rejects invalid actions
- fire-and-forget error handling (rollback on commit failure)
- accepted action values: "download" and "content_preview"

References:
    - Requirements: 6.4
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.models.document_access_log import DocumentAccessLog
from alcoabase.services.audit_access_logger import log_document_access


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession for testing."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# log_document_access: basic record creation
# ---------------------------------------------------------------------------


class TestLogDocumentAccessCreatesRecord:
    """Tests that log_document_access creates DocumentAccessLog with correct fields."""

    @pytest.mark.asyncio
    async def test_creates_record_with_correct_user_id(
        self, mock_session: AsyncMock
    ) -> None:
        """log_document_access creates a record with the specified user_id."""
        await log_document_access(
            session=mock_session,
            user_id=42,
            document_uuid="2025-00001",
            major_version=1,
            minor_version=0,
            action="download",
        )

        mock_session.add.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, DocumentAccessLog)
        assert added_obj.user_id == 42

    @pytest.mark.asyncio
    async def test_creates_record_with_correct_document_uuid(
        self, mock_session: AsyncMock
    ) -> None:
        """log_document_access creates a record with the specified document_uuid."""
        await log_document_access(
            session=mock_session,
            user_id=1,
            document_uuid="2025-00042",
            major_version=1,
            minor_version=0,
            action="download",
        )

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.document_uuid == "2025-00042"

    @pytest.mark.asyncio
    async def test_creates_record_with_correct_version(
        self, mock_session: AsyncMock
    ) -> None:
        """log_document_access creates a record with the specified version."""
        await log_document_access(
            session=mock_session,
            user_id=1,
            document_uuid="2025-00001",
            major_version=3,
            minor_version=2,
            action="download",
        )

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.major_version == 3
        assert added_obj.minor_version == 2

    @pytest.mark.asyncio
    async def test_creates_record_with_download_action(
        self, mock_session: AsyncMock
    ) -> None:
        """log_document_access creates a record with action='download'."""
        await log_document_access(
            session=mock_session,
            user_id=1,
            document_uuid="2025-00001",
            major_version=1,
            minor_version=0,
            action="download",
        )

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.action == "download"

    @pytest.mark.asyncio
    async def test_creates_record_with_content_preview_action(
        self, mock_session: AsyncMock
    ) -> None:
        """log_document_access creates a record with action='content_preview'."""
        await log_document_access(
            session=mock_session,
            user_id=1,
            document_uuid="2025-00001",
            major_version=1,
            minor_version=0,
            action="content_preview",
        )

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.action == "content_preview"

    @pytest.mark.asyncio
    async def test_commits_immediately(
        self, mock_session: AsyncMock
    ) -> None:
        """log_document_access commits the session immediately (fire-and-forget)."""
        await log_document_access(
            session=mock_session,
            user_id=1,
            document_uuid="2025-00001",
            major_version=1,
            minor_version=0,
            action="download",
        )

        mock_session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# log_document_access: action validation
# ---------------------------------------------------------------------------


class TestLogDocumentAccessActionValidation:
    """Tests for action parameter validation."""

    @pytest.mark.asyncio
    async def test_rejects_invalid_action(
        self, mock_session: AsyncMock
    ) -> None:
        """log_document_access raises ValueError for invalid action."""
        with pytest.raises(ValueError, match="Invalid action 'view'"):
            await log_document_access(
                session=mock_session,
                user_id=1,
                document_uuid="2025-00001",
                major_version=1,
                minor_version=0,
                action="view",
            )

    @pytest.mark.asyncio
    async def test_rejects_empty_action(
        self, mock_session: AsyncMock
    ) -> None:
        """log_document_access raises ValueError for empty action string."""
        with pytest.raises(ValueError, match="Invalid action"):
            await log_document_access(
                session=mock_session,
                user_id=1,
                document_uuid="2025-00001",
                major_version=1,
                minor_version=0,
                action="",
            )

    @pytest.mark.asyncio
    async def test_does_not_add_record_on_invalid_action(
        self, mock_session: AsyncMock
    ) -> None:
        """log_document_access does not add a record when action is invalid."""
        with pytest.raises(ValueError):
            await log_document_access(
                session=mock_session,
                user_id=1,
                document_uuid="2025-00001",
                major_version=1,
                minor_version=0,
                action="invalid",
            )

        mock_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# log_document_access: error handling
# ---------------------------------------------------------------------------


class TestLogDocumentAccessErrorHandling:
    """Tests for error handling during commit."""

    @pytest.mark.asyncio
    async def test_rollback_on_commit_failure(
        self, mock_session: AsyncMock
    ) -> None:
        """log_document_access rolls back the session if commit fails."""
        mock_session.commit.side_effect = Exception("DB connection lost")

        # Should not raise — fire-and-forget pattern
        await log_document_access(
            session=mock_session,
            user_id=1,
            document_uuid="2025-00001",
            major_version=1,
            minor_version=0,
            action="download",
        )

        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_raise_on_commit_failure(
        self, mock_session: AsyncMock
    ) -> None:
        """log_document_access swallows exceptions from commit (fire-and-forget)."""
        mock_session.commit.side_effect = Exception("DB connection lost")

        # This should NOT raise
        await log_document_access(
            session=mock_session,
            user_id=1,
            document_uuid="2025-00001",
            major_version=1,
            minor_version=0,
            action="content_preview",
        )
