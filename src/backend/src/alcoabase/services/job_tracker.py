"""Job tracker service for async processing job management.

Provides job creation, status updates, progress tracking, and conflict
detection for long-running video alignment operations. Uses the
processing_jobs table to persist job state across requests.

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Section 5)
    - Requirements: 5.4, 5.8, 6.9, 7.8, 10.6, 10.7, 10.8
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.video import ProcessingJob

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Status of an async processing job."""

    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobConflictError(Exception):
    """Raised when a concurrent operation is detected for the same document+operation.

    Attributes:
        existing_job_id: The job_id of the already-running job.
        document_uuid: The document UUID that has a conflicting job.
        operation: The operation type that conflicts.
    """

    def __init__(
        self,
        existing_job_id: str,
        document_uuid: str,
        operation: str,
    ) -> None:
        self.existing_job_id = existing_job_id
        self.document_uuid = document_uuid
        self.operation = operation
        super().__init__(
            f"Operation '{operation}' is already in progress for document "
            f"'{document_uuid}' (job_id: {existing_job_id})"
        )


@dataclass
class JobState:
    """State of an async processing job.

    Attributes:
        job_id: UUID string identifying the job.
        document_uuid: Document UUID this job operates on.
        operation: Operation type (extract_frames, analyze_frames, etc.).
        status: Current job status.
        started_at: When the job was created.
        completed_at: When the job completed or failed (None if still processing).
        progress_percent: Completion percentage (0-100).
        estimated_duration_seconds: Estimated total duration in seconds.
        result_reference: Optional reference to result data location.
        error_message: Error details if job failed.
    """

    job_id: str
    document_uuid: str
    operation: str
    status: JobStatus
    started_at: datetime
    completed_at: datetime | None = None
    progress_percent: int = 0
    estimated_duration_seconds: int = 0
    result_reference: str | None = None
    error_message: str | None = None


