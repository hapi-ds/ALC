"""Review Pipeline Service for multi-agent document review orchestration.

Orchestrates the full review lifecycle from document submission through
parallel agent reviews to Master Auditor summarization. Provides session
management, action item CRUD, and approval/rejection workflows.

References:
    - Requirement 1: Review Pipeline Orchestration
    - Requirement 1.1: Document submission with optional audit_profile_id
    - Requirement 1.2: Parallel agent dispatch via Celery
    - Requirement 1.3: Session status lifecycle (Pending → InProgress → Completed)
    - Requirement 1.8: POST /api/reviews endpoint (HTTP 202)
    - Requirement 1.9: GET /api/reviews/{session_id} endpoint
    - Requirement 1.10: Company-scoped operations
    - Requirement 10.1–10.8: Review Pipeline API Endpoints
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.document import Document
from alcoabase.models.review import ActionItem, AgentReview, ReviewSession
from alcoabase.services.agent_registry import AgentRegistryService
from alcoabase.services.audit_profile_service import AuditProfileService
from alcoabase.services.inference_client import InferenceClient
from alcoabase.services.risk_controlled import risk_controlled
from alcoabase.services.storage_service import StorageService

logger = logging.getLogger(__name__)

# Valid status transitions for review sessions
_VALID_SESSION_TRANSITIONS: dict[str, set[str]] = {
    "Pending": {"InProgress"},
    "InProgress": {"Completed", "Failed"},
    "Completed": {"Approved", "Rejected"},
}

# Valid status transitions for action items
_VALID_ACTION_ITEM_TRANSITIONS: dict[str, set[str]] = {
    "Open": {"InProgress", "Resolved", "Dismissed"},
    "InProgress": {"Resolved", "Dismissed", "Open"},
}

# Active session statuses that block new submissions
_ACTIVE_STATUSES = {"Pending", "InProgress"}


class ReviewPipelineService:
    """Orchestrates multi-agent document review pipelines.

    Manages the full lifecycle of review sessions including submission,
    parallel agent dispatch, session queries, approval/rejection, and
    action item tracking.

    Attributes:
        _session_factory: SQLAlchemy async session factory for DB access.
        _agent_registry: Service for agent definition lookups.
        _storage_service: MinIO storage service for document retrieval.
        _inference_client: vLLM inference client for AI operations.
        _audit_profile_service: Service for audit profile resolution.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        agent_registry: AgentRegistryService,
        storage_service: StorageService,
        inference_client: InferenceClient,
    ) -> None:
        """Initialize the ReviewPipelineService.

        Args:
            session_factory: SQLAlchemy async session factory for DB access.
            agent_registry: Service for agent definition lookups.
            storage_service: MinIO storage service for document retrieval.
            inference_client: vLLM inference client for AI operations.
        """
        self._session_factory = session_factory
        self._agent_registry = agent_registry
        self._storage_service = storage_service
        self._inference_client = inference_client
        self._audit_profile_service = AuditProfileService(session_factory)

    # -----------------------------------------------------------------------
    # Pipeline Operations
    # -----------------------------------------------------------------------

    @risk_controlled(task_type_id="multi_agent_audit")
    async def submit_review(
        self,
        document_id: int,
        document_version_id: int,
        audit_profile_id: int | None,
        company_id: int,
        user_id: int,
    ) -> ReviewSession:
        """Submit a document for multi-agent review.

        Validates the document exists, checks for active sessions, resolves
        the audit profile, creates a ReviewSession and AgentReview records,
        and dispatches Celery tasks for parallel agent execution.

        Args:
            document_id: ID of the document to review.
            document_version_id: ID of the specific document version.
            audit_profile_id: Optional audit profile override. If None,
                uses the company's default profile.
            company_id: Company scope for multi-tenancy.
            user_id: ID of the user submitting the review.

        Returns:
            The created ReviewSession with status "Pending".

        Raises:
            ValueError: If document not found, no audit profile configured,
                or other validation failures.
            ConflictError: If an active review session already exists for
                the document.
        """
        async with self._session_factory() as session:
            # 1. Validate document exists and belongs to company
            doc_result = await session.execute(
                select(Document).where(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
            document = doc_result.scalar_one_or_none()
            if document is None:
                raise ValueError(f"Document {document_id} not found")

            # 2. Check no active session exists for this document (Requirement 10.8)
            active_result = await session.execute(
                select(ReviewSession).where(
                    ReviewSession.document_id == document_id,
                    ReviewSession.company_id == company_id,
                    ReviewSession.status.in_(_ACTIVE_STATUSES),
                )
            )
            existing_active = active_result.scalar_one_or_none()
            if existing_active is not None:
                raise ConflictError(
                    "Document already has an active review session"
                )

            # 3. Resolve audit profile (Requirement 1.1)
            if audit_profile_id is not None:
                profile = await self._audit_profile_service.get_profile(
                    audit_profile_id, company_id
                )
                if profile is None:
                    raise ValueError(
                        f"Audit profile {audit_profile_id} not found"
                    )
            else:
                profile = await self._audit_profile_service.get_default_profile(
                    company_id
                )
                if profile is None:
                    raise ValueError(
                        "No default audit profile configured for this company"
                    )

            # 4. Create ReviewSession with status "Pending" (Requirement 1.3)
            review_session = ReviewSession(
                company_id=company_id,
                document_id=document_id,
                document_version_id=document_version_id,
                audit_profile_id=profile.id,
                status="Pending",
                submitted_by=user_id,
            )
            session.add(review_session)
            await session.flush()

            # 5. Create AgentReview records for each assigned agent (Requirement 1.2)
            agent_reviews: list[AgentReview] = []
            for agent_id in profile.assigned_agent_ids:
                agent_review = AgentReview(
                    session_id=review_session.id,
                    agent_definition_id=agent_id,
                    status="Pending",
                )
                session.add(agent_review)
                agent_reviews.append(agent_review)

            await session.flush()

            # Refresh to get generated IDs
            await session.refresh(review_session)
            for ar in agent_reviews:
                await session.refresh(ar)

            await session.commit()

            # 6. Dispatch Celery tasks for each agent review (Requirement 1.2)
            self._dispatch_agent_tasks(review_session.id, agent_reviews)

            # Expunge for return outside session context
            session.expunge(review_session)

        logger.info(
            "Submitted review session %d for document %d (company %d, "
            "%d agents assigned)",
            review_session.id,
            document_id,
            company_id,
            len(agent_reviews),
        )
        return review_session

    async def get_session(
        self, session_id: int, company_id: int
    ) -> ReviewSession | None:
        """Get a review session by ID scoped to a company.

        Args:
            session_id: The review session primary key.
            company_id: Company scope for multi-tenancy.

        Returns:
            The ReviewSession if found, else None.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(ReviewSession).where(
                    ReviewSession.id == session_id,
                    ReviewSession.company_id == company_id,
                )
            )
            review_session = result.scalar_one_or_none()
            if review_session:
                session.expunge(review_session)
            return review_session

    async def list_sessions(
        self,
        company_id: int,
        status: str | None = None,
        document_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_score: float | None = None,
        max_score: float | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ReviewSession], int]:
        """List review sessions with pagination and filtering.

        Supports filtering by status, document type, date range, and
        compliance score range. Returns both the paginated results and
        the total count for pagination metadata.

        Args:
            company_id: Company scope for multi-tenancy.
            status: Optional filter by session status.
            document_type: Optional filter by document type.
            date_from: Optional filter for sessions submitted on or after.
            date_to: Optional filter for sessions submitted on or before.
            min_score: Optional minimum compliance score filter.
            max_score: Optional maximum compliance score filter.
            limit: Maximum number of results to return (default 20).
            offset: Number of results to skip (default 0).

        Returns:
            Tuple of (list of ReviewSession, total count).
        """
        async with self._session_factory() as session:
            # Build base query with company filter
            conditions = [ReviewSession.company_id == company_id]

            if status is not None:
                conditions.append(ReviewSession.status == status)

            if date_from is not None:
                conditions.append(ReviewSession.submitted_at >= date_from)

            if date_to is not None:
                conditions.append(ReviewSession.submitted_at <= date_to)

            if min_score is not None:
                conditions.append(ReviewSession.compliance_score >= min_score)

            if max_score is not None:
                conditions.append(ReviewSession.compliance_score <= max_score)

            # Join with Document for document_type filter
            base_query = select(ReviewSession)
            count_query = select(func.count(ReviewSession.id))

            if document_type is not None:
                base_query = base_query.join(
                    Document, ReviewSession.document_id == Document.id
                )
                count_query = count_query.join(
                    Document, ReviewSession.document_id == Document.id
                )
                conditions.append(Document.document_type == document_type)

            # Apply all conditions
            where_clause = and_(*conditions)
            base_query = base_query.where(where_clause)
            count_query = count_query.where(where_clause)

            # Get total count
            count_result = await session.execute(count_query)
            total = count_result.scalar() or 0

            # Get paginated results
            results_query = (
                base_query
                .order_by(ReviewSession.submitted_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(results_query)
            sessions = list(result.scalars().all())

            for s in sessions:
                session.expunge(s)

            return sessions, total

    async def approve_session(
        self, session_id: int, company_id: int
    ) -> ReviewSession:
        """Approve a completed review session.

        Only sessions with status "Completed" can be approved.

        Args:
            session_id: The review session primary key.
            company_id: Company scope for multi-tenancy.

        Returns:
            The updated ReviewSession with status "Approved".

        Raises:
            ValueError: If session not found or not in "Completed" status.
        """
        return await self._transition_session(
            session_id, company_id, "Approved"
        )

    async def reject_session(
        self, session_id: int, company_id: int
    ) -> ReviewSession:
        """Reject a completed review session.

        Only sessions with status "Completed" can be rejected.

        Args:
            session_id: The review session primary key.
            company_id: Company scope for multi-tenancy.

        Returns:
            The updated ReviewSession with status "Rejected".

        Raises:
            ValueError: If session not found or not in "Completed" status.
        """
        return await self._transition_session(
            session_id, company_id, "Rejected"
        )

    # -----------------------------------------------------------------------
    # Action Item CRUD
    # -----------------------------------------------------------------------

    async def create_action_item(
        self,
        session_id: int,
        finding_id: str,
        title: str,
        description: str,
        severity: str,
        assigned_to: int | None,
        company_id: int,
    ) -> ActionItem:
        """Create a new action item for a review session.

        Args:
            session_id: The review session this action item belongs to.
            finding_id: Identifier linking to the specific finding.
            title: Short description of the action item.
            description: Detailed description of what needs to be done.
            severity: Finding severity (Critical/Major/Minor/Informational).
            assigned_to: Optional user ID to assign the item to.
            company_id: Company scope for multi-tenancy.

        Returns:
            The created ActionItem instance.

        Raises:
            ValueError: If the review session is not found or doesn't
                belong to the company.
        """
        async with self._session_factory() as session:
            # Validate session exists and belongs to company
            review_session = await self._get_session_or_raise(
                session, session_id, company_id
            )

            action_item = ActionItem(
                session_id=review_session.id,
                finding_id=finding_id,
                title=title,
                description=description,
                severity=severity,
                status="Open",
                assigned_to=assigned_to,
            )
            session.add(action_item)
            await session.commit()
            await session.refresh(action_item)
            session.expunge(action_item)

        logger.info(
            "Created action item %d for session %d (severity=%s)",
            action_item.id,
            session_id,
            severity,
        )
        return action_item

    async def update_action_item(
        self,
        session_id: int,
        item_id: int,
        status: str,
        resolution_note: str | None,
        company_id: int,
    ) -> ActionItem:
        """Update an action item's status.

        Validates the status transition is valid according to the
        action item state machine.

        Args:
            session_id: The review session the action item belongs to.
            item_id: The action item primary key.
            status: The new status to transition to.
            resolution_note: Optional note explaining the resolution.
            company_id: Company scope for multi-tenancy.

        Returns:
            The updated ActionItem instance.

        Raises:
            ValueError: If the action item is not found, doesn't belong
                to the session/company, or the transition is invalid.
        """
        async with self._session_factory() as session:
            # Validate session belongs to company
            await self._get_session_or_raise(session, session_id, company_id)

            # Get the action item
            result = await session.execute(
                select(ActionItem).where(
                    ActionItem.id == item_id,
                    ActionItem.session_id == session_id,
                )
            )
            action_item = result.scalar_one_or_none()
            if action_item is None:
                raise ValueError(
                    f"Action item {item_id} not found for session {session_id}"
                )

            # Validate status transition
            valid_transitions = _VALID_ACTION_ITEM_TRANSITIONS.get(
                action_item.status, set()
            )
            if status not in valid_transitions:
                raise ValueError(
                    f"Invalid status transition from '{action_item.status}' "
                    f"to '{status}'. Valid transitions: {valid_transitions}"
                )

            # Apply update
            action_item.status = status
            if resolution_note is not None:
                action_item.resolution_note = resolution_note

            # Set resolved_at for terminal states
            if status in {"Resolved", "Dismissed"}:
                action_item.resolved_at = func.now()

            await session.commit()
            await session.refresh(action_item)
            session.expunge(action_item)

        logger.info(
            "Updated action item %d to status '%s'",
            item_id,
            status,
        )
        return action_item

    async def list_action_items(
        self, session_id: int, company_id: int
    ) -> list[ActionItem]:
        """List all action items for a review session.

        Args:
            session_id: The review session to list items for.
            company_id: Company scope for multi-tenancy.

        Returns:
            List of ActionItem instances for the session.

        Raises:
            ValueError: If the review session is not found or doesn't
                belong to the company.
        """
        async with self._session_factory() as session:
            # Validate session belongs to company
            await self._get_session_or_raise(session, session_id, company_id)

            result = await session.execute(
                select(ActionItem)
                .where(ActionItem.session_id == session_id)
                .order_by(ActionItem.created_at.desc())
            )
            items = list(result.scalars().all())
            for item in items:
                session.expunge(item)
            return items

    # -----------------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------------

    async def _transition_session(
        self, session_id: int, company_id: int, target_status: str
    ) -> ReviewSession:
        """Transition a review session to a new status.

        Validates the transition is allowed from the current status.

        Args:
            session_id: The review session primary key.
            company_id: Company scope for multi-tenancy.
            target_status: The desired new status.

        Returns:
            The updated ReviewSession.

        Raises:
            ValueError: If session not found or transition is invalid.
        """
        async with self._session_factory() as session:
            review_session = await self._get_session_or_raise(
                session, session_id, company_id
            )

            # Validate transition
            valid_targets = _VALID_SESSION_TRANSITIONS.get(
                review_session.status, set()
            )
            if target_status not in valid_targets:
                raise ValueError(
                    f"Only completed sessions can be "
                    f"{'approved' if target_status == 'Approved' else 'rejected'}"
                )

            review_session.status = target_status
            await session.commit()
            await session.refresh(review_session)
            session.expunge(review_session)

        logger.info(
            "Transitioned session %d to status '%s'",
            session_id,
            target_status,
        )
        return review_session

    async def _get_session_or_raise(
        self, session: AsyncSession, session_id: int, company_id: int
    ) -> ReviewSession:
        """Get a review session or raise ValueError if not found.

        Args:
            session: Active async DB session.
            session_id: The review session primary key.
            company_id: Company scope for multi-tenancy.

        Returns:
            The ReviewSession instance.

        Raises:
            ValueError: If session not found or doesn't belong to company.
        """
        result = await session.execute(
            select(ReviewSession).where(
                ReviewSession.id == session_id,
                ReviewSession.company_id == company_id,
            )
        )
        review_session = result.scalar_one_or_none()
        if review_session is None:
            raise ValueError(f"Review session {session_id} not found")
        return review_session

    def _dispatch_agent_tasks(
        self, session_id: int, agent_reviews: list[AgentReview]
    ) -> None:
        """Dispatch Celery tasks for each agent review.

        Imports the Celery task lazily to avoid circular imports and
        dispatches one task per agent review record.

        Args:
            session_id: The review session ID.
            agent_reviews: List of AgentReview records to dispatch.
        """
        try:
            from alcoabase.tasks.review_tasks import execute_agent_review

            for agent_review in agent_reviews:
                execute_agent_review.delay(
                    session_id=session_id,
                    agent_review_id=agent_review.id,
                    agent_id=agent_review.agent_definition_id,
                )
                logger.debug(
                    "Dispatched review task for agent_review %d (agent %d)",
                    agent_review.id,
                    agent_review.agent_definition_id,
                )
        except ImportError:
            # Celery tasks module may not be available in test environments
            logger.warning(
                "Could not import review_tasks; skipping Celery dispatch "
                "for session %d",
                session_id,
            )


class ConflictError(Exception):
    """Raised when an operation conflicts with existing state.

    Used for HTTP 409 responses, e.g., when a document already has
    an active review session.
    """

    pass
