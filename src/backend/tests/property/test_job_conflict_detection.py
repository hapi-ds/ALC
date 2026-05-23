"""Property-based tests for concurrent operation conflict detection.

Tests Property 12: Concurrent operation conflict detection from the
multimodal-knowledge-base design document.

Property 12 validates that for any Video_Document that has a processing
job in "processing" state for a given operation type, a new request for
the same operation on the same document SHALL be rejected (JobConflictError
raised with existing job_id). If no active job exists (COMPLETED or FAILED),
no conflict occurs and a new job can be created.

**Validates: Requirements 5.8, 6.9, 7.8, 10.8**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 12)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/job_tracker.py
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Constants matching the specification
# ---------------------------------------------------------------------------

VALID_OPERATIONS: list[str] = [
    "extract_frames",
    "analyze_frames",
    "transcribe_audio",
    "align",
]


class JobStatus(str, Enum):
    """Status of an async processing job (mirrors job_tracker.JobStatus)."""

    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Pure data model for testing
# ---------------------------------------------------------------------------


@dataclass
class ExistingJob:
    """Represents an existing job in the system.

    Attributes:
        job_id: UUID string identifying the job.
        document_uuid: Document UUID this job operates on.
        operation: Operation type (extract_frames, analyze_frames, etc.).
        status: Current job status.
    """

    job_id: str
    document_uuid: str
    operation: str
    status: JobStatus


class JobConflictError(Exception):
    """Raised when a concurrent operation conflict is detected.

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


# ---------------------------------------------------------------------------
# Pure conflict detection logic under test
# ---------------------------------------------------------------------------


def detect_conflict(
    existing_jobs: list[ExistingJob],
    request_document_uuid: str,
    request_operation: str,
) -> tuple[bool, str | None]:
    """Detect if a new job request conflicts with existing active jobs.

    Implements the conflict detection logic from the JobTracker.create_job()
    method: checks if any existing job with status PROCESSING matches the
    same document_uuid AND operation combination.

    Args:
        existing_jobs: List of all existing jobs in the system.
        request_document_uuid: Document UUID for the new job request.
        request_operation: Operation type for the new job request.

    Returns:
        A tuple of (has_conflict, existing_job_id).
        If conflict detected, existing_job_id is the conflicting job's ID.
        If no conflict, existing_job_id is None.
    """
    for job in existing_jobs:
        if (
            job.document_uuid == request_document_uuid
            and job.operation == request_operation
            and job.status == JobStatus.PROCESSING
        ):
            return True, job.job_id
    return False, None


def create_job_or_conflict(
    existing_jobs: list[ExistingJob],
    request_document_uuid: str,
    request_operation: str,
) -> str:
    """Attempt to create a new job, raising JobConflictError on conflict.

    This mirrors the behavior of JobTracker.create_job(): it checks for
    active jobs with the same document+operation, raises JobConflictError
    if found, otherwise returns a new job_id.

    Args:
        existing_jobs: List of all existing jobs in the system.
        request_document_uuid: Document UUID for the new job request.
        request_operation: Operation type for the new job request.

    Returns:
        A new job_id string if no conflict exists.

    Raises:
        JobConflictError: If an active (PROCESSING) job exists for the
            same document+operation combination.
    """
    has_conflict, existing_job_id = detect_conflict(
        existing_jobs, request_document_uuid, request_operation
    )
    if has_conflict:
        raise JobConflictError(
            existing_job_id=existing_job_id,  # type: ignore[arg-type]
            document_uuid=request_document_uuid,
            operation=request_operation,
        )
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_document_uuid() -> st.SearchStrategy[str]:
    """Generate document UUID strings.

    Returns:
        Strategy producing UUID-like strings.
    """
    return st.uuids().map(str)


def st_operation() -> st.SearchStrategy[str]:
    """Generate valid operation types.

    Returns:
        Strategy producing one of the valid operation strings.
    """
    return st.sampled_from(VALID_OPERATIONS)


def st_job_status() -> st.SearchStrategy[JobStatus]:
    """Generate any job status.

    Returns:
        Strategy producing a JobStatus enum value.
    """
    return st.sampled_from(list(JobStatus))


def st_existing_job() -> st.SearchStrategy[ExistingJob]:
    """Generate a random existing job.

    Returns:
        Strategy producing an ExistingJob with random attributes.
    """
    return st.builds(
        ExistingJob,
        job_id=st.uuids().map(str),
        document_uuid=st_document_uuid(),
        operation=st_operation(),
        status=st_job_status(),
    )


