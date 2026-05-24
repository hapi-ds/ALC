"""Training Planner Service for AI-powered schedule generation and skill gap analysis.

This module implements:
- Priority computation based on deadline proximity and access-gate elevation
- Compliance percentage calculation
- Async schedule generation dispatch via Celery
- Skill gap analysis (company-wide and per-user)
- Skill gap recalculation comparing required vs completed training

References:
    - Design doc Section 1: Training Planner Service
    - Requirements 1.1–1.10: AI Training Planner — Schedule Generation
    - Requirements 2.1–2.8: AI Training Planner — Skill Gap Analysis
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.training import TrainingRecord, TrainingTask
from alcoabase.models.training_ecosystem import (
    PriorityLevel,
    SkillGap,
    TrainingSchedule,
    GapType,
)
from alcoabase.models.user import User

if TYPE_CHECKING:
    from alcoabase.services.agent_registry import AgentRegistryService
    from alcoabase.services.inference_client import InferenceClient

logger = logging.getLogger(__name__)


def compute_priority(
    deadline: datetime | None,
    blocks_access: bool,
) -> PriorityLevel:
    """Determine priority based on deadline proximity and access gating.

    Pure function — no database access required.

    Priority rules:
    - Critical: deadline is within 7 days or already overdue
    - High: deadline is within 30 days
    - Medium: deadline is within 90 days
    - Low: deadline is more than 90 days away or no deadline

    Access-gate elevation: if blocks_access is True, the priority is
    elevated by one level (Low → Medium, Medium → High, High → Critical).
    Critical remains Critical.

    Args:
        deadline: The compliance deadline datetime (timezone-aware).
            If None, treated as Low priority (no deadline pressure).
        blocks_access: Whether this training item gates document access.

    Returns:
        The computed PriorityLevel enum value.
    """
    if deadline is None:
        base_priority = PriorityLevel.LOW
    else:
        now = datetime.now(UTC)
        days_until = (deadline - now).days

        if days_until <= 7:
            base_priority = PriorityLevel.CRITICAL
        elif days_until <= 30:
            base_priority = PriorityLevel.HIGH
        elif days_until <= 90:
            base_priority = PriorityLevel.MEDIUM
        else:
            base_priority = PriorityLevel.LOW

    if not blocks_access:
        return base_priority

    # Elevate by one level when access is gated
    elevation_map = {
        PriorityLevel.LOW: PriorityLevel.MEDIUM,
        PriorityLevel.MEDIUM: PriorityLevel.HIGH,
        PriorityLevel.HIGH: PriorityLevel.CRITICAL,
        PriorityLevel.CRITICAL: PriorityLevel.CRITICAL,
    }
    return elevation_map[base_priority]


def compute_compliance_percentage(completed: int, total: int) -> float:
    """Compute compliance percentage from completed and total counts.

    Pure function — no database access required.

    Args:
        completed: Number of completed training items (>= 0).
        total: Total number of required training items (>= 0).

    Returns:
        Compliance percentage rounded to 1 decimal place.
        Returns 100.0 when total is 0 (no requirements = fully compliant).
    """
    if total == 0:
        return 100.0
    return round((completed / total) * 100, 1)


class TrainingPlannerService:
    """AI-powered training schedule generation and skill gap analysis.

    Provides methods for:
    - Dispatching async schedule generation via Celery
    - Retrieving current training schedules
    - Company-wide and per-user skill gap reports
    - Skill gap recalculation

    Usage:
        service = TrainingPlannerService(
            session_factory=session_factory,
            inference_client=inference_client,
            agent_registry=agent_registry,
        )
        job_id = await service.request_schedule_generation(user_id, company_id)
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        inference_client: InferenceClient,
        agent_registry: AgentRegistryService,
    ) -> None:
        """Initialize the TrainingPlannerService.

        Args:
            session_factory: SQLAlchemy async session factory for DB access.
            inference_client: InferenceClient for LLM communication.
            agent_registry: AgentRegistryService for archetype retrieval.
        """
        self._session_factory = session_factory
        self._inference_client = inference_client
        self._agent_registry = agent_registry

    # -----------------------------------------------------------------------
    # Schedule Generation
    # -----------------------------------------------------------------------

    async def request_schedule_generation(
        self,
        user_id: int,
        company_id: int,
    ) -> str:
        """Dispatch async schedule generation task.

        Validates that the user exists and has assigned documents, then
        dispatches a Celery task for AI-powered schedule generation.

        Args:
            user_id: ID of the user to generate a schedule for.
            company_id: Company ID for tenant isolation.

        Returns:
            The job_id string for tracking the async task.

        Raises:
            HTTPException: 404 if user does not exist.
            HTTPException: 400 if user has no assigned documents.
        """
        async with self._session_factory() as session:
            # Validate user exists
            user_result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if user is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"User not found: {user_id}",
                )

            # Check if user has assigned documents (training tasks)
            task_result = await session.execute(
                select(func.count(TrainingTask.id)).where(
                    TrainingTask.assigned_user_id == user_id,
                    TrainingTask.company_id == company_id,
                )
            )
            task_count = task_result.scalar_one()

            # Also check documents in the company that require training
            doc_result = await session.execute(
                select(func.count(Document.id)).where(
                    Document.company_id == company_id,
                    Document.current_status.in_(
                        ["InTraining", "Active", "Approved"]
                    ),
                )
            )
            doc_count = doc_result.scalar_one()

            if task_count == 0 and doc_count == 0:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"No training items could be identified for user {user_id}. "
                        "The user has no assigned documents requiring training."
                    ),
                )

        # Generate job_id and dispatch Celery task
        job_id = uuid.uuid4().hex

        from alcoabase.tasks.training_tasks import generate_training_schedule

        generate_training_schedule.delay(
            user_id=user_id,
            company_id=company_id,
            job_id=job_id,
        )

        logger.info(
            "Dispatched schedule generation for user %d, company %d (job_id=%s)",
            user_id,
            company_id,
            job_id,
        )

        return job_id

    async def get_schedule(
        self,
        user_id: int,
        company_id: int,
    ) -> TrainingSchedule | None:
        """Retrieve current training schedule for a user.

        Args:
            user_id: ID of the user.
            company_id: Company ID for tenant isolation.

        Returns:
            The TrainingSchedule instance, or None if no schedule exists.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(TrainingSchedule).where(
                    TrainingSchedule.user_id == user_id,
                    TrainingSchedule.company_id == company_id,
                )
            )
            schedule = result.scalar_one_or_none()
            if schedule is not None:
                # Expunge to detach from session for safe return
                session.expunge(schedule)
            return schedule

    # -----------------------------------------------------------------------
    # Skill Gap Analysis
    # -----------------------------------------------------------------------

    async def get_company_gaps(
        self,
        company_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Aggregated skill gap report for the company.

        Returns a report containing:
        - total_users_with_gaps: count of users with at least one unresolved gap
        - company_compliance_percentage: overall compliance
        - top_documents: documents with the most untrained users
        - top_users: users with the most outstanding training items
        - by_framework: per-regulatory-framework compliance (if tags exist)
        - total: total gap records for pagination

        Args:
            company_id: Company ID for tenant isolation.
            limit: Maximum number of items in top lists (default 20).
            offset: Offset for pagination (default 0).

        Returns:
            Dictionary matching CompanyGapReportResponse schema.
        """
        async with self._session_factory() as session:
            # Total unresolved gaps
            total_result = await session.execute(
                select(func.count(SkillGap.id)).where(
                    SkillGap.company_id == company_id,
                    SkillGap.resolved_at.is_(None),
                )
            )
            total_gaps = total_result.scalar_one()

            # Total users with gaps
            users_with_gaps_result = await session.execute(
                select(func.count(func.distinct(SkillGap.user_id))).where(
                    SkillGap.company_id == company_id,
                    SkillGap.resolved_at.is_(None),
                )
            )
            total_users_with_gaps = users_with_gaps_result.scalar_one()

            # Company compliance percentage
            # Total required = all training tasks in company
            total_required_result = await session.execute(
                select(func.count(TrainingTask.id)).where(
                    TrainingTask.company_id == company_id,
                )
            )
            total_required = total_required_result.scalar_one()

            # Total completed = completed training tasks
            total_completed_result = await session.execute(
                select(func.count(TrainingTask.id)).where(
                    TrainingTask.company_id == company_id,
                    TrainingTask.is_completed.is_(True),
                )
            )
            total_completed = total_completed_result.scalar_one()

            company_compliance = compute_compliance_percentage(
                total_completed, total_required
            )

            # Top documents with most untrained users
            top_docs_result = await session.execute(
                select(
                    SkillGap.document_id,
                    func.count(func.distinct(SkillGap.user_id)).label(
                        "user_count"
                    ),
                )
                .where(
                    SkillGap.company_id == company_id,
                    SkillGap.resolved_at.is_(None),
                )
                .group_by(SkillGap.document_id)
                .order_by(
                    func.count(func.distinct(SkillGap.user_id)).desc()
                )
                .offset(offset)
                .limit(limit)
            )
            top_docs_rows = top_docs_result.all()

            top_documents = []
            for row in top_docs_rows:
                doc_result = await session.execute(
                    select(Document.title).where(
                        Document.id == row.document_id
                    )
                )
                doc_title = doc_result.scalar_one_or_none() or "Unknown"
                top_documents.append(
                    {
                        "document_id": row.document_id,
                        "title": doc_title,
                        "untrained_users": row.user_count,
                    }
                )

            # Top users with most outstanding training items
            top_users_result = await session.execute(
                select(
                    SkillGap.user_id,
                    func.count(SkillGap.id).label("gap_count"),
                )
                .where(
                    SkillGap.company_id == company_id,
                    SkillGap.resolved_at.is_(None),
                )
                .group_by(SkillGap.user_id)
                .order_by(func.count(SkillGap.id).desc())
                .offset(offset)
                .limit(limit)
            )
            top_users_rows = top_users_result.all()

            top_users = []
            for row in top_users_rows:
                user_result = await session.execute(
                    select(User.full_name).where(User.id == row.user_id)
                )
                user_name = user_result.scalar_one_or_none() or "Unknown"
                top_users.append(
                    {
                        "user_id": row.user_id,
                        "full_name": user_name,
                        "outstanding_items": row.gap_count,
                    }
                )

            # Per-framework compliance (based on document tags)
            by_framework = await self._compute_framework_compliance(
                session, company_id
            )

            return {
                "total_users_with_gaps": total_users_with_gaps,
                "company_compliance_percentage": company_compliance,
                "top_documents": top_documents,
                "top_users": top_users,
                "by_framework": by_framework,
                "total": total_gaps,
            }

    async def _compute_framework_compliance(
        self,
        session: AsyncSession,
        company_id: int,
    ) -> dict[str, float] | None:
        """Compute per-regulatory-framework compliance percentages.

        Groups documents by regulatory tags (GMP, ISO, etc.) and computes
        compliance for each framework.

        Args:
            session: Active async database session.
            company_id: Company ID for tenant isolation.

        Returns:
            Dictionary of framework name to compliance percentage,
            or None if no regulatory tags exist.
        """
        from alcoabase.models.document import DocumentTag

        # Get all documents with regulatory-like tags in this company
        tag_result = await session.execute(
            select(DocumentTag.tag, Document.id)
            .join(Document, DocumentTag.document_id == Document.id)
            .where(Document.company_id == company_id)
        )
        tag_rows = tag_result.all()

        if not tag_rows:
            return None

        # Group documents by tag
        framework_docs: dict[str, set[int]] = {}
        for tag, doc_id in tag_rows:
            # Only include regulatory-like tags
            tag_upper = tag.upper()
            if any(
                fw in tag_upper
                for fw in ["GMP", "GLP", "GCP", "ISO", "FDA", "EMA", "ICH"]
            ):
                framework_docs.setdefault(tag, set()).add(doc_id)

        if not framework_docs:
            return None

        result: dict[str, float] = {}
        for framework, doc_ids in framework_docs.items():
            # Count training tasks for these documents
            total_result = await session.execute(
                select(func.count(TrainingTask.id)).where(
                    TrainingTask.company_id == company_id,
                    TrainingTask.sop_document_uuid.in_(
                        select(Document.document_uuid).where(
                            Document.id.in_(doc_ids)
                        )
                    ),
                )
            )
            total = total_result.scalar_one()

            completed_result = await session.execute(
                select(func.count(TrainingTask.id)).where(
                    TrainingTask.company_id == company_id,
                    TrainingTask.is_completed.is_(True),
                    TrainingTask.sop_document_uuid.in_(
                        select(Document.document_uuid).where(
                            Document.id.in_(doc_ids)
                        )
                    ),
                )
            )
            completed = completed_result.scalar_one()

            result[framework] = compute_compliance_percentage(
                completed, total
            )

        return result if result else None

    async def get_user_gaps(
        self,
        user_id: int,
        company_id: int,
    ) -> list[SkillGap]:
        """Individual skill gap detail for a user.

        Args:
            user_id: ID of the user.
            company_id: Company ID for tenant isolation.

        Returns:
            List of unresolved SkillGap records for the user.

        Raises:
            HTTPException: 404 if user does not exist or doesn't belong
                to the company.
        """
        async with self._session_factory() as session:
            # Validate user exists
            user_result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if user is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"User not found: {user_id}",
                )

            # Retrieve unresolved gaps
            result = await session.execute(
                select(SkillGap).where(
                    SkillGap.user_id == user_id,
                    SkillGap.company_id == company_id,
                    SkillGap.resolved_at.is_(None),
                )
            )
            gaps = list(result.scalars().all())

            # Expunge all to detach from session
            for gap in gaps:
                session.expunge(gap)

            return gaps

    # -----------------------------------------------------------------------
    # Skill Gap Recalculation
    # -----------------------------------------------------------------------

    async def recalculate_gaps(self, company_id: int) -> int:
        """Recalculate all skill gaps for a company.

        Compares required documents (documents in InTraining/Active/Approved
        status) against completed training records for all users in the
        company. Creates new SkillGap records for missing training and
        resolves gaps where training has been completed.

        Args:
            company_id: Company ID to recalculate gaps for.

        Returns:
            Number of gap records created or updated.
        """
        changes = 0

        async with self._session_factory() as session:
            # Get all documents requiring training in this company
            docs_result = await session.execute(
                select(Document).where(
                    Document.company_id == company_id,
                    Document.current_status.in_(
                        ["InTraining", "Active", "Approved"]
                    ),
                )
            )
            required_docs = list(docs_result.scalars().all())

            if not required_docs:
                # No documents require training — resolve all existing gaps
                resolve_result = await session.execute(
                    select(SkillGap).where(
                        SkillGap.company_id == company_id,
                        SkillGap.resolved_at.is_(None),
                    )
                )
                unresolved = list(resolve_result.scalars().all())
                now = datetime.now(UTC)
                for gap in unresolved:
                    gap.resolved_at = now
                    changes += 1
                await session.commit()
                return changes

            # Get all active users in the company (users with training tasks)
            users_result = await session.execute(
                select(func.distinct(TrainingTask.assigned_user_id)).where(
                    TrainingTask.company_id == company_id,
                )
            )
            user_ids = [row[0] for row in users_result.all()]

            if not user_ids:
                await session.commit()
                return 0

            # Get all valid training records for this company
            records_result = await session.execute(
                select(TrainingRecord).where(
                    TrainingRecord.company_id == company_id,
                    TrainingRecord.is_valid.is_(True),
                )
            )
            training_records = list(records_result.scalars().all())

            # Build a set of (user_id, sop_document_uuid) for completed training
            completed_set: set[tuple[int, str]] = {
                (r.user_id, r.sop_document_uuid) for r in training_records
            }

            # For each user × document, check if training is complete
            now = datetime.now(UTC)

            for user_id in user_ids:
                for doc in required_docs:
                    # Get latest version for this document
                    version_result = await session.execute(
                        select(DocumentVersion)
                        .where(DocumentVersion.document_id == doc.id)
                        .order_by(
                            DocumentVersion.major_version.desc(),
                            DocumentVersion.minor_version.desc(),
                        )
                        .limit(1)
                    )
                    latest_version = version_result.scalar_one_or_none()
                    if latest_version is None:
                        continue

                    has_training = (
                        user_id,
                        doc.document_uuid,
                    ) in completed_set

                    # Check for existing gap
                    existing_gap_result = await session.execute(
                        select(SkillGap).where(
                            SkillGap.user_id == user_id,
                            SkillGap.document_id == doc.id,
                            SkillGap.document_version_id == latest_version.id,
                            SkillGap.gap_type == GapType.MISSING_TRAINING,
                            SkillGap.company_id == company_id,
                        )
                    )
                    existing_gap = existing_gap_result.scalar_one_or_none()

                    if has_training:
                        # Resolve existing gap if present
                        if (
                            existing_gap is not None
                            and existing_gap.resolved_at is None
                        ):
                            existing_gap.resolved_at = now
                            changes += 1
                    else:
                        # Create gap if not already present
                        if existing_gap is None:
                            # Determine if this document blocks access
                            blocks_access = doc.current_status in [
                                "InTraining",
                                "Active",
                            ]

                            # Compute priority (no deadline info available
                            # from document model, use None)
                            priority = compute_priority(
                                deadline=None,
                                blocks_access=blocks_access,
                            )

                            new_gap = SkillGap(
                                user_id=user_id,
                                company_id=company_id,
                                document_id=doc.id,
                                document_version_id=latest_version.id,
                                gap_type=GapType.MISSING_TRAINING,
                                priority=priority,
                                days_overdue=0,
                                blocks_access=blocks_access,
                                identified_at=now,
                            )
                            session.add(new_gap)
                            changes += 1
                        elif existing_gap.resolved_at is not None:
                            # Gap was resolved but training is now missing
                            # (e.g., record invalidated) — create new gap
                            blocks_access = doc.current_status in [
                                "InTraining",
                                "Active",
                            ]
                            priority = compute_priority(
                                deadline=None,
                                blocks_access=blocks_access,
                            )

                            new_gap = SkillGap(
                                user_id=user_id,
                                company_id=company_id,
                                document_id=doc.id,
                                document_version_id=latest_version.id,
                                gap_type=GapType.MISSING_TRAINING,
                                priority=priority,
                                days_overdue=0,
                                blocks_access=blocks_access,
                                identified_at=now,
                            )
                            session.add(new_gap)
                            changes += 1

            await session.commit()

        logger.info(
            "Recalculated skill gaps for company %d: %d changes",
            company_id,
            changes,
        )
        return changes
