"""Anomaly Detection Service for audit trail monitoring.

This module provides the AnomalyDetectionService that periodically scans
the audit trail for suspicious patterns including backdated signatures,
workflow bypasses, bulk approvals, off-hours mutations, and rapid version
churn.

References:
    - Requirement 8: Anomaly Detection in Audit Logs
    - Requirement 8.1: Celery periodic task (every 15 minutes)
    - Requirement 8.2: Detection of anomaly types
    - Requirement 8.3: AnomalyAlert record creation with severity
    - Requirement 8.4: GET /api/compliance/anomalies endpoint
    - Requirement 8.5: PATCH resolve endpoint
    - Requirement 8.6: Company-scoped operations
    - Requirement 8.7: Deduplication within 24h detection window
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.anomaly import AnomalyAlert
from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.signature import SignatureRecord

logger = logging.getLogger(__name__)


class AnomalyDetectionService:
    """Monitors audit trail for suspicious patterns.

    Detects anomalies such as backdated signatures, workflow bypasses,
    bulk approvals, off-hours mutations, and rapid version churn.
    Implements deduplication to avoid duplicate alerts for the same event
    within a 24-hour window.

    Attributes:
        _session_factory: SQLAlchemy async session factory for DB access.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the AnomalyDetectionService.

        Args:
            session_factory: SQLAlchemy async session factory for DB access.
        """
        self._session_factory = session_factory

    async def scan_for_anomalies(
        self, company_id: int, hours: int = 24
    ) -> list[AnomalyAlert]:
        """Orchestrate all anomaly detection methods.

        Runs each detection method and collects all newly created alerts.
        Deduplication is handled within each detection method.

        Args:
            company_id: The company to scan anomalies for.
            hours: Number of hours to look back (default 24).

        Returns:
            List of newly created AnomalyAlert records.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        all_alerts: list[AnomalyAlert] = []

        detectors = [
            self._detect_backdated_signatures,
            self._detect_workflow_bypasses,
            self._detect_bulk_approvals,
            self._detect_off_hours_mutations,
            self._detect_rapid_version_churn,
        ]

        for detector in detectors:
            try:
                alerts = await detector(company_id, since)
                all_alerts.extend(alerts)
            except Exception:
                logger.exception(
                    "Error running anomaly detector %s for company %d",
                    detector.__name__,
                    company_id,
                )

        if all_alerts:
            logger.info(
                "Detected %d anomalies for company %d",
                len(all_alerts),
                company_id,
            )

        return all_alerts

    async def list_alerts(
        self,
        company_id: int,
        anomaly_type: str | None = None,
        severity: str | None = None,
        is_resolved: bool | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[AnomalyAlert]:
        """List anomaly alerts for a company with optional filters.

        Args:
            company_id: The company to list alerts for.
            anomaly_type: Filter by anomaly type (optional).
            severity: Filter by severity level (optional).
            is_resolved: Filter by resolution status (optional).
            date_from: Filter alerts detected on or after this date (optional).
            date_to: Filter alerts detected on or before this date (optional).

        Returns:
            List of AnomalyAlert records matching the filters.
        """
        async with self._session_factory() as session:
            stmt = select(AnomalyAlert).where(
                AnomalyAlert.company_id == company_id
            )

            if anomaly_type is not None:
                stmt = stmt.where(AnomalyAlert.anomaly_type == anomaly_type)
            if severity is not None:
                stmt = stmt.where(AnomalyAlert.severity == severity)
            if is_resolved is not None:
                stmt = stmt.where(AnomalyAlert.is_resolved == is_resolved)
            if date_from is not None:
                stmt = stmt.where(AnomalyAlert.detected_at >= date_from)
            if date_to is not None:
                stmt = stmt.where(AnomalyAlert.detected_at <= date_to)

            stmt = stmt.order_by(AnomalyAlert.detected_at.desc())

            result = await session.execute(stmt)
            alerts = list(result.scalars().all())
            for alert in alerts:
                session.expunge(alert)
            return alerts

    async def resolve_alert(
        self, anomaly_id: int, resolution_note: str, company_id: int
    ) -> AnomalyAlert:
        """Resolve an anomaly alert with a resolution note.

        Args:
            anomaly_id: The alert primary key.
            resolution_note: Explanation of how the anomaly was resolved.
            company_id: Company scope for multi-tenancy.

        Returns:
            The updated AnomalyAlert record.

        Raises:
            ValueError: If the alert is not found or doesn't belong to
                the specified company.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(AnomalyAlert).where(
                    AnomalyAlert.id == anomaly_id,
                    AnomalyAlert.company_id == company_id,
                )
            )
            alert = result.scalar_one_or_none()

            if alert is None:
                raise ValueError(
                    f"Anomaly alert {anomaly_id} not found for company {company_id}"
                )

            alert.is_resolved = True
            alert.resolved_at = datetime.now(timezone.utc)
            alert.resolution_note = resolution_note

            await session.commit()
            await session.refresh(alert)
            session.expunge(alert)

        logger.info(
            "Resolved anomaly alert id=%d for company %d",
            anomaly_id,
            company_id,
        )
        return alert

    async def _detect_backdated_signatures(
        self, company_id: int, since: datetime
    ) -> list[AnomalyAlert]:
        """Detect signatures where timestamp is >5 minutes before the audit log entry.

        A backdated signature occurs when signature.signed_at is more than
        5 minutes before the audit log entry timestamp (created_at), suggesting
        the signature was applied retroactively.

        Args:
            company_id: The company to scan.
            since: Only consider signatures created after this time.

        Returns:
            List of newly created AnomalyAlert records for backdated signatures.
        """
        alerts: list[AnomalyAlert] = []

        async with self._session_factory() as session:
            # Detect signatures where signed_at is more than 5 minutes before
            # the document version's uploaded_at (the audit log entry timestamp).
            # This detects signatures that claim to have been made before the
            # document version was uploaded, indicating backdating.
            backdated_stmt = (
                select(SignatureRecord, DocumentVersion.uploaded_at)
                .join(
                    DocumentVersion,
                    SignatureRecord.document_version_id == DocumentVersion.id,
                )
                .where(
                    SignatureRecord.company_id == company_id,
                    SignatureRecord.signed_at >= since,
                    SignatureRecord.signed_at
                    < DocumentVersion.uploaded_at - timedelta(minutes=5),
                )
            )

            result = await session.execute(backdated_stmt)
            rows = result.all()

            for row in rows:
                sig = row[0]
                uploaded_at = row[1]

                # Check deduplication
                if await self._is_duplicate(
                    session,
                    "backdated_signature",
                    sig.document_version_id,
                    sig.signer_user_id,
                ):
                    continue

                alert = AnomalyAlert(
                    company_id=company_id,
                    anomaly_type="backdated_signature",
                    severity="Critical",
                    description=(
                        f"Signature by user {sig.signer_user_id} on document "
                        f"version {sig.document_version_id} has timestamp "
                        f"{sig.signed_at.isoformat()} which is more than 5 "
                        f"minutes before the document was uploaded at "
                        f"{uploaded_at.isoformat()}"
                    ),
                    affected_document_id=None,
                    affected_user_id=sig.signer_user_id,
                    detected_at=datetime.now(timezone.utc),
                    is_resolved=False,
                )
                session.add(alert)
                alerts.append(alert)

            if alerts:
                await session.commit()
                for alert in alerts:
                    await session.refresh(alert)
                    session.expunge(alert)

        return alerts

    async def _detect_workflow_bypasses(
        self, company_id: int, since: datetime
    ) -> list[AnomalyAlert]:
        """Detect document status changes without corresponding workflow transitions.

        A workflow bypass occurs when a document's current_status changes
        but there is no matching record in workflow_transition_audits for
        that document within a reasonable time window.

        Args:
            company_id: The company to scan.
            since: Only consider changes after this time.

        Returns:
            List of newly created AnomalyAlert records for workflow bypasses.
        """
        alerts: list[AnomalyAlert] = []

        async with self._session_factory() as session:
            # Find documents that had status changes (via Continuum version table)
            # without corresponding workflow_transition_audits records.
            # Use raw SQL to query the documents_version table for status changes.
            bypass_query = text("""
                SELECT DISTINCT dv.id as doc_id, dv.current_status, dv.created_by
                FROM documents_version dv
                WHERE dv.company_id = :company_id
                  AND dv.transaction_id IN (
                      SELECT transaction_id FROM documents_version
                      WHERE company_id = :company_id
                  )
                  AND dv.current_status IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM workflow_transition_audits wta
                      WHERE wta.document_id = dv.id
                        AND wta.new_state = dv.current_status
                        AND wta.timestamp >= :since
                  )
                  AND dv.id IN (
                      SELECT id FROM documents
                      WHERE company_id = :company_id
                        AND current_status != 'Draft'
                  )
            """)

            try:
                result = await session.execute(
                    bypass_query,
                    {"company_id": company_id, "since": since},
                )
                rows = result.fetchall()
            except Exception:
                # Version table may not exist in test environments
                logger.debug(
                    "Could not query documents_version table for company %d",
                    company_id,
                )
                return alerts

            for row in rows:
                doc_id = row[0]
                status = row[1]
                user_id = row[2]

                # Check deduplication
                if await self._is_duplicate(
                    session, "workflow_bypass", doc_id, user_id
                ):
                    continue

                alert = AnomalyAlert(
                    company_id=company_id,
                    anomaly_type="workflow_bypass",
                    severity="Critical",
                    description=(
                        f"Document {doc_id} status changed to '{status}' "
                        f"without a corresponding workflow transition record"
                    ),
                    affected_document_id=doc_id,
                    affected_user_id=user_id,
                    detected_at=datetime.now(timezone.utc),
                    is_resolved=False,
                )
                session.add(alert)
                alerts.append(alert)

            if alerts:
                await session.commit()
                for alert in alerts:
                    await session.refresh(alert)
                    session.expunge(alert)

        return alerts

    async def _detect_bulk_approvals(
        self, company_id: int, since: datetime
    ) -> list[AnomalyAlert]:
        """Detect users who approved more than 10 documents in a 1-hour window.

        Args:
            company_id: The company to scan.
            since: Only consider approvals after this time.

        Returns:
            List of newly created AnomalyAlert records for bulk approvals.
        """
        alerts: list[AnomalyAlert] = []

        async with self._session_factory() as session:
            # Query workflow_transition_audits for approval transitions
            # grouped by user and 1-hour windows.
            # An "approval" is a transition to "Approved" state.
            bulk_query = text("""
                SELECT wta.user_id, COUNT(*) as approval_count,
                       MIN(wta.timestamp) as window_start,
                       MAX(wta.timestamp) as window_end
                FROM workflow_transition_audits wta
                JOIN documents d ON d.id = wta.document_id
                WHERE d.company_id = :company_id
                  AND wta.new_state = 'Approved'
                  AND wta.timestamp >= :since
                GROUP BY wta.user_id,
                         date_trunc('hour', wta.timestamp)
                HAVING COUNT(*) > 10
            """)

            try:
                result = await session.execute(
                    bulk_query,
                    {"company_id": company_id, "since": since},
                )
                rows = result.fetchall()
            except Exception:
                logger.debug(
                    "Could not query workflow_transition_audits for company %d",
                    company_id,
                )
                return alerts

            for row in rows:
                user_id = row[0]
                approval_count = row[1]

                # Check deduplication
                if await self._is_duplicate(
                    session, "bulk_approval", None, user_id
                ):
                    continue

                alert = AnomalyAlert(
                    company_id=company_id,
                    anomaly_type="bulk_approval",
                    severity="Major",
                    description=(
                        f"User {user_id} approved {approval_count} documents "
                        f"within a 1-hour window"
                    ),
                    affected_document_id=None,
                    affected_user_id=user_id,
                    detected_at=datetime.now(timezone.utc),
                    is_resolved=False,
                )
                session.add(alert)
                alerts.append(alert)

            if alerts:
                await session.commit()
                for alert in alerts:
                    await session.refresh(alert)
                    session.expunge(alert)

        return alerts

    async def _detect_off_hours_mutations(
        self, company_id: int, since: datetime
    ) -> list[AnomalyAlert]:
        """Detect mutating operations performed outside business hours (06:00-22:00).

        Args:
            company_id: The company to scan.
            since: Only consider mutations after this time.

        Returns:
            List of newly created AnomalyAlert records for off-hours mutations.
        """
        alerts: list[AnomalyAlert] = []

        async with self._session_factory() as session:
            # Find document versions uploaded outside business hours
            stmt = (
                select(DocumentVersion, Document.id.label("doc_id"))
                .join(Document, DocumentVersion.document_id == Document.id)
                .where(
                    Document.company_id == company_id,
                    DocumentVersion.uploaded_at >= since,
                    # Outside 06:00-22:00 UTC
                    func.extract("hour", DocumentVersion.uploaded_at).not_in(
                        list(range(6, 22))
                    ),
                )
            )

            result = await session.execute(stmt)
            rows = result.all()

            for row in rows:
                version = row[0]
                doc_id = row[1]

                # Check deduplication
                if await self._is_duplicate(
                    session, "off_hours_mutation", doc_id, version.uploaded_by
                ):
                    continue

                hour = version.uploaded_at.hour if version.uploaded_at else 0
                alert = AnomalyAlert(
                    company_id=company_id,
                    anomaly_type="off_hours_mutation",
                    severity="Minor",
                    description=(
                        f"Document {doc_id} version {version.id} was uploaded "
                        f"at {version.uploaded_at.isoformat()} (hour {hour:02d}:00) "
                        f"outside business hours (06:00-22:00)"
                    ),
                    affected_document_id=doc_id,
                    affected_user_id=version.uploaded_by,
                    detected_at=datetime.now(timezone.utc),
                    is_resolved=False,
                )
                session.add(alert)
                alerts.append(alert)

            if alerts:
                await session.commit()
                for alert in alerts:
                    await session.refresh(alert)
                    session.expunge(alert)

        return alerts

    async def _detect_rapid_version_churn(
        self, company_id: int, since: datetime
    ) -> list[AnomalyAlert]:
        """Detect documents with more than 5 versions created in a 1-hour window.

        Args:
            company_id: The company to scan.
            since: Only consider versions created after this time.

        Returns:
            List of newly created AnomalyAlert records for rapid version churn.
        """
        alerts: list[AnomalyAlert] = []

        async with self._session_factory() as session:
            # Find documents with >5 versions in any 1-hour window
            churn_query = text("""
                SELECT dv.document_id, COUNT(*) as version_count,
                       dv.uploaded_by
                FROM document_versions dv
                JOIN documents d ON d.id = dv.document_id
                WHERE d.company_id = :company_id
                  AND dv.uploaded_at >= :since
                GROUP BY dv.document_id,
                         date_trunc('hour', dv.uploaded_at),
                         dv.uploaded_by
                HAVING COUNT(*) > 5
            """)

            try:
                result = await session.execute(
                    churn_query,
                    {"company_id": company_id, "since": since},
                )
                rows = result.fetchall()
            except Exception:
                logger.debug(
                    "Could not query document_versions for company %d",
                    company_id,
                )
                return alerts

            for row in rows:
                doc_id = row[0]
                version_count = row[1]
                user_id = row[2]

                # Check deduplication
                if await self._is_duplicate(
                    session, "rapid_version_churn", doc_id, user_id
                ):
                    continue

                alert = AnomalyAlert(
                    company_id=company_id,
                    anomaly_type="rapid_version_churn",
                    severity="Minor",
                    description=(
                        f"Document {doc_id} had {version_count} versions "
                        f"created within a 1-hour window by user {user_id}"
                    ),
                    affected_document_id=doc_id,
                    affected_user_id=user_id,
                    detected_at=datetime.now(timezone.utc),
                    is_resolved=False,
                )
                session.add(alert)
                alerts.append(alert)

            if alerts:
                await session.commit()
                for alert in alerts:
                    await session.refresh(alert)
                    session.expunge(alert)

        return alerts

    async def _is_duplicate(
        self,
        session: AsyncSession,
        anomaly_type: str,
        affected_document_id: int | None,
        affected_user_id: int | None,
    ) -> bool:
        """Check if an anomaly alert already exists within the 24h dedup window.

        Deduplication is based on (anomaly_type, affected_document_id,
        affected_user_id) within the last 24 hours.

        Args:
            session: Active async DB session.
            anomaly_type: The type of anomaly.
            affected_document_id: The affected document ID (nullable).
            affected_user_id: The affected user ID (nullable).

        Returns:
            True if a duplicate exists within 24 hours, False otherwise.
        """
        dedup_window = datetime.now(timezone.utc) - timedelta(hours=24)

        conditions = [
            AnomalyAlert.anomaly_type == anomaly_type,
            AnomalyAlert.detected_at >= dedup_window,
        ]

        if affected_document_id is not None:
            conditions.append(
                AnomalyAlert.affected_document_id == affected_document_id
            )
        else:
            conditions.append(AnomalyAlert.affected_document_id.is_(None))

        if affected_user_id is not None:
            conditions.append(
                AnomalyAlert.affected_user_id == affected_user_id
            )
        else:
            conditions.append(AnomalyAlert.affected_user_id.is_(None))

        stmt = select(func.count()).select_from(AnomalyAlert).where(
            and_(*conditions)
        )

        result = await session.execute(stmt)
        count = result.scalar_one()
        return count > 0
