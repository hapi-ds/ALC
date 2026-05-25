"""Impact Notification Service for AI-Driven Change Impact Analysis.

Creates and manages impact notifications for document owners when
critical or major findings are identified. Handles training task resets
and document impact status computation.

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.document import Document
from alcoabase.models.impact_analysis import ImpactNotification, ImpactReport
from alcoabase.models.training import TrainingTask
from alcoabase.schemas.impact_analysis import (
    DocumentImpactStatusResponse,
    NotificationResponse,
    PaginationParams,
)

logger = logging.getLogger(__name__)

# Severities that trigger notification creation
_NOTIFIABLE_SEVERITIES = frozenset({"critical", "major"})

# Severity ordering for sorting (lower value = higher priority)
_SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2, "unknown": 3}


class ImpactNotificationService:
    """Service for managing impact notifications and training task resets.

    Handles:
    - Creating notifications for document owners on critical/major findings
    - Acknowledging notifications (idempotent)
    - Listing unacknowledged notifications sorted by severity/date
    - Resetting training tasks when retraining is required
    - Computing document impact status

    All operations are scoped by company_id for tenant isolation.
    """

    async def create_notifications(
        self,
        session: AsyncSession,
        report_id: str,
        affected_items: list[dict],
        company_id: int,
    ) -> list[int]:
        """Create notifications for critical/major severity affected items.

        Only creates notifications for items with impact_severity "critical"
        or "major". Targets the document owner (Document.created_by).
        Deduplicates against existing unacknowledged notifications with the
        same (report_id, affected_document_uuid, target_user_id).

        Args:
            session: Active database session.
            report_id: UUID of the associated impact report.
            affected_items: List of AffectedItemSchema dicts from the report.
            company_id: Company ID for tenant scoping.

        Returns:
            List of notification IDs that were created.
        """
        created_ids: list[int] = []

        for item in affected_items:
            severity = item.get("impact_severity")
            if severity not in _NOTIFIABLE_SEVERITIES:
                continue

            affected_doc_uuid = item.get("affected_document_uuid")
            if not affected_doc_uuid:
                # Training tasks without a document UUID don't get notifications
                continue

            # Look up the document owner (created_by)
            doc_result = await session.execute(
                select(Document.created_by).where(
                    Document.document_uuid == affected_doc_uuid,
                    Document.company_id == company_id,
                )
            )
            target_user_id = doc_result.scalar_one_or_none()
            if target_user_id is None:
                logger.warning(
                    "Document %s not found in company %d, skipping notification",
                    affected_doc_uuid,
                    company_id,
                )
                continue

            # Deduplicate: check for existing unacknowledged notification
            existing = await session.execute(
                select(ImpactNotification.id).where(
                    ImpactNotification.report_id == report_id,
                    ImpactNotification.affected_document_uuid == affected_doc_uuid,
                    ImpactNotification.target_user_id == target_user_id,
                    ImpactNotification.is_acknowledged == False,  # noqa: E712
                )
            )
            if existing.scalar_one_or_none() is not None:
                # Notification already exists, skip (Requirement 8.8)
                continue

            # Create the notification
            change_summary = item.get("change_summary", "")[:2000]
            notification = ImpactNotification(
                report_id=report_id,
                affected_document_uuid=affected_doc_uuid,
                notification_type="change_impact",
                impact_severity=severity,
                change_summary=change_summary,
                target_user_id=target_user_id,
                is_acknowledged=False,
                company_id=company_id,
            )
            session.add(notification)
            await session.flush()
            created_ids.append(notification.id)

        return created_ids

    async def acknowledge_notification(
        self,
        session: AsyncSession,
        notification_id: int,
        user_id: int,
        company_id: int,
    ) -> NotificationResponse | None:
        """Acknowledge a notification (idempotent).

        Marks the notification as acknowledged with the user_id and timestamp.
        If already acknowledged, returns the existing acknowledgment details
        without modification (idempotent per Requirement 8.3).

        Args:
            session: Active database session.
            notification_id: ID of the notification to acknowledge.
            user_id: ID of the user acknowledging.
            company_id: Company ID for tenant scoping.

        Returns:
            NotificationResponse if found, None if not found or wrong company.
        """
        result = await session.execute(
            select(ImpactNotification).where(
                ImpactNotification.id == notification_id,
                ImpactNotification.company_id == company_id,
            )
        )
        notification = result.scalar_one_or_none()

        if notification is None:
            return None

        # Idempotent: if already acknowledged, return as-is
        if not notification.is_acknowledged:
            notification.is_acknowledged = True
            notification.acknowledged_at = datetime.now(timezone.utc)
            notification.acknowledged_by = user_id
            await session.flush()

        return NotificationResponse.model_validate(notification)

    async def get_unacknowledged(
        self,
        session: AsyncSession,
        user_id: int,
        company_id: int,
        pagination: PaginationParams | None = None,
    ) -> dict:
        """Get unacknowledged notifications for a user.

        Sorted by severity (critical first) then created_at (newest first).

        Args:
            session: Active database session.
            user_id: ID of the target user.
            company_id: Company ID for tenant scoping.
            pagination: Optional pagination parameters.

        Returns:
            Dict with "notifications" (list of NotificationResponse) and
            "total_count" (int).
        """
        if pagination is None:
            pagination = PaginationParams()

        conditions = [
            ImpactNotification.target_user_id == user_id,
            ImpactNotification.company_id == company_id,
            ImpactNotification.is_acknowledged == False,  # noqa: E712
        ]

        # Count total
        count_stmt = select(func.count(ImpactNotification.id)).where(*conditions)
        total_count = (await session.execute(count_stmt)).scalar_one()

        # Build severity ordering using CASE expression
        severity_order = case(
            (ImpactNotification.impact_severity == "critical", 0),
            (ImpactNotification.impact_severity == "major", 1),
            (ImpactNotification.impact_severity == "minor", 2),
            else_=3,
        )

        # Query with sorting and pagination
        query = (
            select(ImpactNotification)
            .where(*conditions)
            .order_by(severity_order, ImpactNotification.created_at.desc())
            .limit(pagination.limit)
            .offset(pagination.offset)
        )
        result = await session.execute(query)
        notifications = list(result.scalars().all())

        return {
            "notifications": [
                NotificationResponse.model_validate(n) for n in notifications
            ],
            "total_count": total_count,
        }

    async def reset_training_tasks(
        self,
        session: AsyncSession,
        affected_items: list[dict],
        report_id: str,
    ) -> dict:
        """Reset training tasks for items with recommended_action "retraining_required".

        Sets is_completed=false for affected TrainingTasks (idempotent).
        Records failures in a metadata dict for inclusion in the report.

        Args:
            session: Active database session.
            affected_items: List of AffectedItemSchema dicts from the report.
            report_id: UUID of the associated impact report.

        Returns:
            Dict with "reset_count" (int) and "failures" (list of failure dicts).
        """
        reset_count = 0
        failures: list[dict] = []

        for item in affected_items:
            if item.get("recommended_action") != "retraining_required":
                continue

            training_task_id = item.get("training_task_id")
            affected_doc_uuid = item.get("affected_document_uuid")

            if training_task_id:
                # Reset by training task ID
                try:
                    result = await session.execute(
                        select(TrainingTask).where(
                            TrainingTask.id == training_task_id,
                        )
                    )
                    task = result.scalar_one_or_none()
                    if task is None:
                        failures.append(
                            {
                                "training_task_id": training_task_id,
                                "reason": "TrainingTask not found",
                                "report_id": report_id,
                            }
                        )
                        continue

                    # Idempotent: only update if currently completed
                    if task.is_completed:
                        task.is_completed = False
                        task.completed_at = None
                        await session.flush()
                    reset_count += 1
                except Exception as e:
                    logger.warning(
                        "Failed to reset TrainingTask %d: %s",
                        training_task_id,
                        str(e),
                    )
                    failures.append(
                        {
                            "training_task_id": training_task_id,
                            "reason": f"Database error: {type(e).__name__}",
                            "report_id": report_id,
                        }
                    )

            elif affected_doc_uuid:
                # Reset all training tasks for the affected document
                try:
                    result = await session.execute(
                        select(TrainingTask).where(
                            TrainingTask.sop_document_uuid == affected_doc_uuid,
                            TrainingTask.is_completed == True,  # noqa: E712
                        )
                    )
                    tasks = list(result.scalars().all())

                    for task in tasks:
                        task.is_completed = False
                        task.completed_at = None
                        reset_count += 1

                    await session.flush()
                except Exception as e:
                    logger.warning(
                        "Failed to reset TrainingTasks for document %s: %s",
                        affected_doc_uuid,
                        str(e),
                    )
                    failures.append(
                        {
                            "affected_document_uuid": affected_doc_uuid,
                            "reason": f"Database error: {type(e).__name__}",
                            "report_id": report_id,
                        }
                    )

        return {
            "reset_count": reset_count,
            "failures": failures,
        }

    async def get_document_status(
        self,
        session: AsyncSession,
        document_uuid: str,
        company_id: int,
    ) -> DocumentImpactStatusResponse:
        """Compute the impact status for a document.

        Determines is_up_to_date based on unacknowledged critical/major
        notifications where this document is the affected target.

        Args:
            session: Active database session.
            document_uuid: UUID of the document to check.
            company_id: Company ID for tenant scoping.

        Returns:
            DocumentImpactStatusResponse with outstanding counts and status.
        """
        # Count outstanding critical notifications
        critical_count_result = await session.execute(
            select(func.count(ImpactNotification.id)).where(
                ImpactNotification.affected_document_uuid == document_uuid,
                ImpactNotification.company_id == company_id,
                ImpactNotification.is_acknowledged == False,  # noqa: E712
                ImpactNotification.impact_severity == "critical",
            )
        )
        outstanding_critical = critical_count_result.scalar_one()

        # Count outstanding major notifications
        major_count_result = await session.execute(
            select(func.count(ImpactNotification.id)).where(
                ImpactNotification.affected_document_uuid == document_uuid,
                ImpactNotification.company_id == company_id,
                ImpactNotification.is_acknowledged == False,  # noqa: E712
                ImpactNotification.impact_severity == "major",
            )
        )
        outstanding_major = major_count_result.scalar_one()

        # Get the latest analysis report for this document
        latest_report_result = await session.execute(
            select(ImpactReport.analysis_timestamp, ImpactReport.report_id)
            .where(
                ImpactReport.triggering_document_uuid == document_uuid,
                ImpactReport.company_id == company_id,
            )
            .order_by(ImpactReport.analysis_timestamp.desc())
            .limit(1)
        )
        latest_report = latest_report_result.one_or_none()

        last_analysis_date = None
        last_analysis_report_id = None
        if latest_report:
            last_analysis_date = latest_report.analysis_timestamp
            last_analysis_report_id = latest_report.report_id

        is_up_to_date = (outstanding_critical + outstanding_major) == 0

        return DocumentImpactStatusResponse(
            document_uuid=document_uuid,
            last_analysis_date=last_analysis_date,
            last_analysis_report_id=last_analysis_report_id,
            outstanding_critical_count=outstanding_critical,
            outstanding_major_count=outstanding_major,
            is_up_to_date=is_up_to_date,
        )