class JobTracker:
    """Tracks async processing job states in PostgreSQL.

    Provides job creation, status updates, and conflict detection
    for concurrent operations on the same document. Uses SQLAlchemy
    async sessions passed per-call for database operations.

    Example:
        tracker = JobTracker()
        job = await tracker.create_job(session, "2024-00001", "extract_frames", 120)
        await tracker.update_progress(session, job.job_id, 50)
        await tracker.complete_job(session, job.job_id, "/results/frames")
    """

    def __init__(self) -> None:
        """Initialize the JobTracker."""

    async def create_job(
        self,
        session: AsyncSession,
        document_uuid: str,
        operation: str,
        estimated_duration_seconds: int = 0,
        company_id: int = 0,
    ) -> JobState:
        """Create a new processing job, checking for conflicts.

        Generates a UUID job_id, verifies no active (PROCESSING) job exists
        for the same document+operation combination, and inserts a new record
        into the processing_jobs table.

        Args:
            session: Active async database session.
            document_uuid: Document UUID this job operates on.
            operation: Operation type (e.g., "extract_frames", "analyze_frames").
            estimated_duration_seconds: Estimated total duration in seconds.
            company_id: Tenant company ID for scoping.

        Returns:
            JobState representing the newly created job.

        Raises:
            JobConflictError: If a job for the same document+operation is
                already in PROCESSING state.
        """
        # Check for existing active job with same document_uuid + operation
        existing_job_id = await self.has_active_job(
            session, document_uuid, operation
        )
        if existing_job_id is not None:
            raise JobConflictError(
                existing_job_id=existing_job_id,
                document_uuid=document_uuid,
                operation=operation,
            )

        # Generate new job_id
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Look up document_id from document_uuid
        from alcoabase.models.document import Document

        doc_result = await session.execute(
            select(Document.id).where(Document.document_uuid == document_uuid)
        )
        document_id = doc_result.scalar_one_or_none()
        if document_id is None:
            # Use 0 as fallback if document not found (allows testing without full DB)
            document_id = 0

        # Create the processing job record
        job_record = ProcessingJob(
            job_id=job_id,
            document_id=document_id,
            operation=operation,
            status=JobStatus.PROCESSING.value,
            progress_percent=0,
            estimated_duration_seconds=estimated_duration_seconds,
            started_at=now,
            company_id=company_id,
        )
        session.add(job_record)
        await session.flush()

        logger.info(
            "Created job %s for document %s operation %s",
            job_id,
            document_uuid,
            operation,
        )

        return JobState(
            job_id=job_id,
            document_uuid=document_uuid,
            operation=operation,
            status=JobStatus.PROCESSING,
            started_at=now,
            estimated_duration_seconds=estimated_duration_seconds,
        )

    async def update_progress(
        self,
        session: AsyncSession,
        job_id: str,
        progress_percent: int,
    ) -> None:
        """Update the progress percentage for a job.

        Args:
            session: Active async database session.
            job_id: UUID string of the job to update.
            progress_percent: New progress percentage (0-100).
        """
        progress_percent = max(0, min(100, progress_percent))

        await session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.job_id == job_id)
            .values(progress_percent=progress_percent)
        )
        await session.flush()

        logger.debug("Job %s progress updated to %d%%", job_id, progress_percent)

    async def complete_job(
        self,
        session: AsyncSession,
        job_id: str,
        result_reference: str | None = None,
    ) -> None:
        """Mark a job as completed.

        Sets the status to "completed", records the completion timestamp,
        sets progress to 100%, and optionally stores a result reference.

        Args:
            session: Active async database session.
            job_id: UUID string of the job to complete.
            result_reference: Optional reference to result data location.
        """
        now = datetime.now(timezone.utc)

        await session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.job_id == job_id)
            .values(
                status=JobStatus.COMPLETED.value,
                completed_at=now,
                progress_percent=100,
                result_reference=result_reference,
            )
        )
        await session.flush()

        logger.info("Job %s completed", job_id)

    async def fail_job(
        self,
        session: AsyncSession,
        job_id: str,
        error_message: str,
    ) -> None:
        """Mark a job as failed.

        Sets the status to "failed", records the completion timestamp,
        and stores the error message.

        Args:
            session: Active async database session.
            job_id: UUID string of the job to mark as failed.
            error_message: Description of what went wrong.
        """
        now = datetime.now(timezone.utc)

        await session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.job_id == job_id)
            .values(
                status=JobStatus.FAILED.value,
                completed_at=now,
                error_message=error_message,
            )
        )
        await session.flush()

        logger.warning("Job %s failed: %s", job_id, error_message)

    async def get_job(
        self,
        session: AsyncSession,
        job_id: str,
    ) -> JobState | None:
        """Retrieve job state by job_id.

        Args:
            session: Active async database session.
            job_id: UUID string of the job to retrieve.

        Returns:
            JobState if found, None otherwise.
        """
        result = await session.execute(
            select(ProcessingJob).where(ProcessingJob.job_id == job_id)
        )
        job_record = result.scalar_one_or_none()

        if job_record is None:
            return None

        # Resolve document_uuid from document_id
        from alcoabase.models.document import Document

        doc_result = await session.execute(
            select(Document.document_uuid).where(
                Document.id == job_record.document_id
            )
        )
        document_uuid = doc_result.scalar_one_or_none() or ""

        return JobState(
            job_id=job_record.job_id,
            document_uuid=document_uuid,
            operation=job_record.operation,
            status=JobStatus(job_record.status),
            started_at=job_record.started_at,
            completed_at=job_record.completed_at,
            progress_percent=job_record.progress_percent,
            estimated_duration_seconds=job_record.estimated_duration_seconds,
            result_reference=job_record.result_reference,
            error_message=job_record.error_message,
        )

    async def has_active_job(
        self,
        session: AsyncSession,
        document_uuid: str,
        operation: str,
    ) -> str | None:
        """Check if an active (PROCESSING) job exists for a document+operation.

        Args:
            session: Active async database session.
            document_uuid: Document UUID to check.
            operation: Operation type to check.

        Returns:
            The job_id of the active job if one exists, None otherwise.
        """
        from alcoabase.models.document import Document

        # Look up document_id from document_uuid
        doc_result = await session.execute(
            select(Document.id).where(Document.document_uuid == document_uuid)
        )
        document_id = doc_result.scalar_one_or_none()

        if document_id is None:
            return None

        # Check for active job
        result = await session.execute(
            select(ProcessingJob.job_id).where(
                ProcessingJob.document_id == document_id,
                ProcessingJob.operation == operation,
                ProcessingJob.status == JobStatus.PROCESSING.value,
            )
        )
        return result.scalar_one_or_none()
