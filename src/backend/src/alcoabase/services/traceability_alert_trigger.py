"""Event trigger for traceability alerts on ImpactReport creation.

Registers a SQLAlchemy `after_insert` listener on the ImpactReport model
that checks whether the triggering document is a source in any existing
non-deleted TraceabilityMatrix for the same company. If so, schedules
asynchronous alert creation via TraceabilityAlertService.

The trigger implements:
- Filtering: checks if triggering_document_uuid matches any source_document_uuid
  in existing non-deleted TraceabilityMatrices for the same company
- Graceful failure handling: logs errors without failing the impact analysis job
- Async scheduling: uses asyncio to run the async alert creation from the
  synchronous event handler context

References:
    - Requirements: 9.1, 9.5, 9.7
    - Design: Event Listener section in design.md
"""

from __future__ import annotations

import asyncio
import logging
import threading

from sqlalchemy import event, select
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.orm import Session

from alcoabase.models.impact_analysis import ImpactReport
from alcoabase.models.traceability import TraceabilityMatrix

logger = logging.getLogger(__name__)


def _has_affected_matrices(
    session: Session,
    triggering_document_uuid: str,
    company_id: int,
) -> bool:
    """Check if the triggering document is a source in any non-deleted matrix.

    Uses a synchronous session (from the event handler context) to query
    TraceabilityMatrix records where source_document_uuids contains the
    triggering document UUID and deleted_at is null.

    Args:
        session: The synchronous SQLAlchemy session from the event context.
        triggering_document_uuid: UUID of the document that triggered analysis.
        company_id: Company ID for tenant scoping.

    Returns:
        True if at least one affected matrix exists, False otherwise.
    """
    from sqlalchemy import func

    result = session.execute(
        select(TraceabilityMatrix.id).where(
            TraceabilityMatrix.company_id == company_id,
            TraceabilityMatrix.deleted_at.is_(None),
            TraceabilityMatrix.source_document_uuids.op("@>")(
                func.cast(
                    f'["{triggering_document_uuid}"]',
                    PG_JSONB,
                )
            ),
        ).limit(1)
    )
    return result.first() is not None


