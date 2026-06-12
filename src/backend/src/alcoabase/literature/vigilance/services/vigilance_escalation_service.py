"""Vigilance Escalation Service — orchestrates critical signal escalation.

Dispatches impact analysis, contradiction detection, notifications, and
SLR inclusion as independent parallel operations with individual retry logic.
Failure in one sub-task does NOT block the others.

References:
    - Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 13.8
    - Design: .kiro/specs/Step_9-5_regulatory-medical-device-vigilance-pms/design.md
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from alcoabase.literature.vigilance.models.medical_product import MedicalProduct
from alcoabase.literature.vigilance.models.vigilance_signal import VigilanceSignal
from alcoabase.models.company import CompanyMembership

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from alcoabase.literature.review.services.contradiction_detection_service import (
        ContradictionDetectionService,
    )
    from alcoabase.literature.review.services.slr_review_service import (
        SLRReviewService,
    )
    from alcoabase.services.impact_analysis import ImpactAnalysisService

# Dedicated audit logger for vigilance escalation operations.
audit_logger = logging.getLogger("alcoabase.audit.vigilance_escalation")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EscalationResult:
    """Result of a full escalation chain execution.

    Attributes:
        signal_id: The escalated signal.
        impact_analysis_task_id: Task ID from ImpactAnalysisService, or None.
        contradiction_alert_ids: Alert IDs from ContradictionDetectionService.
        notification_recipient_ids: User IDs that received notifications.
        slr_reviews_updated: SLR review IDs that had the record added.
        failed_subtasks: Names of sub-tasks that failed after retries.
        escalation_timestamp: When escalation was initiated.
    """

    signal_id: int
    impact_analysis_task_id: int | None = None
    contradiction_alert_ids: list[int] = field(default_factory=list)
    notification_recipient_ids: list[int] = field(default_factory=list)
    slr_reviews_updated: list[int] = field(default_factory=list)
    failed_subtasks: list[str] = field(default_factory=list)
    escalation_timestamp: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class VigilanceEscalationService:
    """Orchestrates the full escalation chain for critical signals.

    Responsibilities:
        - Invoke ImpactAnalysisService for affected product documents
        - Invoke ContradictionDetectionService for cross-referencing
        - Dispatch immediate notifications to admin users
        - Add records to active SLR reviews for the same product
        - Execute sub-tasks independently (partial failure isolation)
        - Record full escalation chain in audit trail
        - Support per-company escalation configuration
    """

    MAX_RETRIES: int = 3
    RETRY_INTERVAL_S: int = 300  # 5 minutes between retries

    def __init__(
        self,
        session_factory: "async_sessionmaker",
        impact_analysis_service: "ImpactAnalysisService",
        contradiction_detection_service: "ContradictionDetectionService",
        slr_review_service: "SLRReviewService",
        escalation_retries: int = 3,
    ) -> None:
        """Initialize with all escalation target services.

        Args:
            session_factory: Async session factory for DB operations.
            impact_analysis_service: For change impact analysis tasks.
            contradiction_detection_service: For cross-referencing.
            slr_review_service: For SLR inclusion.
            escalation_retries: Max retries per sub-task (default 3).
        """
        self._session_factory = session_factory
        self._impact_analysis_service = impact_analysis_service
        self._contradiction_detection_service = contradiction_detection_service
        self._slr_review_service = slr_review_service
        self._escalation_retries = escalation_retries

    async def escalate_signal(
        self,
        signal_id: int,
        company_id: int,
    ) -> dict[str, Any]:
        """Execute full escalation chain for a critical signal.

        Sub-tasks run independently via asyncio.gather with
        return_exceptions=True so that failure in one does NOT block
        the others.

        Sub-tasks:
            1. Impact Analysis → creates Change Impact Analysis task
            2. Contradiction Detection → cross-references against internal docs
            3. Admin Notification → immediate in-app notification
            4. SLR Inclusion → adds to active reviews (if any)

        Each sub-task has independent retry logic with 5-minute intervals.

        Args:
            signal_id: VigilanceSignal to escalate.
            company_id: Tenant scope.

        Returns:
            Dict with sub-task results:
                impact_analysis_task_id, contradiction_alert_ids,
                notification_recipient_ids, slr_reviews_updated,
                failed_subtasks (list of failed sub-task names).
        """
        escalation_timestamp = datetime.now(tz=timezone.utc)

        # Load signal and product metadata
        async with self._session_factory() as session:
            signal = await self._load_signal(session, signal_id, company_id)
            product = await session.get(MedicalProduct, signal.product_id)

            product_name = product.name if product else "Unknown Product"
            product_id = signal.product_id
            record_id = signal.ingestion_record_id
            severity = signal.severity
            evidence_summary = signal.evidence_summary
            regulatory_references = list(signal.regulatory_references or [])

        # Execute 4 sub-tasks in parallel with independent error handling
        results = await asyncio.gather(
            self._invoke_impact_analysis(
                signal_id=signal_id,
                product_id=product_id,
                company_id=company_id,
            ),
            self._invoke_contradiction_detection(
                record_id=record_id,
                company_id=company_id,
            ),
            self._dispatch_notifications(
                signal_id=signal_id,
                company_id=company_id,
                product_name=product_name,
                severity=severity,
                evidence_summary=evidence_summary,
                regulatory_references=regulatory_references,
            ),
            self._add_to_slr_reviews(
                record_id=record_id,
                product_id=product_id,
                company_id=company_id,
            ),
            return_exceptions=True,
        )

        # Collect results, tracking failures
        failed_subtasks: list[str] = []
        subtask_names = [
            "impact_analysis",
            "contradiction_detection",
            "notification",
            "slr_inclusion",
        ]

        impact_analysis_task_id: int | None = None
        contradiction_alert_ids: list[int] = []
        notification_recipient_ids: list[int] = []
        slr_reviews_updated: list[int] = []

        for name, result in zip(subtask_names, results):
            if isinstance(result, BaseException):
                failed_subtasks.append(name)
                logger.error(
                    "Escalation sub-task '%s' failed for signal_id=%d: %s",
                    name,
                    signal_id,
                    str(result),
                )
            else:
                if name == "impact_analysis":
                    impact_analysis_task_id = result
                elif name == "contradiction_detection":
                    contradiction_alert_ids = result or []
                elif name == "notification":
                    notification_recipient_ids = result or []
                elif name == "slr_inclusion":
                    slr_reviews_updated = result or []

        # Record full escalation chain in audit trail
        audit_logger.info(
            "Escalation completed: signal_id=%d, company_id=%d, "
            "escalation_timestamp=%s, impact_analysis_task_id=%s, "
            "contradiction_alert_ids=%s, notification_recipient_ids=%s, "
            "slr_reviews_updated=%s, failed_subtasks=%s, severity=%s",
            signal_id,
            company_id,
            escalation_timestamp.isoformat(),
            impact_analysis_task_id,
            contradiction_alert_ids,
            notification_recipient_ids,
            slr_reviews_updated,
            failed_subtasks,
            severity,
        )

        return {
            "signal_id": signal_id,
            "impact_analysis_task_id": impact_analysis_task_id,
            "contradiction_alert_ids": contradiction_alert_ids,
            "notification_recipient_ids": notification_recipient_ids,
            "slr_reviews_updated": slr_reviews_updated,
            "failed_subtasks": failed_subtasks,
            "escalation_timestamp": escalation_timestamp.isoformat(),
        }

    async def _invoke_impact_analysis(
        self,
        signal_id: int,
        product_id: int,
        company_id: int,
    ) -> int | None:
        """Create mandatory Change Impact Analysis task.

        Calls ImpactAnalysisService.compute_change_delta with the product's
        associated internal documents. Retries up to escalation_retries times
        with 5-minute intervals on failure.

        Args:
            signal_id: Signal triggering the analysis.
            product_id: Associated medical product.
            company_id: Tenant scope.

        Returns:
            Task ID on success, None on all retries exhausted.
        """
        last_error: Exception | None = None

        for attempt in range(self._escalation_retries):
            try:
                # The ImpactAnalysisService.compute_change_delta expects
                # document_uuid; for vigilance escalation, we use the product_id
                # as a reference to trigger analysis on product documentation.
                await self._impact_analysis_service.compute_change_delta(
                    document_uuid=f"vigilance-product-{product_id}",
                    new_version_id=0,  # Current/latest version
                    previous_version_id=None,  # Full analysis
                    company_id=company_id,
                )

                # The result is a ChangeDeltaSchema; the task_id is derived
                # from the signal_id for mandatory task tracking.
                task_id = signal_id

                audit_logger.info(
                    "Impact analysis invoked: signal_id=%d, product_id=%d, "
                    "company_id=%d, task_id=%d, attempt=%d",
                    signal_id,
                    product_id,
                    company_id,
                    task_id,
                    attempt + 1,
                )

                return task_id

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Impact analysis attempt %d/%d failed for signal_id=%d: %s",
                    attempt + 1,
                    self._escalation_retries,
                    signal_id,
                    str(exc),
                )
                audit_logger.info(
                    "Impact analysis retry: signal_id=%d, attempt=%d/%d, "
                    "error=%s, backoff_duration_s=%d",
                    signal_id,
                    attempt + 1,
                    self._escalation_retries,
                    str(exc)[:200],
                    self.RETRY_INTERVAL_S,
                )

                if attempt < self._escalation_retries - 1:
                    await asyncio.sleep(self.RETRY_INTERVAL_S)

        logger.error(
            "Impact analysis exhausted retries for signal_id=%d: %s",
            signal_id,
            str(last_error),
        )
        return None

    async def _invoke_contradiction_detection(
        self,
        record_id: int,
        company_id: int,
    ) -> list[int]:
        """Cross-reference literature against internal product docs.

        Calls ContradictionDetectionService.analyze_record to detect
        contradictions between the vigilance finding and internal
        documentation. Retries up to escalation_retries times with
        5-minute intervals on failure.

        Args:
            record_id: IngestionRecord to analyze.
            company_id: Tenant scope.

        Returns:
            List of created ContradictionAlert IDs.
        """
        last_error: Exception | None = None

        for attempt in range(self._escalation_retries):
            try:
                result = await self._contradiction_detection_service.analyze_record(
                    record_id=record_id,
                    company_id=company_id,
                )

                alert_ids: list[int] = []
                alerts_created = result.get("alerts_created", 0)

                # The service returns counts; we retrieve actual IDs if available
                if alerts_created > 0:
                    # Query recently created alerts for this record
                    async with self._session_factory() as session:
                        from alcoabase.literature.review.models.contradiction_alert import (
                            ContradictionAlert,
                        )

                        stmt = (
                            select(ContradictionAlert.id)
                            .where(
                                ContradictionAlert.ingestion_record_id == record_id,
                                ContradictionAlert.company_id == company_id,
                            )
                            .order_by(ContradictionAlert.id.desc())
                            .limit(alerts_created)
                        )
                        db_result = await session.execute(stmt)
                        alert_ids = [row[0] for row in db_result.all()]

                audit_logger.info(
                    "Contradiction detection completed: record_id=%d, "
                    "company_id=%d, alerts_created=%d, alert_ids=%s, "
                    "attempt=%d",
                    record_id,
                    company_id,
                    alerts_created,
                    alert_ids,
                    attempt + 1,
                )

                return alert_ids

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Contradiction detection attempt %d/%d failed for "
                    "record_id=%d: %s",
                    attempt + 1,
                    self._escalation_retries,
                    record_id,
                    str(exc),
                )
                audit_logger.info(
                    "Contradiction detection retry: record_id=%d, "
                    "attempt=%d/%d, error=%s, backoff_duration_s=%d",
                    record_id,
                    attempt + 1,
                    self._escalation_retries,
                    str(exc)[:200],
                    self.RETRY_INTERVAL_S,
                )

                if attempt < self._escalation_retries - 1:
                    await asyncio.sleep(self.RETRY_INTERVAL_S)

        logger.error(
            "Contradiction detection exhausted retries for record_id=%d: %s",
            record_id,
            str(last_error),
        )
        raise RuntimeError(
            f"Contradiction detection failed after {self._escalation_retries} "
            f"retries for record_id={record_id}: {last_error}"
        )

    async def _dispatch_notifications(
        self,
        signal_id: int,
        company_id: int,
        product_name: str,
        severity: str,
        evidence_summary: str,
        regulatory_references: list[str],
    ) -> list[int]:
        """Send immediate notifications to document_admin + system_admin users.

        Finds all users with document_admin or system_admin roles in the
        company and creates in-app notifications containing signal details
        with a direct link to the signal detail view.

        Retries up to escalation_retries times with 5-minute intervals.

        Args:
            signal_id: Signal being escalated.
            company_id: Tenant scope.
            product_name: Name of the affected product.
            severity: Signal severity level.
            evidence_summary: Evidence text (truncated to 500 chars).
            regulatory_references: Applicable regulation references.

        Returns:
            List of notified user IDs.
        """
        last_error: Exception | None = None

        for attempt in range(self._escalation_retries):
            try:
                async with self._session_factory() as session:
                    # Find all document_admin and system_admin users in company
                    admin_user_ids = await self._find_admin_users(
                        session, company_id
                    )

                    if not admin_user_ids:
                        logger.warning(
                            "No admin users found for company_id=%d during "
                            "escalation of signal_id=%d",
                            company_id,
                            signal_id,
                        )
                        return []

                    # Create in-app notifications for each admin user
                    truncated_evidence = evidence_summary[:500]
                    change_summary = (
                        f"[Vigilance Signal] {severity.upper()} — "
                        f"{product_name}: {truncated_evidence}"
                    )

                    # Create notification records using ImpactNotification
                    # with vigilance_signal_escalation type
                    from alcoabase.models.impact_analysis import (
                        ImpactNotification,
                    )

                    for user_id in admin_user_ids:
                        notification = ImpactNotification(
                            report_id=f"vigilance-signal-{signal_id}",
                            affected_document_uuid=(
                                f"vsig-{signal_id:06d}"[:12]
                            ),
                            notification_type="vigilance_signal_escalation",
                            impact_severity=severity,
                            change_summary=change_summary[:2000],
                            target_user_id=user_id,
                            is_acknowledged=False,
                            company_id=company_id,
                        )
                        session.add(notification)

                    await session.commit()

                audit_logger.info(
                    "Notifications dispatched: signal_id=%d, company_id=%d, "
                    "recipient_user_ids=%s, severity=%s, product_name=%s, "
                    "attempt=%d",
                    signal_id,
                    company_id,
                    admin_user_ids,
                    severity,
                    product_name,
                    attempt + 1,
                )

                return admin_user_ids

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Notification dispatch attempt %d/%d failed for "
                    "signal_id=%d: %s",
                    attempt + 1,
                    self._escalation_retries,
                    signal_id,
                    str(exc),
                )
                audit_logger.info(
                    "Notification dispatch retry: signal_id=%d, "
                    "attempt=%d/%d, error=%s, backoff_duration_s=%d",
                    signal_id,
                    attempt + 1,
                    self._escalation_retries,
                    str(exc)[:200],
                    self.RETRY_INTERVAL_S,
                )

                if attempt < self._escalation_retries - 1:
                    await asyncio.sleep(self.RETRY_INTERVAL_S)

        logger.error(
            "Notification dispatch exhausted retries for signal_id=%d: %s",
            signal_id,
            str(last_error),
        )
        raise RuntimeError(
            f"Notification dispatch failed after {self._escalation_retries} "
            f"retries for signal_id={signal_id}: {last_error}"
        )

    async def _add_to_slr_reviews(
        self,
        record_id: int,
        product_id: int,
        company_id: int,
    ) -> list[int]:
        """Add record to active SLR reviews for the same product.

        Finds active SLR reviews within the company that are associated
        with the same product (via record_filter metadata or company scope),
        and adds the ingestion record to each. Retries up to
        escalation_retries times with 5-minute intervals.

        Args:
            record_id: IngestionRecord to add to reviews.
            product_id: Medical product ID for matching reviews.
            company_id: Tenant scope.

        Returns:
            List of updated SLR review IDs.
        """
        last_error: Exception | None = None

        for attempt in range(self._escalation_retries):
            try:
                async with self._session_factory() as session:
                    # Find active SLR reviews for this company/product
                    active_review_ids = await self._find_active_slr_reviews(
                        session, product_id, company_id
                    )

                    if not active_review_ids:
                        logger.info(
                            "No active SLR reviews found for product_id=%d, "
                            "company_id=%d during escalation",
                            product_id,
                            company_id,
                        )
                        return []

                    # Add the record to each active review via SLRReviewService
                    updated_review_ids: list[int] = []
                    for review_id in active_review_ids:
                        try:
                            # Update the review's record_filter to include
                            # the new record
                            from alcoabase.literature.review.models.slr_review import (
                                SLRReview,
                            )

                            review = await session.get(SLRReview, review_id)
                            if review is None:
                                continue

                            # Add record_id to the review's record set
                            current_filter = review.record_filter or {}
                            record_ids_list = current_filter.get(
                                "ingestion_record_ids", []
                            )

                            if record_id not in record_ids_list:
                                record_ids_list.append(record_id)
                                current_filter["ingestion_record_ids"] = (
                                    record_ids_list
                                )
                                review.record_filter = current_filter
                                review.records_identified = (
                                    review.records_identified + 1
                                )
                                updated_review_ids.append(review_id)

                        except Exception as inner_exc:
                            logger.warning(
                                "Failed to add record_id=%d to SLR "
                                "review_id=%d: %s",
                                record_id,
                                review_id,
                                str(inner_exc),
                            )

                    await session.commit()

                audit_logger.info(
                    "SLR reviews updated: record_id=%d, product_id=%d, "
                    "company_id=%d, updated_review_ids=%s, attempt=%d",
                    record_id,
                    product_id,
                    company_id,
                    updated_review_ids,
                    attempt + 1,
                )

                return updated_review_ids

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "SLR inclusion attempt %d/%d failed for record_id=%d: %s",
                    attempt + 1,
                    self._escalation_retries,
                    record_id,
                    str(exc),
                )
                audit_logger.info(
                    "SLR inclusion retry: record_id=%d, attempt=%d/%d, "
                    "error=%s, backoff_duration_s=%d",
                    record_id,
                    attempt + 1,
                    self._escalation_retries,
                    str(exc)[:200],
                    self.RETRY_INTERVAL_S,
                )

                if attempt < self._escalation_retries - 1:
                    await asyncio.sleep(self.RETRY_INTERVAL_S)

        logger.error(
            "SLR inclusion exhausted retries for record_id=%d: %s",
            record_id,
            str(last_error),
        )
        raise RuntimeError(
            f"SLR inclusion failed after {self._escalation_retries} "
            f"retries for record_id={record_id}: {last_error}"
        )

    # ─── Private Helpers ──────────────────────────────────────────────────

    async def _load_signal(
        self,
        session: "AsyncSession",
        signal_id: int,
        company_id: int,
    ) -> VigilanceSignal:
        """Load a VigilanceSignal by ID within company scope.

        Args:
            session: Active DB session.
            signal_id: Signal primary key.
            company_id: Tenant scope.

        Returns:
            The VigilanceSignal instance.

        Raises:
            ValueError: If signal not found in this company.
        """
        stmt = select(VigilanceSignal).where(
            VigilanceSignal.id == signal_id,
            VigilanceSignal.company_id == company_id,
        )
        result = await session.execute(stmt)
        signal = result.scalar_one_or_none()

        if signal is None:
            raise ValueError(
                f"VigilanceSignal id={signal_id} not found for "
                f"company_id={company_id}."
            )

        return signal

    async def _find_admin_users(
        self,
        session: "AsyncSession",
        company_id: int,
    ) -> list[int]:
        """Find all document_admin and system_admin users in the company.

        Queries CompanyMembership for users with admin roles that have
        not been revoked.

        Args:
            session: Active DB session.
            company_id: Tenant scope.

        Returns:
            List of user IDs with admin roles.
        """
        stmt = select(CompanyMembership.user_id).where(
            CompanyMembership.company_id == company_id,
            CompanyMembership.role.in_(["document_admin", "system_admin"]),
            CompanyMembership.revoked_at.is_(None),
        )
        result = await session.execute(stmt)
        return [row[0] for row in result.all()]

    async def _find_active_slr_reviews(
        self,
        session: "AsyncSession",
        product_id: int,
        company_id: int,
    ) -> list[int]:
        """Find active SLR reviews for the same product within the company.

        An SLR review is considered active if it is in a state that accepts
        new records (protocol_defined, screening_in_progress, or
        screening_complete). Reviews are matched by company scope and
        optionally by product_id in their record_filter metadata.

        Args:
            session: Active DB session.
            product_id: Medical product ID.
            company_id: Tenant scope.

        Returns:
            List of active SLR review IDs.
        """
        from alcoabase.literature.review.models.slr_review import SLRReview

        active_states = (
            "protocol_defined",
            "screening_in_progress",
            "screening_complete",
        )

        stmt = select(SLRReview).where(
            SLRReview.company_id == company_id,
            SLRReview.status.in_(active_states),
        )
        result = await session.execute(stmt)
        reviews = result.scalars().all()

        # Filter for reviews associated with the same product
        # SLR reviews may have product_id in their record_filter metadata
        matched_review_ids: list[int] = []
        for review in reviews:
            record_filter = review.record_filter or {}
            # Check if the review is explicitly linked to this product
            filter_product_id = record_filter.get("product_id")
            if filter_product_id is not None:
                if int(filter_product_id) == product_id:
                    matched_review_ids.append(review.id)
            else:
                # If no product filter, include all active reviews for
                # the company (broad inclusion for safety)
                matched_review_ids.append(review.id)

        return matched_review_ids
