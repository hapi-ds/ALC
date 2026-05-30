"""Unit tests for HITLCheckpointService.

Tests the HITL checkpoint lifecycle: listing with filters, reviewing
(approve/reject) with optimistic locking, and expiring stale checkpoints.

References:
    - Design: .kiro/specs/Step_8-1_ai-risk-compliance-framework/design.md
    - Requirements: 5.1–5.11, 8.9
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.risk_framework import CheckpointStatus, HITLCheckpoint
from alcoabase.schemas.risk_framework import CheckpointFilters
from alcoabase.services.hitl_checkpoint_service import (
    CheckpointNotFoundError,
    CheckpointNotPendingError,
    ConcurrentReviewError,
    HITLCheckpointService,
    InsufficientReviewPermissionError,
    RejectionRequiresCommentsError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> HITLCheckpointService:
    """Create a HITLCheckpointService instance."""
    return HITLCheckpointService()


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def sample_checkpoint() -> HITLCheckpoint:
    """Create a sample pending HITL checkpoint."""
    now = datetime.now(timezone.utc)
    return HITLCheckpoint(
        id=uuid.uuid4(),
        company_id=1,
        operation_id="op-123",
        task_type_id="document_generation",
        ai_output_reference="s3://bucket/output/123.json",
        status=CheckpointStatus.PENDING.value,
        assigned_reviewer_role="system_admin,doc_admin",
        reviewer_user_id=None,
        reviewer_comments=None,
        reviewed_sections=None,
        created_at=now,
        expires_at=now + timedelta(hours=72),
        reviewed_at=None,
    )


# ---------------------------------------------------------------------------
# Tests: list_checkpoints
# ---------------------------------------------------------------------------


class TestListCheckpoints:
    """Tests for HITLCheckpointService.list_checkpoints."""

    @pytest.mark.asyncio
    async def test_list_returns_paginated_result(
        self, service: HITLCheckpointService, mock_session: AsyncMock, sample_checkpoint: HITLCheckpoint
    ) -> None:
        """list_checkpoints returns a PaginatedResult with correct structure."""
        # Mock count query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        # Mock data query
        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = [sample_checkpoint]

        mock_session.execute.side_effect = [count_result, data_result]

        filters = CheckpointFilters()
        result = await service.list_checkpoints(
            session=mock_session, company_id=1, filters=filters, limit=20, offset=0
        )

        assert result.total == 1
        assert result.limit == 20
        assert result.offset == 0
        assert len(result.items) == 1
        assert result.items[0].id == sample_checkpoint.id
        assert result.items[0].status == "pending"

    @pytest.mark.asyncio
    async def test_list_clamps_pagination_params(
        self, service: HITLCheckpointService, mock_session: AsyncMock
    ) -> None:
        """list_checkpoints clamps limit to [1, 100] and offset to >= 0."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [count_result, data_result]

        filters = CheckpointFilters()
        result = await service.list_checkpoints(
            session=mock_session, company_id=1, filters=filters, limit=200, offset=-5
        )

        assert result.limit == 100
        assert result.offset == 0

    @pytest.mark.asyncio
    async def test_list_empty_result(
        self, service: HITLCheckpointService, mock_session: AsyncMock
    ) -> None:
        """list_checkpoints returns empty result when no checkpoints exist."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [count_result, data_result]

        filters = CheckpointFilters()
        result = await service.list_checkpoints(
            session=mock_session, company_id=1, filters=filters
        )

        assert result.total == 0
        assert result.items == []


# ---------------------------------------------------------------------------
# Tests: review_checkpoint
# ---------------------------------------------------------------------------


class TestReviewCheckpoint:
    """Tests for HITLCheckpointService.review_checkpoint."""

    @pytest.mark.asyncio
    async def test_approve_checkpoint_success(
        self, service: HITLCheckpointService, mock_session: AsyncMock, sample_checkpoint: HITLCheckpoint
    ) -> None:
        """Approving a pending checkpoint succeeds with proper role."""
        # Mock role check (user has permission)
        role_result = MagicMock()
        role_result.scalar_one.return_value = 1
        # Mock checkpoint fetch
        checkpoint_result = MagicMock()
        checkpoint_result.scalar_one_or_none.return_value = sample_checkpoint
        # Mock update (1 row affected)
        update_result = MagicMock()
        update_result.rowcount = 1

        mock_session.execute.side_effect = [role_result, checkpoint_result, update_result]

        # After refresh, checkpoint should have updated status
        async def mock_refresh(obj):
            obj.status = CheckpointStatus.APPROVED.value
            obj.reviewer_user_id = 1
            obj.reviewer_comments = "Looks good"
            obj.reviewed_at = datetime.now(timezone.utc)

        mock_session.refresh.side_effect = mock_refresh

        result = await service.review_checkpoint(
            session=mock_session,
            checkpoint_id=sample_checkpoint.id,
            company_id=1,
            user_id=1,
            action="approve",
            comments="Looks good",
            reviewed_sections=["section_1"],
        )

        assert result.status == "approved"
        assert result.reviewer_user_id == 1

    @pytest.mark.asyncio
    async def test_reject_checkpoint_success(
        self, service: HITLCheckpointService, mock_session: AsyncMock, sample_checkpoint: HITLCheckpoint
    ) -> None:
        """Rejecting a pending checkpoint succeeds with comments."""
        role_result = MagicMock()
        role_result.scalar_one.return_value = 1
        checkpoint_result = MagicMock()
        checkpoint_result.scalar_one_or_none.return_value = sample_checkpoint
        update_result = MagicMock()
        update_result.rowcount = 1

        mock_session.execute.side_effect = [role_result, checkpoint_result, update_result]

        async def mock_refresh(obj):
            obj.status = CheckpointStatus.REJECTED.value
            obj.reviewer_user_id = 1
            obj.reviewer_comments = "Needs revision"
            obj.reviewed_at = datetime.now(timezone.utc)

        mock_session.refresh.side_effect = mock_refresh

        result = await service.review_checkpoint(
            session=mock_session,
            checkpoint_id=sample_checkpoint.id,
            company_id=1,
            user_id=1,
            action="reject",
            comments="Needs revision",
            reviewed_sections=None,
        )

        assert result.status == "rejected"

    @pytest.mark.asyncio
    async def test_reject_without_comments_raises_error(
        self, service: HITLCheckpointService, mock_session: AsyncMock
    ) -> None:
        """Rejecting without comments raises RejectionRequiresCommentsError."""
        # Mock role check (user has permission)
        role_result = MagicMock()
        role_result.scalar_one.return_value = 1
        mock_session.execute.side_effect = [role_result]

        with pytest.raises(RejectionRequiresCommentsError):
            await service.review_checkpoint(
                session=mock_session,
                checkpoint_id=uuid.uuid4(),
                company_id=1,
                user_id=1,
                action="reject",
                comments="",
                reviewed_sections=None,
            )

    @pytest.mark.asyncio
    async def test_reject_with_none_comments_raises_error(
        self, service: HITLCheckpointService, mock_session: AsyncMock
    ) -> None:
        """Rejecting with None comments raises RejectionRequiresCommentsError."""
        role_result = MagicMock()
        role_result.scalar_one.return_value = 1
        mock_session.execute.side_effect = [role_result]

        with pytest.raises(RejectionRequiresCommentsError):
            await service.review_checkpoint(
                session=mock_session,
                checkpoint_id=uuid.uuid4(),
                company_id=1,
                user_id=1,
                action="reject",
                comments=None,
                reviewed_sections=None,
            )

    @pytest.mark.asyncio
    async def test_insufficient_permission_raises_error(
        self, service: HITLCheckpointService, mock_session: AsyncMock
    ) -> None:
        """User without system_admin/doc_admin role gets 403."""
        role_result = MagicMock()
        role_result.scalar_one.return_value = 0  # No matching roles
        mock_session.execute.side_effect = [role_result]

        with pytest.raises(InsufficientReviewPermissionError):
            await service.review_checkpoint(
                session=mock_session,
                checkpoint_id=uuid.uuid4(),
                company_id=1,
                user_id=99,
                action="approve",
                comments="Approved",
                reviewed_sections=None,
            )

    @pytest.mark.asyncio
    async def test_checkpoint_not_found_raises_error(
        self, service: HITLCheckpointService, mock_session: AsyncMock
    ) -> None:
        """Non-existent checkpoint raises CheckpointNotFoundError."""
        role_result = MagicMock()
        role_result.scalar_one.return_value = 1
        checkpoint_result = MagicMock()
        checkpoint_result.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [role_result, checkpoint_result]

        checkpoint_id = uuid.uuid4()
        with pytest.raises(CheckpointNotFoundError) as exc_info:
            await service.review_checkpoint(
                session=mock_session,
                checkpoint_id=checkpoint_id,
                company_id=1,
                user_id=1,
                action="approve",
                comments="OK",
                reviewed_sections=None,
            )
        assert exc_info.value.checkpoint_id == checkpoint_id

    @pytest.mark.asyncio
    async def test_checkpoint_not_pending_raises_error(
        self, service: HITLCheckpointService, mock_session: AsyncMock, sample_checkpoint: HITLCheckpoint
    ) -> None:
        """Reviewing an already-approved checkpoint raises CheckpointNotPendingError."""
        sample_checkpoint.status = CheckpointStatus.APPROVED.value

        role_result = MagicMock()
        role_result.scalar_one.return_value = 1
        checkpoint_result = MagicMock()
        checkpoint_result.scalar_one_or_none.return_value = sample_checkpoint

        mock_session.execute.side_effect = [role_result, checkpoint_result]

        with pytest.raises(CheckpointNotPendingError) as exc_info:
            await service.review_checkpoint(
                session=mock_session,
                checkpoint_id=sample_checkpoint.id,
                company_id=1,
                user_id=1,
                action="approve",
                comments="OK",
                reviewed_sections=None,
            )
        assert exc_info.value.current_status == "approved"

    @pytest.mark.asyncio
    async def test_concurrent_review_raises_error(
        self, service: HITLCheckpointService, mock_session: AsyncMock, sample_checkpoint: HITLCheckpoint
    ) -> None:
        """Concurrent review (0 rows affected) raises ConcurrentReviewError."""
        role_result = MagicMock()
        role_result.scalar_one.return_value = 1
        checkpoint_result = MagicMock()
        checkpoint_result.scalar_one_or_none.return_value = sample_checkpoint
        # Optimistic lock fails: 0 rows affected
        update_result = MagicMock()
        update_result.rowcount = 0

        mock_session.execute.side_effect = [role_result, checkpoint_result, update_result]

        with pytest.raises(ConcurrentReviewError):
            await service.review_checkpoint(
                session=mock_session,
                checkpoint_id=sample_checkpoint.id,
                company_id=1,
                user_id=1,
                action="approve",
                comments="OK",
                reviewed_sections=None,
            )

    @pytest.mark.asyncio
    async def test_expired_checkpoint_cannot_be_reviewed(
        self, service: HITLCheckpointService, mock_session: AsyncMock, sample_checkpoint: HITLCheckpoint
    ) -> None:
        """Expired checkpoint raises CheckpointNotPendingError."""
        sample_checkpoint.status = CheckpointStatus.EXPIRED.value

        role_result = MagicMock()
        role_result.scalar_one.return_value = 1
        checkpoint_result = MagicMock()
        checkpoint_result.scalar_one_or_none.return_value = sample_checkpoint

        mock_session.execute.side_effect = [role_result, checkpoint_result]

        with pytest.raises(CheckpointNotPendingError) as exc_info:
            await service.review_checkpoint(
                session=mock_session,
                checkpoint_id=sample_checkpoint.id,
                company_id=1,
                user_id=1,
                action="approve",
                comments="OK",
                reviewed_sections=None,
            )
        assert exc_info.value.current_status == "expired"


# ---------------------------------------------------------------------------
# Tests: expire_stale_checkpoints
# ---------------------------------------------------------------------------


class TestExpireStaleCheckpoints:
    """Tests for HITLCheckpointService.expire_stale_checkpoints."""

    @pytest.mark.asyncio
    async def test_expire_returns_count(
        self, service: HITLCheckpointService, mock_session: AsyncMock
    ) -> None:
        """expire_stale_checkpoints returns the count of expired checkpoints."""
        update_result = MagicMock()
        update_result.rowcount = 3
        mock_session.execute.return_value = update_result

        count = await service.expire_stale_checkpoints(session=mock_session)
        assert count == 3

    @pytest.mark.asyncio
    async def test_expire_returns_zero_when_none_stale(
        self, service: HITLCheckpointService, mock_session: AsyncMock
    ) -> None:
        """expire_stale_checkpoints returns 0 when no checkpoints are stale."""
        update_result = MagicMock()
        update_result.rowcount = 0
        mock_session.execute.return_value = update_result

        count = await service.expire_stale_checkpoints(session=mock_session)
        assert count == 0

    @pytest.mark.asyncio
    async def test_expire_is_idempotent(
        self, service: HITLCheckpointService, mock_session: AsyncMock
    ) -> None:
        """Running expire_stale_checkpoints multiple times is idempotent."""
        # First run: 2 expired
        first_result = MagicMock()
        first_result.rowcount = 2
        # Second run: 0 expired (already done)
        second_result = MagicMock()
        second_result.rowcount = 0

        mock_session.execute.side_effect = [first_result, second_result]

        count1 = await service.expire_stale_checkpoints(session=mock_session)
        count2 = await service.expire_stale_checkpoints(session=mock_session)

        assert count1 == 2
        assert count2 == 0