def st_existing_jobs_list() -> st.SearchStrategy[list[ExistingJob]]:
    """Generate a list of existing jobs (0-10 jobs).

    Returns:
        Strategy producing a list of ExistingJob instances.
    """
    return st.lists(st_existing_job(), min_size=0, max_size=10)


# ---------------------------------------------------------------------------
# Property 12: Concurrent operation conflict detection
# ---------------------------------------------------------------------------


# Feature: multimodal-knowledge-base, Property 12: Concurrent operation conflict detection
class TestConcurrentOperationConflictDetection:
    """Property tests for concurrent operation conflict detection.

    For any Video_Document that has a processing job in "processing" state
    for a given operation type, a new request for the same operation on the
    same document SHALL be rejected with the existing job_id. If no active
    job exists, the request succeeds.

    **Validates: Requirements 5.8, 6.9, 7.8, 10.8**
    """

    @given(
        existing_jobs=st_existing_jobs_list(),
        request_document_uuid=st_document_uuid(),
        request_operation=st_operation(),
    )
    @settings(max_examples=300)
    def test_conflict_detected_iff_active_job_exists(
        self,
        existing_jobs: list[ExistingJob],
        request_document_uuid: str,
        request_operation: str,
    ) -> None:
        """Conflict is detected if and only if an active (PROCESSING) job
        exists for the same document+operation combination.

        **Validates: Requirements 5.8, 6.9, 7.8, 10.8**
        """
        # Determine expected outcome from spec
        expected_conflict = any(
            job.document_uuid == request_document_uuid
            and job.operation == request_operation
            and job.status == JobStatus.PROCESSING
            for job in existing_jobs
        )

        has_conflict, existing_job_id = detect_conflict(
            existing_jobs, request_document_uuid, request_operation
        )

        assert has_conflict == expected_conflict, (
            f"Expected conflict={expected_conflict} for "
            f"document_uuid='{request_document_uuid}', "
            f"operation='{request_operation}', "
            f"but got conflict={has_conflict}"
        )

        if expected_conflict:
            assert existing_job_id is not None
        else:
            assert existing_job_id is None

    @given(
        other_jobs=st_existing_jobs_list(),
        active_job_id=st.uuids().map(str),
        document_uuid=st_document_uuid(),
        operation=st_operation(),
    )
    @settings(max_examples=200)
    def test_active_job_always_causes_conflict(
        self,
        other_jobs: list[ExistingJob],
        active_job_id: str,
        document_uuid: str,
        operation: str,
    ) -> None:
        """When a PROCESSING job exists for the same document+operation,
        a new request for that combination always raises JobConflictError
        with the existing job_id.

        **Validates: Requirements 5.8, 6.9, 7.8, 10.8**
        """
        # Inject an active job for the target document+operation
        active_job = ExistingJob(
            job_id=active_job_id,
            document_uuid=document_uuid,
            operation=operation,
            status=JobStatus.PROCESSING,
        )
        all_jobs = other_jobs + [active_job]

        with pytest.raises(JobConflictError) as exc_info:
            create_job_or_conflict(all_jobs, document_uuid, operation)

        error = exc_info.value
        assert error.existing_job_id == active_job_id
        assert error.document_uuid == document_uuid
        assert error.operation == operation

    @given(
        document_uuid=st_document_uuid(),
        operation=st_operation(),
        completed_job_id=st.uuids().map(str),
    )
    @settings(max_examples=200)
    def test_completed_job_does_not_cause_conflict(
        self,
        document_uuid: str,
        operation: str,
        completed_job_id: str,
    ) -> None:
        """A COMPLETED job for the same document+operation does NOT
        cause a conflict. A new job can be created.

        **Validates: Requirements 5.8, 6.9, 7.8, 10.8**
        """
        existing_jobs = [
            ExistingJob(
                job_id=completed_job_id,
                document_uuid=document_uuid,
                operation=operation,
                status=JobStatus.COMPLETED,
            )
        ]

        # Should not raise - new job created successfully
        new_job_id = create_job_or_conflict(
            existing_jobs, document_uuid, operation
        )
        assert new_job_id is not None
        assert new_job_id != completed_job_id

    @given(
        document_uuid=st_document_uuid(),
        operation=st_operation(),
        failed_job_id=st.uuids().map(str),
    )
    @settings(max_examples=200)
    def test_failed_job_does_not_cause_conflict(
        self,
        document_uuid: str,
        operation: str,
        failed_job_id: str,
    ) -> None:
        """A FAILED job for the same document+operation does NOT
        cause a conflict. A new job can be created.

        **Validates: Requirements 5.8, 6.9, 7.8, 10.8**
        """
        existing_jobs = [
            ExistingJob(
                job_id=failed_job_id,
                document_uuid=document_uuid,
                operation=operation,
                status=JobStatus.FAILED,
            )
        ]

        # Should not raise - new job created successfully
        new_job_id = create_job_or_conflict(
            existing_jobs, document_uuid, operation
        )
        assert new_job_id is not None
        assert new_job_id != failed_job_id

    @given(
        document_uuid=st_document_uuid(),
        request_operation=st_operation(),
        other_operation=st_operation(),
        active_job_id=st.uuids().map(str),
    )
    @settings(max_examples=200)
    def test_different_operation_no_conflict(
        self,
        document_uuid: str,
        request_operation: str,
        other_operation: str,
        active_job_id: str,
    ) -> None:
        """An active (PROCESSING) job for a DIFFERENT operation on the
        same document does NOT cause a conflict for the requested operation.

        **Validates: Requirements 5.8, 6.9, 7.8, 10.8**
        """
        # Skip when operations happen to be the same
        if request_operation == other_operation:
            return

        existing_jobs = [
            ExistingJob(
                job_id=active_job_id,
                document_uuid=document_uuid,
                operation=other_operation,
                status=JobStatus.PROCESSING,
            )
        ]

        # Should not raise - different operation
        new_job_id = create_job_or_conflict(
            existing_jobs, document_uuid, request_operation
        )
        assert new_job_id is not None

    @given(
        request_document_uuid=st_document_uuid(),
        other_document_uuid=st_document_uuid(),
        operation=st_operation(),
        active_job_id=st.uuids().map(str),
    )
    @settings(max_examples=200)
    def test_different_document_no_conflict(
        self,
        request_document_uuid: str,
        other_document_uuid: str,
        operation: str,
        active_job_id: str,
    ) -> None:
        """An active (PROCESSING) job for the same operation on a
        DIFFERENT document does NOT cause a conflict.

        **Validates: Requirements 5.8, 6.9, 7.8, 10.8**
        """
        # Skip when UUIDs happen to be the same
        if request_document_uuid == other_document_uuid:
            return

        existing_jobs = [
            ExistingJob(
                job_id=active_job_id,
                document_uuid=other_document_uuid,
                operation=operation,
                status=JobStatus.PROCESSING,
            )
        ]

        # Should not raise - different document
        new_job_id = create_job_or_conflict(
            existing_jobs, request_document_uuid, operation
        )
        assert new_job_id is not None

    @given(
        existing_jobs=st_existing_jobs_list(),
        request_document_uuid=st_document_uuid(),
        request_operation=st_operation(),
    )
    @settings(max_examples=300)
    def test_conflict_error_includes_job_id(
        self,
        existing_jobs: list[ExistingJob],
        request_document_uuid: str,
        request_operation: str,
    ) -> None:
        """When a conflict is detected, the JobConflictError includes
        the existing job_id, document_uuid, and operation in its attributes.

        **Validates: Requirements 5.8, 6.9, 7.8, 10.8**
        """
        # Find if there's an expected conflict
        conflicting_job = None
        for job in existing_jobs:
            if (
                job.document_uuid == request_document_uuid
                and job.operation == request_operation
                and job.status == JobStatus.PROCESSING
            ):
                conflicting_job = job
                break

        if conflicting_job is not None:
            with pytest.raises(JobConflictError) as exc_info:
                create_job_or_conflict(
                    existing_jobs, request_document_uuid, request_operation
                )

            error = exc_info.value
            assert error.existing_job_id == conflicting_job.job_id
            assert error.document_uuid == request_document_uuid
            assert error.operation == request_operation
            # Verify the error message contains the job_id
            assert conflicting_job.job_id in str(error)
        else:
            # No conflict - should succeed
            new_job_id = create_job_or_conflict(
                existing_jobs, request_document_uuid, request_operation
            )
            assert new_job_id is not None
