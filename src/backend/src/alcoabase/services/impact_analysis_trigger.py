"""Event trigger for automatic impact analysis on document version creation.

Registers a SQLAlchemy `after_insert` listener on the DocumentVersion model
that conditionally enqueues the `analyze_change_impact` Celery task when a
new version is created for a non-Draft, non-CSV document.

The trigger implements:
- Filtering: skips Draft documents and CSV validation records
- Conflict detection: checks for existing "processing" jobs with staleness
  threshold of 600 seconds
- Graceful Celery broker failure handling: logs the error without crashing

References:
    - Requirements: 2.1, 2.2, 2.3, 2.5, 2.7, 2.9
    - Design: Event Listener section in design.md
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.video import ProcessingJob

logger = logging.getLogger(__name__)

# Staleness threshold in seconds: a processing job older than this is
# considered stale and eligible for replacement.
STALENESS_THRESHOLD_SECONDS = 600

# Operation name used for impact analysis jobs in the JobTracker.
IMPACT_ANALYSIS_OPERATION = "change_impact_analysis"


def _is_eligible_for_analysis(document: Document) -> bool:
    """Check if a document is eligible for automatic impact analysis.

    A document is excluded from auto-trigger if:
    - Its current_status is "Draft"
    - It is flagged as a CSV validation record

    Args:
        document: The Document instance associated with the new version.

    Returns:
        True if the document should trigger impact analysis, False otherwise.
    """
    if document.current_status == "Draft":
        logger.debug(
            "Skipping impact analysis for document %s: status is Draft",
            document.document_uuid,
        )
        return False

    if document.is_csv_validation_record:
        logger.debug(
            "Skipping impact analysis for document %s: is_csv_validation_record",
            document.document_uuid,
        )
        return False

    return True


def _has_active_non_stale_job(
    session: Session,
    document_id: int,
) -> str | None:
    """Check for an existing active (non-stale) processing job.

    A job is considered active if its status is "processing" and its
    started_at timestamp is within STALENESS_THRESHOLD_SECONDS of now.

    Args:
        session: The synchronous SQLAlchemy session from the event context.
        document_id: The document ID to check for active jobs.

    Returns:
        The job_id of the active non-stale job if one exists, None otherwise.
    """
    now = datetime.now(timezone.utc)

    result = session.execute(
        select(ProcessingJob.job_id, ProcessingJob.started_at).where(
            ProcessingJob.document_id == document_id,
            ProcessingJob.operation == IMPACT_ANALYSIS_OPERATION,
            ProcessingJob.status == "processing",
        )
    )
    row = result.first()

    if row is None:
        return None

    job_id, started_at = row

    # Ensure started_at is timezone-aware for comparison
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    elapsed_seconds = (now - started_at).total_seconds()

    if elapsed_seconds < STALENESS_THRESHOLD_SECONDS:
        logger.info(
            "Active non-stale job %s found for document_id=%d "
            "(elapsed=%.0fs < %ds threshold)",
            job_id,
            document_id,
            elapsed_seconds,
            STALENESS_THRESHOLD_SECONDS,
        )
        return job_id

    logger.info(
        "Stale job %s found for document_id=%d "
        "(elapsed=%.0fs >= %ds threshold), allowing new trigger",
        job_id,
        document_id,
        elapsed_seconds,
        STALENESS_THRESHOLD_SECONDS,
    )
    return None


def _on_document_version_after_insert(
    mapper,  # noqa: ANN001
    connection,  # noqa: ANN001
    target: DocumentVersion,
) -> None:
    """SQLAlchemy after_insert event handler for DocumentVersion.

    Fires when a new DocumentVersion row is inserted. Checks eligibility
    filters and conflict detection, then enqueues the impact analysis
    Celery task if appropriate.

    Args:
        mapper: The SQLAlchemy mapper for DocumentVersion.
        connection: The database connection used for the INSERT.
        target: The newly inserted DocumentVersion instance.
    """
    # Use a synchronous session bound to the current connection for queries
    session = Session(bind=connection)

    try:
        # Load the parent document to check eligibility
        document = session.get(Document, target.document_id)
        if document is None:
            logger.warning(
                "DocumentVersion %d inserted but parent document_id=%d not found",
                target.id,
                target.document_id,
            )
            return

        # Filter: skip Draft and CSV validation records
        if not _is_eligible_for_analysis(document):
            return

        # Conflict detection: check for active non-stale job
        existing_job_id = _has_active_non_stale_job(session, target.document_id)
        if existing_job_id is not None:
            logger.info(
                "Skipping auto-trigger for document %s version %d: "
                "active job %s already exists (409 equivalent)",
                document.document_uuid,
                target.id,
                existing_job_id,
            )
            return

        # Enqueue the Celery task
        _enqueue_impact_analysis(
            document_uuid=document.document_uuid,
            document_id=target.document_id,
            version_id=target.id,
            company_id=document.company_id,
            uploaded_by=target.uploaded_by,
        )

    except Exception:
        # Catch-all to prevent the INSERT transaction from failing
        # due to trigger logic errors
        logger.exception(
            "Unexpected error in impact analysis trigger for "
            "DocumentVersion id=%s, document_id=%s",
            getattr(target, "id", "unknown"),
            getattr(target, "document_id", "unknown"),
        )
    finally:
        session.close()


def _enqueue_impact_analysis(
    document_uuid: str,
    document_id: int,
    version_id: int,
    company_id: int,
    uploaded_by: int,
) -> None:
    """Enqueue the analyze_change_impact Celery task.

    Handles Celery broker unavailability gracefully by logging the
    failure without raising, so the document remains eligible for
    manual trigger.

    Args:
        document_uuid: The document's UUID string.
        document_id: The document's primary key.
        version_id: The new DocumentVersion's primary key.
        company_id: The company ID for tenant scoping.
        uploaded_by: The user ID who uploaded the new version.
    """
    try:
        from alcoabase.tasks.celery_app import celery_app

        celery_app.send_task(
            "alcoabase.tasks.impact_analysis_tasks.analyze_change_impact",
            kwargs={
                "document_uuid": document_uuid,
                "document_id": document_id,
                "version_id": version_id,
                "company_id": company_id,
                "uploaded_by": uploaded_by,
            },
            queue="ai_operations",
        )
        logger.info(
            "Enqueued impact analysis for document %s version_id=%d "
            "(company_id=%d)",
            document_uuid,
            version_id,
            company_id,
        )
    except Exception as exc:
        # Celery broker unavailable or task enqueue failure
        # Log and allow the document to remain eligible for manual trigger
        logger.error(
            "Failed to enqueue impact analysis for document %s "
            "version_id=%d: %s. Document remains eligible for manual trigger.",
            document_uuid,
            version_id,
            exc,
        )


def register_impact_analysis_trigger() -> None:
    """Register the after_insert event listener on DocumentVersion.

    This function should be called once during application startup,
    after all models have been imported. It attaches the event handler
    that auto-triggers impact analysis on new document versions.
    """
    event.listen(
        DocumentVersion,
        "after_insert",
        _on_document_version_after_insert,
    )
    logger.info(
        "Registered impact analysis trigger (after_insert on DocumentVersion)."
    )
