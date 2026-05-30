"""HITL Checkpoint Service for AI Risk & Compliance Framework.

Manages the lifecycle of Human-in-the-Loop checkpoints: listing with
filters and pagination, reviewing (approve/reject) with optimistic
locking, and expiring stale checkpoints.

State machine: pending → approved | rejected | expired
No other transitions are permitted.

References:
    - Design: .kiro/specs/Step_8-1_ai-risk-compliance-framework/design.md
    - Requirements: 5.1–5.11, 8.9
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.risk_framework import (
    CheckpointStatus,
    HITLCheckpoint,
)
from alcoabase.models.user import Role, User, UserRole
from alcoabase.schemas.risk_framework import (
    CheckpointFilters,
    HITLCheckpointResponse,
    PaginatedResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------


class CheckpointNotFoundError(Exception):
    """Raised when a checkpoint is not found for the given company."""

    def __init__(self, checkpoint_id: UUID, company_id: int) -> None:
        self.checkpoint_id = checkpoint_id
        self.company_id = company_id
        super().__init__(
            f"Checkpoint '{checkpoint_id}' not found for company {company_id}."
        )


class CheckpointNotPendingError(Exception):
    """Raised when attempting to review a checkpoint that is not pending.

    HTTP 409 — the checkpoint has already been reviewed or expired.
    """

    def __init__(self, checkpoint_id: UUID, current_status: str) -> None:
        self.checkpoint_id = checkpoint_id
        self.current_status = current_status
        super().__init__(
            f"Checkpoint is already in state '{current_status}'. "
            f"Only pending checkpoints can be reviewed."
        )


class ConcurrentReviewError(Exception):
    """Raised when a concurrent review wins the optimistic lock race.

    HTTP 409 — another user already reviewed this checkpoint.
    """

    def __init__(self, checkpoint_id: UUID) -> None:
        self.checkpoint_id = checkpoint_id
        super().__init__(
            "Checkpoint was already reviewed by another user."
        )


class InsufficientReviewPermissionError(Exception):
    """Raised when the user lacks system_admin or doc_admin role.

    HTTP 403 — only qualified reviewers can approve/reject checkpoints.
    """

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        super().__init__(
            "Insufficient permissions. Requires system_admin or doc_admin role."
        )


class RejectionRequiresCommentsError(Exception):
    """Raised when a rejection is submitted without reviewer_comments.

    HTTP 422 — reviewer comments are required for rejections.
    """

    def __init__(self) -> None:
        super().__init__(
            "reviewer_comments is required when action is 'reject'."
        )


# ---------------------------------------------------------------------------
# HITLCheckpointService
# ---------------------------------------------------------------------------


class HITLCheckpointService:
    """Manages HITL checkpoint lifecycle: listing, review, and expiration.

    All methods accept an AsyncSession for database operations, following
    the project's dependency injection pattern.
    """

    async def list_checkpoints(
        self,
        session: AsyncSession,
        company_id: int,
        filters: CheckpointFilters,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedResult[HITLCheckpointResponse]:
        """Return paginated list of HITL checkpoints for a company.

        Supports filtering by task_type_id, status, assigned_reviewer,
        and date range. Results are sorted by expires_at ascending
        (nearest expiry first).

        Args:
            session: Active async database session.
            company_id: Company ID for tenant scoping.
            filters: Filter criteria for the query.
            limit: Maximum items per page (1-100).
            offset: Number of items to skip.

        Returns:
            PaginatedResult containing HITLCheckpointResponse items.
        """
        # Clamp pagination parameters
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        # Build filter conditions
        conditions = [HITLCheckpoint.company_id == company_id]

        if filters.task_type_id is not None:
            conditions.append(HITLCheckpoint.task_type_id == filters.task_type_id)

        if filters.status is not None:
            conditions.append(HITLCheckpoint.status == filters.status)

        if filters.assigned_reviewer is not None:
            conditions.append(
                HITLCheckpoint.reviewer_user_id == int(str(filters.assigned_reviewer))
            )

        if filters.start_date is not None:
            conditions.append(HITLCheckpoint.created_at >= filters.start_date)

        if filters.end_date is not None:
            conditions.append(HITLCheckpoint.created_at <= filters.end_date)

        where_clause = and_(*conditions)

        # Count total matching records
        count_stmt = (
            select(func.count())
            .select_from(HITLCheckpoint)
            .where(where_clause)
        )
        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one()

        # Fetch paginated checkpoints sorted by expires_at ascending
        query = (
            select(HITLCheckpoint)
            .where(where_clause)
            .order_by(HITLCheckpoint.expires_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(query)
        checkpoints = result.scalars().all()

        items = [
            self._to_response(checkpoint) for checkpoint in checkpoints
        ]

        return PaginatedResult[HITLCheckpointResponse](
            items=items, total=total, limit=limit, offset=offset
        )

    async def review_checkpoint(
        self,
        session: AsyncSession,
        checkpoint_id: UUID,
        company_id: int,
        user_id: int,
        action: str,
        comments: str | None,
        reviewed_sections: list[str] | None,
    ) -> HITLCheckpointResponse:
        """Review a HITL checkpoint (approve or reject).

        Business rules:
        - Only users with system_admin or doc_admin role can review.
        - Checkpoint must be in "pending" status.
        - Rejection requires non-empty reviewer_comments.
        - Uses optimistic locking: UPDATE WHERE status='pending' to handle
          concurrent reviews. If 0 rows affected, another user already reviewed.

        Args:
            session: Active async database session.
            checkpoint_id: UUID of the checkpoint to review.
            company_id: Company ID for tenant scoping.
            user_id: ID of the reviewing user.
            action: Review action — "approve" or "reject".
            comments: Reviewer's comments (required for rejection).
            reviewed_sections: Optional list of section identifiers reviewed.

        Returns:
            HITLCheckpointResponse for the updated checkpoint.

        Raises:
            CheckpointNotFoundError: If checkpoint not found for company.
            InsufficientReviewPermissionError: If user lacks required role.
            RejectionRequiresCommentsError: If rejecting without comments.
            CheckpointNotPendingError: If checkpoint is not in pending state.
            ConcurrentReviewError: If another user already reviewed.
        """
        # 1. Validate reviewer has system_admin or doc_admin role
        has_permission = await self._user_has_review_permission(
            session, user_id, company_id
        )
        if not has_permission:
            raise InsufficientReviewPermissionError(user_id)

        # 2. Validate rejection requires comments
        if action == "reject":
            if not comments or not comments.strip():
                raise RejectionRequiresCommentsError()

        # 3. Fetch checkpoint to verify it exists and belongs to company
        stmt = select(HITLCheckpoint).where(
            and_(
                HITLCheckpoint.id == checkpoint_id,
                HITLCheckpoint.company_id == company_id,
            )
        )
        result = await session.execute(stmt)
        checkpoint = result.scalar_one_or_none()

        if checkpoint is None:
            raise CheckpointNotFoundError(checkpoint_id, company_id)

        # 4. Check current status — if not pending, raise 409
        if checkpoint.status != CheckpointStatus.PENDING.value:
            raise CheckpointNotPendingError(checkpoint_id, checkpoint.status)

        # 5. Optimistic locking: UPDATE WHERE status='pending'
        new_status = (
            CheckpointStatus.APPROVED.value
            if action == "approve"
            else CheckpointStatus.REJECTED.value
        )
        now = datetime.now(timezone.utc)

        update_stmt = (
            update(HITLCheckpoint)
            .where(
                and_(
                    HITLCheckpoint.id == checkpoint_id,
                    HITLCheckpoint.status == CheckpointStatus.PENDING.value,
                )
            )
            .values(
                status=new_status,
                reviewer_user_id=user_id,
                reviewer_comments=comments,
                reviewed_sections=reviewed_sections,
                reviewed_at=now,
            )
        )
        update_result = await session.execute(update_stmt)

        # If 0 rows affected, another user already reviewed (race condition)
        if update_result.rowcount == 0:
            raise ConcurrentReviewError(checkpoint_id)

        # 6. Refresh the checkpoint to get updated state
        await session.refresh(checkpoint)

        logger.info(
            "Checkpoint %s %s by user %d for company %d",
            checkpoint_id,
            new_status,
            user_id,
            company_id,
        )

        return self._to_response(checkpoint)

    async def expire_stale_checkpoints(
        self,
        session: AsyncSession,
    ) -> int:
        """Expire all pending checkpoints whose expires_at has passed.

        Finds all checkpoints where status='pending' AND expires_at < now,
        then sets their status to 'expired'. This operation is idempotent —
        running it multiple times has no additional effect.

        Args:
            session: Active async database session.

        Returns:
            Count of checkpoints that were expired in this run.
        """
        now = datetime.now(timezone.utc)

        update_stmt = (
            update(HITLCheckpoint)
            .where(
                and_(
                    HITLCheckpoint.status == CheckpointStatus.PENDING.value,
                    HITLCheckpoint.expires_at < now,
                )
            )
            .values(status=CheckpointStatus.EXPIRED.value)
        )
        result = await session.execute(update_stmt)
        expired_count = result.rowcount

        if expired_count > 0:
            logger.info(
                "Expired %d stale HITL checkpoints.", expired_count
            )

        return expired_count

    # ------------------------------------------------------------------
    # Private helper methods
    # ------------------------------------------------------------------

    async def _user_has_review_permission(
        self,
        session: AsyncSession,
        user_id: int,
        company_id: int,
    ) -> bool:
        """Check if a user has system_admin or doc_admin role.

        Checks for roles scoped to the given company or global roles
        (company_id IS NULL).

        Args:
            session: Active async database session.
            user_id: The user ID to check.
            company_id: The company ID for role scoping.

        Returns:
            True if the user has system_admin or doc_admin role.
        """
        stmt = (
            select(func.count())
            .select_from(User)
            .join(UserRole, User.id == UserRole.c.user_id)
            .join(Role, Role.id == UserRole.c.role_id)
            .where(
                and_(
                    User.id == user_id,
                    User.is_active.is_(True),
                    Role.name.in_(["system_admin", "doc_admin"]),
                    (Role.company_id == company_id) | (Role.company_id.is_(None)),
                )
            )
        )
        result = await session.execute(stmt)
        count = result.scalar_one()
        return count > 0

    def _to_response(self, checkpoint: HITLCheckpoint) -> HITLCheckpointResponse:
        """Convert a HITLCheckpoint model to its response schema.

        Args:
            checkpoint: The HITLCheckpoint ORM model instance.

        Returns:
            HITLCheckpointResponse Pydantic model.
        """
        return HITLCheckpointResponse(
            id=checkpoint.id,
            company_id=checkpoint.company_id,
            operation_id=checkpoint.operation_id,
            task_type_id=checkpoint.task_type_id,
            ai_output_reference=checkpoint.ai_output_reference,
            status=checkpoint.status,
            assigned_reviewer_role=checkpoint.assigned_reviewer_role,
            reviewer_user_id=checkpoint.reviewer_user_id,
            reviewer_comments=checkpoint.reviewer_comments,
            reviewed_sections=checkpoint.reviewed_sections,
            created_at=checkpoint.created_at,
            expires_at=checkpoint.expires_at,
            reviewed_at=checkpoint.reviewed_at,
        )
