"""Celery tasks for AI-Powered Traceability & Gap Discovery.

Implements the async task layer for traceability matrix generation:
- generate_traceability_matrix: Full pipeline orchestration with monotonic
  progress updates, 600s hard timeout, and partial_success persistence.

These tasks run on the ai_operations queue and use asyncio.run() pattern
for async code (matching existing impact_analysis_tasks.py pattern).

References:
    - Requirements 11.1, 11.2, 11.4, 11.5, 11.8, 11.9, 11.10
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from celery.utils.log import get_task_logger

from alcoabase.tasks.celery_app import celery_app

logger = get_task_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HARD_TIMEOUT_SECONDS = 600
MIN_ESTIMATED_DURATION_SECONDS = 60
SECONDS_PER_DOCUMENT = 30

# Progress milestones for generate_traceability_matrix
PROGRESS_VALIDATION = 5
PROGRESS_REQ_EXTRACTION_START = 5
PROGRESS_REQ_EXTRACTION_END = 30
PROGRESS_TC_EXTRACTION_START = 30
PROGRESS_TC_EXTRACTION_END = 60
PROGRESS_LINK_ESTABLISHMENT_START = 60
PROGRESS_LINK_ESTABLISHMENT_END = 85
PROGRESS_ORPHAN_DETECTION_START = 85
PROGRESS_ORPHAN_DETECTION_END = 90
PROGRESS_METRICS_START = 90
PROGRESS_METRICS_END = 95
PROGRESS_PERSISTENCE_START = 95
PROGRESS_COMPLETE = 100


# ---------------------------------------------------------------------------
# Helper: Async session factory (same pattern as impact_analysis_tasks.py)
# ---------------------------------------------------------------------------


def _get_async_session_factory():
    """Get the async session factory for DB access in Celery tasks.

    Creates a standalone async engine and session factory since Celery
    workers don't share the FastAPI application's DB lifecycle.

    Returns:
        async_sessionmaker bound to a fresh async engine.
    """
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from alcoabase.config import get_settings

    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def _sanitize_error_message(exc: Exception) -> str:
    """Sanitize an exception into a safe error message without stack traces.

    Extracts the exception type and a truncated message, ensuring no
    internal stack traces or sensitive details are exposed.

    Args:
        exc: The exception to sanitize.

    Returns:
        A sanitized error message (max 1000 characters).
    """
    import re

    exc_type = type(exc).__name__
    exc_msg = str(exc)[:500]
    # Remove any newlines that might contain stack trace fragments
    exc_msg = exc_msg.replace("\n", " ").replace("\r", " ")
    # Remove stack trace patterns that could expose internals
    exc_msg = re.sub(r"Traceback \(most recent call last\):?", "", exc_msg)
    exc_msg = re.sub(r'File ".*?"', "", exc_msg)
    # Collapse multiple spaces left by removals
    exc_msg = re.sub(r" {2,}", " ", exc_msg).strip()
    sanitized = f"{exc_type}: {exc_msg}"
    return sanitized[:1000]


def _estimate_duration(document_count: int) -> int:
    """Estimate job duration based on total document count.

    Uses 30 seconds per document with a minimum of 60 seconds.

    Args:
        document_count: Total number of source + target documents.

    Returns:
        Estimated duration in seconds.
    """
    estimated = document_count * SECONDS_PER_DOCUMENT
    return max(estimated, MIN_ESTIMATED_DURATION_SECONDS)


# ---------------------------------------------------------------------------
# Task: generate_traceability_matrix
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    max_retries=0,
    time_limit=HARD_TIMEOUT_SECONDS,
    queue="ai_operations",
)
def generate_traceability_matrix(
    self,
    job_id: str,
    source_document_ids: list[int],
    target_document_ids: list[int],
    matrix_name: str,
    description: str | None,
    company_id: int,
    user_id: int,
) -> dict[str, Any]:
    """Execute the full traceability matrix generation pipeline.

    Orchestrates: validate → extract requirements → extract test cases →
    three-pass matching → orphan detection → coverage metrics → persist
    matrix → persist snapshot.

    Updates JobTracker progress monotonically:
        5% validation, 5-30% requirement extraction, 30-60% test case
        extraction, 60-85% link establishment, 85-90% orphan detection,
        90-95% metrics computation, 95-100% persistence.

    Enforces a 600s hard timeout with partial_success persistence and
    unprocessed_requirements metadata.

    Args:
        self: Celery task instance (bound).
        job_id: UUID of the pre-created job for progress tracking.
        source_document_ids: List of source document database IDs.
        target_document_ids: List of target document database IDs.
        matrix_name: Name for the generated matrix.
        description: Optional description for the matrix.
        company_id: Company ID for tenant scoping.
        user_id: ID of the requesting user.

    Returns:
        Dict with generation results (status, matrix_id, metrics).
    """
    try:
        result = asyncio.run(
            _generate_traceability_matrix_async(
                job_id=job_id,
                source_document_ids=source_document_ids,
                target_document_ids=target_document_ids,
                matrix_name=matrix_name,
                description=description,
                company_id=company_id,
                user_id=user_id,
            )
        )
        return result
    except Exception as exc:
        logger.error(
            "generate_traceability_matrix failed for job %s: %s",
            job_id,
            exc,
        )
        # Attempt to persist failure status
        try:
            asyncio.run(
                _handle_generation_failure(job_id=job_id, error=exc)
            )
        except Exception:
            pass
        return {
            "status": "failed",
            "job_id": job_id,
            "error": _sanitize_error_message(exc),
        }


async def _handle_generation_failure(
    job_id: str,
    error: Exception,
) -> None:
    """Handle generation failure by marking the job as failed.

    Sets job status to "failed" with a sanitized error message.
    Freezes progress_percent at the last reported value (does not
    update progress on failure).

    Args:
        job_id: UUID of the job to mark as failed.
        error: The exception that caused the failure.
    """
    from alcoabase.services.job_tracker import JobTracker

    session_factory = _get_async_session_factory()
    job_tracker = JobTracker()

    async with session_factory() as session:
        await job_tracker.fail_job(
            session, job_id, _sanitize_error_message(error)
        )
        await session.commit()


async def _generate_traceability_matrix_async(
    job_id: str,
    source_document_ids: list[int],
    target_document_ids: list[int],
    matrix_name: str,
    description: str | None,
    company_id: int,
    user_id: int,
) -> dict[str, Any]:
    """Async implementation of the full traceability matrix generation pipeline.

    Orchestrates the complete pipeline with monotonic progress updates:
    1. Validation (0% → 5%)
    2. Requirement extraction (5% → 30%)
    3. Test case extraction (30% → 60%)
    4. Link establishment via three-pass matching (60% → 85%)
    5. Orphan detection (85% → 90%)
    6. Coverage metrics computation (90% → 95%)
    7. Matrix and snapshot persistence (95% → 100%)

    Args:
        job_id: UUID of the pre-created job for progress tracking.
        source_document_ids: List of source document database IDs.
        target_document_ids: List of target document database IDs.
        matrix_name: Name for the generated matrix.
        description: Optional description for the matrix.
        company_id: Company ID for tenant scoping.
        user_id: ID of the requesting user.

    Returns:
        Dict with generation results.
    """
    from alcoabase.services.coverage_metrics import CoverageMetricsService
    from alcoabase.services.cross_reference import CrossReferenceService
    from alcoabase.services.job_tracker import JobTracker
    from alcoabase.services.orphan_detection import OrphanDetectionService
    from alcoabase.services.service_factory import (
        get_inference_client,
        get_knowledge_service,
    )
    from alcoabase.services.storage_service import StorageService
    from alcoabase.services.traceability_matrix import TraceabilityMatrixService

    session_factory = _get_async_session_factory()
    job_tracker = JobTracker()
    knowledge_service = get_knowledge_service()
    inference_client = get_inference_client()
    storage_service = StorageService()

    cross_reference_service = CrossReferenceService(
        session_factory=session_factory,
        knowledge_service=knowledge_service,
        storage_service=storage_service,
    )

    # Initialize the TraceabilityMatrixService with all dependencies
    matrix_service = TraceabilityMatrixService(
        knowledge_service=knowledge_service,
        inference_client=inference_client,
        agent_registry=None,  # Will use fallback if needed
        cross_reference_service=cross_reference_service,
        session_factory=session_factory,
        job_tracker=job_tracker,
    )

    start_time = time.monotonic()
    current_progress = 0

    # Helper to ensure monotonic progress updates
    async def _update_progress(target: int) -> None:
        nonlocal current_progress
        if target > current_progress:
            current_progress = target
            async with session_factory() as session:
                await job_tracker.update_progress(
                    session, job_id, current_progress
                )
                await session.commit()

    # Helper to check timeout
    def _check_timeout() -> bool:
        return (time.monotonic() - start_time) >= HARD_TIMEOUT_SECONDS

    try:
        # --- Step 1: Validation (→ 5%) ---
        await _update_progress(PROGRESS_VALIDATION)

        # Build a request-like object for the service
        request = _MatrixRequest(
            source_document_ids=source_document_ids,
            target_document_ids=target_document_ids,
            matrix_name=matrix_name,
            description=description,
        )

        if _check_timeout():
            raise TimeoutError(
                "Hard timeout exceeded during validation"
            )

        # --- Step 2: Requirement extraction (5% → 30%) ---
        # Build source document dicts for extraction
        source_docs = await _resolve_documents(
            session_factory, source_document_ids, company_id
        )
        await _update_progress(PROGRESS_REQ_EXTRACTION_START + 5)

        req_result = await matrix_service.extract_requirements(
            source_docs, company_id
        )

        if req_result.failed:
            raise _UnrecoverableError(
                req_result.failure_message
                or "Requirement extraction failed"
            )

        await _update_progress(PROGRESS_REQ_EXTRACTION_END)

        if _check_timeout():
            return await _persist_timeout_result(
                session_factory=session_factory,
                job_tracker=job_tracker,
                matrix_service=matrix_service,
                job_id=job_id,
                request=request,
                company_id=company_id,
                user_id=user_id,
                start_time=start_time,
                requirements=req_result.requirements,
                test_cases=[],
                links=[],
                unprocessed_reason="Timeout after requirement extraction",
            )

        # --- Step 3: Test case extraction (30% → 60%) ---
        target_docs = await _resolve_documents(
            session_factory, target_document_ids, company_id
        )
        await _update_progress(PROGRESS_TC_EXTRACTION_START + 5)

        tc_result = await matrix_service.extract_test_cases(
            target_docs, company_id
        )

        if tc_result.failed:
            raise _UnrecoverableError(
                tc_result.failure_message
                or "Test case extraction failed"
            )

        await _update_progress(PROGRESS_TC_EXTRACTION_END)

        if _check_timeout():
            return await _persist_timeout_result(
                session_factory=session_factory,
                job_tracker=job_tracker,
                matrix_service=matrix_service,
                job_id=job_id,
                request=request,
                company_id=company_id,
                user_id=user_id,
                start_time=start_time,
                requirements=req_result.requirements,
                test_cases=tc_result.test_cases,
                links=[],
                unprocessed_reason="Timeout after test case extraction",
            )

        # --- Step 4: Link establishment via three-pass matching (60% → 85%) ---
        await _update_progress(PROGRESS_LINK_ESTABLISHMENT_START)

        matching_result = await matrix_service.run_three_pass_matching(
            req_result.requirements, tc_result.test_cases, company_id
        )

        await _update_progress(PROGRESS_LINK_ESTABLISHMENT_END)

        if _check_timeout():
            return await _persist_timeout_result(
                session_factory=session_factory,
                job_tracker=job_tracker,
                matrix_service=matrix_service,
                job_id=job_id,
                request=request,
                company_id=company_id,
                user_id=user_id,
                start_time=start_time,
                requirements=req_result.requirements,
                test_cases=tc_result.test_cases,
                links=matching_result.links,
                unprocessed_reason="Timeout after link establishment",
            )

        # --- Step 5: Orphan detection (85% → 90%) ---
        await _update_progress(PROGRESS_ORPHAN_DETECTION_START)

        orphan_service = OrphanDetectionService(
            inference_client=inference_client,
            agent_registry=None,
        )

        orphan_reqs = await orphan_service.identify_orphan_requirements(
            req_result.requirements, matching_result.links
        )
        orphan_tcs = await orphan_service.identify_orphan_test_cases(
            tc_result.test_cases, matching_result.links
        )

        await _update_progress(PROGRESS_ORPHAN_DETECTION_END)

        if _check_timeout():
            return await _persist_timeout_result(
                session_factory=session_factory,
                job_tracker=job_tracker,
                matrix_service=matrix_service,
                job_id=job_id,
                request=request,
                company_id=company_id,
                user_id=user_id,
                start_time=start_time,
                requirements=req_result.requirements,
                test_cases=tc_result.test_cases,
                links=matching_result.links,
                unprocessed_reason="Timeout after orphan detection",
            )

        # --- Step 6: Coverage metrics computation (90% → 95%) ---
        await _update_progress(PROGRESS_METRICS_START)

        coverage_service = CoverageMetricsService(
            session_factory=session_factory,
        )

        coverage_metrics = coverage_service.compute_coverage_metrics(
            requirements=req_result.requirements,
            test_cases=tc_result.test_cases,
            links=matching_result.links,
            source_docs=source_docs,
            target_docs=target_docs,
        )

        await _update_progress(PROGRESS_METRICS_END)

        if _check_timeout():
            return await _persist_timeout_result(
                session_factory=session_factory,
                job_tracker=job_tracker,
                matrix_service=matrix_service,
                job_id=job_id,
                request=request,
                company_id=company_id,
                user_id=user_id,
                start_time=start_time,
                requirements=req_result.requirements,
                test_cases=tc_result.test_cases,
                links=matching_result.links,
                unprocessed_reason="Timeout after metrics computation",
            )

        # --- Step 7: Persist matrix and snapshot (95% → 100%) ---
        await _update_progress(PROGRESS_PERSISTENCE_START)

        # Delegate to the service's generate_matrix which handles
        # persistence with retries, parent_matrix_id resolution,
        # document version capture, and job completion
        matrix_result = await matrix_service.generate_matrix(
            job_id=job_id,
            request=request,
            company_id=company_id,
            user_id=user_id,
        )

        # Persist coverage snapshot for each source document
        source_uuids = (
            matrix_result.source_document_uuids
            if hasattr(matrix_result, "source_document_uuids")
            else [d["document_uuid"] for d in source_docs]
        )
        for source_uuid in source_uuids:
            try:
                await coverage_service.persist_coverage_snapshot(
                    matrix_id=matrix_result.matrix_id,
                    metrics=coverage_metrics,
                    source_document_uuid=source_uuid,
                    company_id=company_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to persist coverage snapshot for "
                    "document %s: %s",
                    source_uuid,
                    str(e),
                )

        await _update_progress(PROGRESS_COMPLETE)

        # Compute duration
        duration_ms = int((time.monotonic() - start_time) * 1000)

        logger.info(
            "Traceability matrix generation completed: job_id=%s, "
            "matrix_id=%s, links=%d, orphan_reqs=%d, orphan_tcs=%d, "
            "duration=%dms",
            job_id,
            matrix_result.matrix_id,
            len(matching_result.links),
            len(orphan_reqs),
            len(orphan_tcs),
            duration_ms,
        )

        return {
            "status": matrix_result.status,
            "job_id": job_id,
            "matrix_id": matrix_result.matrix_id,
            "total_requirements": len(req_result.requirements),
            "total_test_cases": len(tc_result.test_cases),
            "total_links": len(matching_result.links),
            "orphan_requirements_count": len(orphan_reqs),
            "orphan_test_cases_count": len(orphan_tcs),
            "coverage_metrics": coverage_metrics,
            "generation_duration_ms": duration_ms,
        }

    except TimeoutError:
        # Hard timeout: persist partial results
        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Determine what we have so far
        unprocessed_reqs = [
            req.requirement_id
            for req in req_result.requirements
        ] if "req_result" in dir() else []

        error_msg = (
            f"Matrix generation timeout after {HARD_TIMEOUT_SECONDS}s. "
            f"{len(unprocessed_reqs)} requirements may be unprocessed."
        )

        async with session_factory() as session:
            await job_tracker.complete_job(
                session, job_id, result_reference=None
            )
            await session.commit()

        logger.warning(
            "Traceability matrix generation timed out: job_id=%s, "
            "duration=%dms",
            job_id,
            duration_ms,
        )

        return {
            "status": "partial_success",
            "job_id": job_id,
            "generation_duration_ms": duration_ms,
            "unprocessed_requirements": unprocessed_reqs,
        }

    except _UnrecoverableError as exc:
        # Unrecoverable error: set job status "failed"
        error_msg = _sanitize_error_message(exc)
        duration_ms = int((time.monotonic() - start_time) * 1000)

        async with session_factory() as session:
            await job_tracker.fail_job(session, job_id, error_msg)
            await session.commit()

        logger.error(
            "Traceability matrix generation failed (unrecoverable): "
            "job_id=%s, error=%s",
            job_id,
            error_msg,
        )

        return {
            "status": "failed",
            "job_id": job_id,
            "error": error_msg,
            "generation_duration_ms": duration_ms,
        }

    except Exception as exc:
        # Unexpected error: set job status "failed", freeze progress
        error_msg = _sanitize_error_message(exc)
        duration_ms = int((time.monotonic() - start_time) * 1000)

        async with session_factory() as session:
            await job_tracker.fail_job(session, job_id, error_msg)
            await session.commit()

        logger.error(
            "Traceability matrix generation failed: job_id=%s, error=%s",
            job_id,
            error_msg,
        )

        return {
            "status": "failed",
            "job_id": job_id,
            "error": error_msg,
            "generation_duration_ms": duration_ms,
        }


# ---------------------------------------------------------------------------
# Helper: Resolve document UUIDs from IDs
# ---------------------------------------------------------------------------


async def _resolve_documents(
    session_factory,
    document_ids: list[int],
    company_id: int,
) -> list[dict[str, Any]]:
    """Resolve document database IDs to UUID-based dicts for extraction.

    Args:
        session_factory: Async session factory for DB access.
        document_ids: List of document database IDs.
        company_id: Company ID for tenant scoping.

    Returns:
        List of dicts with document_uuid and document_id keys.
    """
    from sqlalchemy import select

    from alcoabase.models.document import Document

    docs: list[dict[str, Any]] = []

    async with session_factory() as session:
        for doc_id in document_ids:
            result = await session.execute(
                select(Document.document_uuid).where(
                    Document.id == doc_id,
                    Document.company_id == company_id,
                )
            )
            doc_uuid = result.scalar_one_or_none()
            docs.append({
                "document_uuid": doc_uuid or f"doc-{doc_id}",
                "document_id": doc_id,
            })

    return docs


# ---------------------------------------------------------------------------
# Helper: Persist timeout result as partial_success
# ---------------------------------------------------------------------------


async def _persist_timeout_result(
    session_factory,
    job_tracker,
    matrix_service,
    job_id: str,
    request: "_MatrixRequest",
    company_id: int,
    user_id: int,
    start_time: float,
    requirements: list,
    test_cases: list,
    links: list,
    unprocessed_reason: str,
) -> dict[str, Any]:
    """Persist partial results when the 600s hard timeout is reached.

    Persists all links discovered so far and records unprocessed
    requirements in metadata. Marks the job as completed with
    partial_success status.

    Args:
        session_factory: Async session factory.
        job_tracker: JobTracker instance.
        matrix_service: TraceabilityMatrixService instance.
        job_id: UUID of the job.
        request: Matrix generation request.
        company_id: Company ID for tenant scoping.
        user_id: Requesting user ID.
        start_time: Monotonic start time.
        requirements: Requirements extracted so far.
        test_cases: Test cases extracted so far.
        links: Links discovered so far.
        unprocessed_reason: Reason for partial completion.

    Returns:
        Dict with partial_success results.
    """
    duration_ms = int((time.monotonic() - start_time) * 1000)

    # Attempt to persist via the service's partial_success method
    try:
        source_docs = await _resolve_documents(
            session_factory, request.source_document_ids, company_id
        )
        target_docs = await _resolve_documents(
            session_factory, request.target_document_ids, company_id
        )

        matrix_result = await matrix_service._persist_partial_success(
            job_id=job_id,
            request=request,
            source_docs=source_docs,
            target_docs=target_docs,
            source_document_versions=[],
            target_document_versions=[],
            links=links,
            requirements=requirements,
            test_cases=test_cases,
            company_id=company_id,
            user_id=user_id,
            start_time=start_time,
            unprocessed_reason=unprocessed_reason,
        )

        matrix_id = (
            matrix_result.matrix_id
            if hasattr(matrix_result, "matrix_id")
            else None
        )
    except Exception as e:
        logger.warning(
            "Failed to persist partial_success matrix: %s", str(e)
        )
        matrix_id = None
        # Still mark job as completed
        async with session_factory() as session:
            await job_tracker.complete_job(
                session, job_id, result_reference=None
            )
            await session.commit()

    # Collect unprocessed requirement IDs
    unprocessed_reqs = [
        req.requirement_id for req in requirements
    ] if requirements else []

    logger.warning(
        "Traceability matrix generation timed out: job_id=%s, "
        "reason=%s, duration=%dms",
        job_id,
        unprocessed_reason,
        duration_ms,
    )

    return {
        "status": "partial_success",
        "job_id": job_id,
        "matrix_id": matrix_id,
        "generation_duration_ms": duration_ms,
        "unprocessed_requirements": unprocessed_reqs,
        "unprocessed_reason": unprocessed_reason,
    }


# ---------------------------------------------------------------------------
# Internal: Request data class and exceptions
# ---------------------------------------------------------------------------


class _MatrixRequest:
    """Lightweight request object for passing to TraceabilityMatrixService.

    Mimics the GenerateMatrixRequest Pydantic schema interface without
    requiring the full schema import in the Celery worker context.

    Attributes:
        source_document_ids: List of source document database IDs.
        target_document_ids: List of target document database IDs.
        matrix_name: Name for the generated matrix.
        description: Optional description.
    """

    def __init__(
        self,
        source_document_ids: list[int],
        target_document_ids: list[int],
        matrix_name: str,
        description: str | None = None,
    ) -> None:
        self.source_document_ids = source_document_ids
        self.target_document_ids = target_document_ids
        self.matrix_name = matrix_name
        self.description = description


class _UnrecoverableError(Exception):
    """Raised when an unrecoverable error occurs during generation.

    Used to distinguish between timeout-based partial_success and
    hard failures that should mark the job as "failed".
    """

    pass