def _schedule_alert_creation(
    triggering_report_id: str,
    triggering_document_uuid: str,
    company_id: int,
) -> None:
    """Schedule async alert creation in a background thread.

    Since SQLAlchemy event listeners are synchronous, we schedule the
    async TraceabilityAlertService.create_alert call in a new thread
    with its own event loop. This ensures the alert is created within
    30 seconds of the event (Requirement 9.1) without blocking the
    current transaction.

    All failures are caught and logged without propagating to the
    impact analysis job (Requirement 9.7).

    Args:
        triggering_report_id: UUID of the ImpactReport that triggered this.
        triggering_document_uuid: UUID of the document that changed.
        company_id: Company ID for tenant scoping.
    """

    def _run_alert_creation() -> None:
        """Run the async alert creation in a new event loop."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    _create_alert_async(
                        triggering_report_id,
                        triggering_document_uuid,
                        company_id,
                    )
                )
            finally:
                loop.close()
        except Exception as exc:
            # Requirement 9.7: log failure, do not propagate
            logger.error(
                "Background alert creation thread failed for report %s "
                "(document=%s, company=%d): %s",
                triggering_report_id,
                triggering_document_uuid,
                company_id,
                exc,
            )

    thread = threading.Thread(
        target=_run_alert_creation,
        name=f"traceability-alert-{triggering_report_id[:8]}",
        daemon=True,
    )
    thread.start()

    logger.debug(
        "Scheduled traceability alert creation for report %s "
        "(document=%s, company=%d)",
        triggering_report_id,
        triggering_document_uuid,
        company_id,
    )


async def _create_alert_async(
    triggering_report_id: str,
    triggering_document_uuid: str,
    company_id: int,
) -> None:
    """Create a traceability alert asynchronously.

    Instantiates a TraceabilityAlertService with a fresh session factory
    and calls create_alert. All exceptions are caught and logged.

    Args:
        triggering_report_id: UUID of the ImpactReport that triggered this.
        triggering_document_uuid: UUID of the document that changed.
        company_id: Company ID for tenant scoping.
    """
    try:
        from sqlalchemy.ext.asyncio import (
            AsyncSession,
            async_sessionmaker,
            create_async_engine,
        )

        from alcoabase.config import get_settings
        from alcoabase.services.traceability_alert import (
            TraceabilityAlertService,
        )

        settings = get_settings()
        engine = create_async_engine(
            settings.database_url,
            pool_size=2,
            max_overflow=3,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        try:
            service = TraceabilityAlertService(session_factory=session_factory)
            alert = await service.create_alert(
                triggering_report_id=triggering_report_id,
                triggering_document_uuid=triggering_document_uuid,
                company_id=company_id,
            )

            if alert is not None:
                logger.info(
                    "Traceability alert %s created successfully for report %s",
                    alert.alert_id,
                    triggering_report_id,
                )
            else:
                logger.debug(
                    "No traceability alert created for report %s "
                    "(no affected matrices or duplicate)",
                    triggering_report_id,
                )
        finally:
            await engine.dispose()

    except Exception as exc:
        # Requirement 9.7: log failure, do not propagate
        logger.error(
            "Failed to create traceability alert for report %s "
            "(document=%s, company=%d): %s",
            triggering_report_id,
            triggering_document_uuid,
            company_id,
            exc,
        )


def _on_impact_report_after_insert(
    mapper,  # noqa: ANN001
    connection,  # noqa: ANN001
    target: ImpactReport,
) -> None:
    """SQLAlchemy after_insert event handler for ImpactReport.

    Fires when a new ImpactReport row is inserted. Checks if the
    triggering document is a source in any existing non-deleted
    TraceabilityMatrix for the same company, and if so, schedules
    async alert creation.

    This handler MUST NOT raise exceptions — any failure would cause
    the impact analysis job to fail (Requirement 9.7).

    Args:
        mapper: The SQLAlchemy mapper for ImpactReport.
        connection: The database connection used for the INSERT.
        target: The newly inserted ImpactReport instance.
    """
    try:
        # Use a synchronous session bound to the current connection for queries
        session = Session(bind=connection)

        try:
            triggering_document_uuid = target.triggering_document_uuid
            company_id = target.company_id
            report_id = target.report_id

            if not triggering_document_uuid or not company_id or not report_id:
                logger.warning(
                    "ImpactReport inserted with missing fields "
                    "(document_uuid=%s, company_id=%s, report_id=%s), "
                    "skipping traceability alert check",
                    triggering_document_uuid,
                    company_id,
                    report_id,
                )
                return

            # Requirement 9.5: Check if the triggering document is a source
            # in any existing non-deleted TraceabilityMatrix
            if not _has_affected_matrices(
                session, triggering_document_uuid, company_id
            ):
                logger.debug(
                    "No affected traceability matrices for document %s "
                    "in company %d, skipping alert creation",
                    triggering_document_uuid,
                    company_id,
                )
                return

            # Schedule async alert creation in a background thread
            # Requirement 9.1: alert must be created within 30 seconds
            _schedule_alert_creation(
                triggering_report_id=report_id,
                triggering_document_uuid=triggering_document_uuid,
                company_id=company_id,
            )

        finally:
            session.close()

    except Exception:
        # Requirement 9.7: Catch-all to prevent the INSERT transaction
        # from failing due to trigger logic errors
        logger.exception(
            "Unexpected error in traceability alert trigger for "
            "ImpactReport report_id=%s",
            getattr(target, "report_id", "unknown"),
        )


def register_traceability_alert_trigger() -> None:
    """Register the after_insert event listener on ImpactReport.

    This function should be called once during application startup,
    after all models have been imported. It attaches the event handler
    that auto-triggers traceability alert creation when new impact
    reports are inserted.
    """
    event.listen(
        ImpactReport,
        "after_insert",
        _on_impact_report_after_insert,
    )
    logger.info(
        "Registered traceability alert trigger (after_insert on ImpactReport)."
    )
