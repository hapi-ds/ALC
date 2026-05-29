"""Traceability Alert Service for AI-Powered Traceability & Gap Discovery.

Creates and manages traceability alerts when impact reports affect documents
that are sources in existing traceability matrices. Handles stale link marking
for critical alerts and resolution workflows.

Integrates with the Impact Analysis Engine (5.5) via ImpactReport after_insert
events to automatically detect when requirement changes affect traceability.

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError

from alcoabase.models.impact_analysis import ImpactReport
from alcoabase.models.traceability import (
    StaleLinkMarker,
    TraceabilityAlert,
    TraceabilityMatrix,
)
from alcoabase.schemas.traceability import AlertFilters

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

# Severity ordering for sorting (lower value = higher priority)
_SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2}


class TraceabilityAlertService:
    """Service for managing traceability alerts and stale link markers.

    Creates alerts when impact reports affect traceability matrix sources,
    marks links as stale for critical alerts, and handles alert resolution
    with conditional stale marker clearing.

    Args:
        session_factory: SQLAlchemy async session factory for DB operations.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        """Initialize TraceabilityAlertService.

        Args:
            session_factory: Async session factory for database operations.
        """
        self._session_factory = session_factory

    async def create_alert(
        self,
        triggering_report_id: str,
        triggering_document_uuid: str,
        company_id: int,
    ) -> TraceabilityAlert | None:
        """Create a traceability alert for an impact report affecting matrices.

        Queries non-deleted matrices where source_document_uuids contains the
        triggering document, computes affected link count, determines severity
        from the impact report's highest finding severity, and persists the alert.

        Handles unique constraint violations gracefully (duplicate alert for
        same report + company). Handles database write failures by logging
        without propagating to the impact analysis job.

        Args:
            triggering_report_id: UUID of the ImpactReport that triggered this.
            triggering_document_uuid: UUID of the document that changed.
            company_id: Company ID for tenant scoping.

        Returns:
            The created TraceabilityAlert, or None if creation failed or was
            skipped (no affected matrices, duplicate, or DB error).
        """
        if self._session_factory is None:
            logger.error(
                "Cannot create alert: session_factory not configured"
            )
            return None

        try:
            async with self._session_factory() as session:
                # Find non-deleted matrices where the document is a source
                affected_matrices = await self._find_affected_matrices(
                    session, triggering_document_uuid, company_id
                )

                if not affected_matrices:
                    logger.debug(
                        "No affected matrices for document %s in company %d, "
                        "skipping alert creation",
                        triggering_document_uuid,
                        company_id,
                    )
                    return None

                # Compute affected link count across all affected matrices
                affected_link_count = self._compute_affected_link_count(
                    affected_matrices, triggering_document_uuid
                )

                # Determine alert severity from impact report's findings
                alert_severity = await self._determine_alert_severity(
                    session, triggering_report_id
                )

                # Build the alert record
                affected_matrix_ids = [m.matrix_id for m in affected_matrices]
                alert = TraceabilityAlert(
                    alert_id=str(uuid.uuid4()),
                    triggering_report_id=triggering_report_id,
                    affected_matrix_ids=affected_matrix_ids,
                    affected_link_count=affected_link_count,
                    alert_severity=alert_severity,
                    is_resolved=False,
                    company_id=company_id,
                )

                session.add(alert)

                try:
                    await session.commit()
                except IntegrityError:
                    # Unique constraint violation: alert already exists for
                    # this report + company combination
                    await session.rollback()
                    logger.info(
                        "Alert already exists for report %s in company %d, "
                        "skipping duplicate creation",
                        triggering_report_id,
                        company_id,
                    )
                    return None

                await session.refresh(alert)

                # Mark stale links for critical alerts (Requirement 9.4)
                if alert_severity == "critical":
                    await self.mark_stale_links(
                        alert, affected_matrices, triggering_document_uuid
                    )

                logger.info(
                    "Created traceability alert %s (severity=%s, "
                    "affected_matrices=%d, affected_links=%d) for report %s",
                    alert.alert_id,
                    alert_severity,
                    len(affected_matrix_ids),
                    affected_link_count,
                    triggering_report_id,
                )

                return alert

        except Exception as exc:
            # Requirement 9.7: log failure, do not propagate to impact
            # analysis job
            logger.error(
                "Failed to create traceability alert for report %s "
                "(document=%s, company=%d): %s",
                triggering_report_id,
                triggering_document_uuid,
                company_id,
                exc,
            )
            return None

    async def mark_stale_links(
        self,
        alert: TraceabilityAlert,
        affected_matrices: list[TraceabilityMatrix],
        triggering_document_uuid: str,
    ) -> int:
        """Mark links as stale for critical alerts.

        Creates StaleLinkMarker records for each traceability link originating
        from the changed document in the affected matrices. Only called for
        critical severity alerts.

        Args:
            alert: The TraceabilityAlert that triggered stale marking.
            affected_matrices: List of affected TraceabilityMatrix records.
            triggering_document_uuid: UUID of the document that changed.

        Returns:
            Number of stale link markers created.
        """
        if self._session_factory is None:
            logger.error(
                "Cannot mark stale links: session_factory not configured"
            )
            return 0

        markers_created = 0

        try:
            async with self._session_factory() as session:
                for matrix in affected_matrices:
                    # Find links originating from the changed document
                    links = matrix.traceability_links or []
                    for link in links:
                        if link.get("source_document_uuid") == triggering_document_uuid:
                            requirement_id = link.get("requirement_id", "")
                            marker = StaleLinkMarker(
                                matrix_id=matrix.matrix_id,
                                requirement_id=requirement_id,
                                stale_since=alert.created_at or datetime.now(timezone.utc),
                                stale_reason=(
                                    f"Requirement document {triggering_document_uuid} "
                                    f"changed (impact report: {alert.triggering_report_id})"
                                ),
                                triggering_report_id=alert.triggering_report_id,
                                is_cleared=False,
                                company_id=alert.company_id,
                            )
                            session.add(marker)
                            markers_created += 1

                if markers_created > 0:
                    try:
                        await session.commit()
                    except IntegrityError:
                        # Some markers may already exist (unique constraint),
                        # fall back to individual inserts
                        await session.rollback()
                        markers_created = await self._insert_markers_individually(
                            alert, affected_matrices, triggering_document_uuid
                        )

                logger.info(
                    "Created %d stale link markers for alert %s",
                    markers_created,
                    alert.alert_id,
                )

        except Exception as exc:
            logger.error(
                "Failed to mark stale links for alert %s: %s",
                alert.alert_id,
                exc,
            )
            markers_created = 0

        return markers_created

    async def _insert_markers_individually(
        self,
        alert: TraceabilityAlert,
        affected_matrices: list[TraceabilityMatrix],
        triggering_document_uuid: str,
    ) -> int:
        """Insert stale link markers one by one, skipping duplicates.

        Fallback when batch insert fails due to unique constraint violations.

        Args:
            alert: The TraceabilityAlert that triggered stale marking.
            affected_matrices: List of affected TraceabilityMatrix records.
            triggering_document_uuid: UUID of the document that changed.

        Returns:
            Number of markers successfully created.
        """
        markers_created = 0

        async with self._session_factory() as session:
            for matrix in affected_matrices:
                links = matrix.traceability_links or []
                for link in links:
                    if link.get("source_document_uuid") == triggering_document_uuid:
                        requirement_id = link.get("requirement_id", "")
                        marker = StaleLinkMarker(
                            matrix_id=matrix.matrix_id,
                            requirement_id=requirement_id,
                            stale_since=alert.created_at or datetime.now(timezone.utc),
                            stale_reason=(
                                f"Requirement document {triggering_document_uuid} "
                                f"changed (impact report: {alert.triggering_report_id})"
                            ),
                            triggering_report_id=alert.triggering_report_id,
                            is_cleared=False,
                            company_id=alert.company_id,
                        )
                        session.add(marker)
                        try:
                            await session.flush()
                            markers_created += 1
                        except IntegrityError:
                            await session.rollback()
                            # Re-open session state after rollback
                            continue

            if markers_created > 0:
                await session.commit()

        return markers_created

    async def resolve_alert(
        self,
        alert_id: str,
        user_id: int,
        resolution_action: str,
        resolution_note: str | None,
        company_id: int,
    ) -> tuple[TraceabilityAlert | None, int]:
        """Resolve a traceability alert.

        Marks the alert as resolved with the given action and note. Clears
        stale markers when resolution_action is "links_verified" or
        "matrix_regenerated". Does NOT clear markers for "no_action_needed".

        Args:
            alert_id: UUID of the alert to resolve.
            user_id: ID of the user resolving the alert.
            resolution_action: One of "matrix_regenerated", "links_verified",
                "no_action_needed".
            resolution_note: Optional note explaining the resolution.
            company_id: Company ID for tenant scoping.

        Returns:
            Tuple of (alert, status_code):
            - (alert, 200) on success
            - (None, 404) if alert not found or wrong company
            - (None, 409) if alert already resolved
        """
        if self._session_factory is None:
            logger.error(
                "Cannot resolve alert: session_factory not configured"
            )
            return None, 500

        async with self._session_factory() as session:
            # Find the alert scoped to company
            result = await session.execute(
                select(TraceabilityAlert).where(
                    TraceabilityAlert.alert_id == alert_id,
                    TraceabilityAlert.company_id == company_id,
                )
            )
            alert = result.scalar_one_or_none()

            if alert is None:
                return None, 404

            if alert.is_resolved:
                return None, 409

            # Mark as resolved
            now = datetime.now(timezone.utc)
            alert.is_resolved = True
            alert.resolved_at = now
            alert.resolved_by = user_id
            alert.resolution_action = resolution_action
            alert.resolution_note = resolution_note

            await session.commit()
            await session.refresh(alert)

            # Clear stale markers for qualifying resolution actions
            # Requirement 9.8: only "links_verified" and "matrix_regenerated"
            # clear markers; "no_action_needed" does NOT
            if resolution_action in ("links_verified", "matrix_regenerated"):
                await self.clear_stale_markers(alert)

            return alert, 200

    async def clear_stale_markers(
        self,
        alert: TraceabilityAlert,
    ) -> int:
        """Clear stale link markers associated with a resolved alert.

        Sets is_cleared=True and cleared_at to the current timestamp on all
        StaleLinkMarker records matching the alert's triggering_report_id.

        Only called when resolution_action is "links_verified" or
        "matrix_regenerated". NOT called for "no_action_needed".

        Args:
            alert: The resolved TraceabilityAlert whose markers to clear.

        Returns:
            Number of markers cleared.
        """
        if self._session_factory is None:
            logger.error(
                "Cannot clear stale markers: session_factory not configured"
            )
            return 0

        try:
            async with self._session_factory() as session:
                now = datetime.now(timezone.utc)

                result = await session.execute(
                    update(StaleLinkMarker)
                    .where(
                        StaleLinkMarker.triggering_report_id == alert.triggering_report_id,
                        StaleLinkMarker.company_id == alert.company_id,
                        StaleLinkMarker.is_cleared == False,  # noqa: E712
                    )
                    .values(
                        is_cleared=True,
                        cleared_at=now,
                    )
                )

                await session.commit()

                cleared_count = result.rowcount
                logger.info(
                    "Cleared %d stale link markers for alert %s "
                    "(action=%s)",
                    cleared_count,
                    alert.alert_id,
                    alert.resolution_action,
                )
                return cleared_count

        except Exception as exc:
            logger.error(
                "Failed to clear stale markers for alert %s: %s",
                alert.alert_id,
                exc,
            )
            return 0

    async def get_alerts(
        self,
        company_id: int,
        filters: AlertFilters | None = None,
    ) -> tuple[list[TraceabilityAlert], int]:
        """Get traceability alerts for a company.

        Returns unresolved alerts sorted by severity (critical first) then
        by created_at (newest first), with pagination support.

        Args:
            company_id: Company ID for tenant scoping.
            filters: Optional filter and pagination parameters.

        Returns:
            Tuple of (alerts_list, total_count).
        """
        if self._session_factory is None:
            logger.error(
                "Cannot get alerts: session_factory not configured"
            )
            return [], 0

        if filters is None:
            filters = AlertFilters()

        async with self._session_factory() as session:
            # Base query scoped to company
            base_query = select(TraceabilityAlert).where(
                TraceabilityAlert.company_id == company_id,
            )

            # Apply resolution filter (default: unresolved only)
            if filters.is_resolved is not None:
                base_query = base_query.where(
                    TraceabilityAlert.is_resolved == filters.is_resolved
                )

            # Apply severity filter
            if filters.alert_severity is not None:
                base_query = base_query.where(
                    TraceabilityAlert.alert_severity == filters.alert_severity
                )

            # Count total matching records
            count_query = select(func.count()).select_from(
                base_query.subquery()
            )
            total_count_result = await session.execute(count_query)
            total_count = total_count_result.scalar() or 0

            # Sort by severity (critical > major > minor) then created_at desc
            # Use CASE expression for severity ordering
            severity_order = case(
                (TraceabilityAlert.alert_severity == "critical", 0),
                (TraceabilityAlert.alert_severity == "major", 1),
                (TraceabilityAlert.alert_severity == "minor", 2),
                else_=3,
            )
            ordered_query = base_query.order_by(
                severity_order,
                TraceabilityAlert.created_at.desc(),
            )

            # Apply pagination
            paginated_query = ordered_query.offset(filters.offset).limit(
                filters.limit
            )

            result = await session.execute(paginated_query)
            alerts = list(result.scalars().all())

            return alerts, total_count

    # ─────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────

    async def _find_affected_matrices(
        self,
        session: AsyncSession,
        triggering_document_uuid: str,
        company_id: int,
    ) -> list[TraceabilityMatrix]:
        """Find non-deleted matrices where the document is a source.

        Queries TraceabilityMatrix records where source_document_uuids JSONB
        array contains the triggering_document_uuid and deleted_at is null.

        Args:
            session: Active async database session.
            triggering_document_uuid: UUID of the changed document.
            company_id: Company ID for tenant scoping.

        Returns:
            List of affected TraceabilityMatrix records.
        """
        # Use JSONB contains operator to check if the document UUID is in
        # the source_document_uuids array
        from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

        result = await session.execute(
            select(TraceabilityMatrix).where(
                TraceabilityMatrix.company_id == company_id,
                TraceabilityMatrix.deleted_at.is_(None),
                TraceabilityMatrix.source_document_uuids.op("@>")(
                    func.cast(
                        f'["{triggering_document_uuid}"]',
                        PG_JSONB,
                    )
                ),
            )
        )
        return list(result.scalars().all())

    def _compute_affected_link_count(
        self,
        affected_matrices: list[TraceabilityMatrix],
        triggering_document_uuid: str,
    ) -> int:
        """Compute the total number of links originating from the changed document.

        Counts traceability links across all affected matrices where the
        source_document_uuid matches the triggering document.

        Args:
            affected_matrices: List of affected TraceabilityMatrix records.
            triggering_document_uuid: UUID of the changed document.

        Returns:
            Total count of affected links.
        """
        count = 0
        for matrix in affected_matrices:
            links = matrix.traceability_links or []
            for link in links:
                if link.get("source_document_uuid") == triggering_document_uuid:
                    count += 1
        return count

    async def _determine_alert_severity(
        self,
        session: AsyncSession,
        triggering_report_id: str,
    ) -> str:
        """Determine alert severity from the impact report's highest finding severity.

        Looks at the gap_findings in the ImpactReport and returns the highest
        severity found. Falls back to "minor" if no findings or report not found.

        Severity precedence: critical > major > minor.

        Args:
            session: Active async database session.
            triggering_report_id: UUID of the ImpactReport.

        Returns:
            Alert severity string: "critical", "major", or "minor".
        """
        result = await session.execute(
            select(ImpactReport).where(
                ImpactReport.report_id == triggering_report_id,
            )
        )
        report = result.scalar_one_or_none()

        if report is None:
            logger.warning(
                "ImpactReport %s not found, defaulting to 'minor' severity",
                triggering_report_id,
            )
            return "minor"

        # Check gap_findings for highest severity
        highest_severity = "minor"
        gap_findings = report.gap_findings or []

        for finding in gap_findings:
            severity = finding.get("severity", "").lower()
            if severity == "critical":
                return "critical"  # Can't get higher, return immediately
            elif severity == "major":
                highest_severity = "major"

        # Also check affected_items for impact_severity
        affected_items = report.affected_items or []
        for item in affected_items:
            severity = item.get("impact_severity", "").lower()
            if severity == "critical":
                return "critical"
            elif severity == "major":
                highest_severity = "major"

        return highest_severity
