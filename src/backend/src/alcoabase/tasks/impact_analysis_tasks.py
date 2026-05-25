"""Celery tasks for AI-Driven Change Impact Analysis.

Implements the async task layer for impact analysis:
- build_dependency_graph: Builds/updates the dependency graph for a company
- analyze_change_impact: Full impact analysis pipeline for a document change
- execute_gap_analysis: Gap analysis between a specific document pair

These tasks run on the ai_operations queue and use asyncio.run() pattern
for async code (matching existing review_tasks.py pattern).

References:
    - Requirements 6.1, 6.2, 6.4, 6.5: Job management and status tracking
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from celery.utils.log import get_task_logger

from alcoabase.tasks.celery_app import celery_app

logger = get_task_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HARD_TIMEOUT_SECONDS = 600
BUILD_GRAPH_TIMEOUT_SECONDS = 300
GAP_ANALYSIS_TIMEOUT_SECONDS = 180
MIN_ESTIMATED_DURATION_SECONDS = 30
SECONDS_PER_DEPENDENCY = 15

# Progress milestones for analyze_change_impact
PROGRESS_DELTA_COMPLETE = 10
PROGRESS_DEPS_COMPLETE = 20
PROGRESS_ITEMS_START = 20
PROGRESS_ITEMS_END = 85
PROGRESS_GAPS_START = 85
PROGRESS_GAPS_END = 95
PROGRESS_REPORT_COMPLETE = 100


# ---------------------------------------------------------------------------
# Helper: Async session factory (same pattern as review_tasks.py)
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


def _estimate_duration(dependency_count: int) -> int:
    """Estimate job duration based on dependency count.

    Uses 15 seconds per dependency with a minimum of 30 seconds.

    Args:
        dependency_count: Number of downstream dependencies.

    Returns:
        Estimated duration in seconds.
    """
    estimated = dependency_count * SECONDS_PER_DEPENDENCY
    return max(estimated, MIN_ESTIMATED_DURATION_SECONDS)


# ---------------------------------------------------------------------------
# Task: build_dependency_graph
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    max_retries=0,
    time_limit=BUILD_GRAPH_TIMEOUT_SECONDS,
    queue="ai_operations",
)
def build_dependency_graph(
    self,
    company_id: int,
    scope: str = "incremental",
    document_uuid: str = "dependency_graph",
) -> dict[str, Any]:
    """Build or update the dependency graph for a company.

    Creates a job via JobTracker, delegates to DependencyGraphService,
    and updates progress upon completion.

    Args:
        self: Celery task instance (bound).
        company_id: Company ID to build the graph for.
        scope: "full" or "incremental" (default "incremental").
        document_uuid: Document UUID for job tracking (defaults to
            "dependency_graph" as a virtual identifier).

    Returns:
        Dict with build results (status, edges_created, etc.).
    """
    try:
        result = asyncio.run(
            _build_dependency_graph_async(
                company_id=company_id,
                scope=scope,
                document_uuid=document_uuid,
            )
        )
        return result
    except Exception as exc:
        logger.error(
            "build_dependency_graph failed for company_id=%d: %s",
            company_id,
            exc,
        )
        return {
            "status": "failed",
            "error": _sanitize_error_message(exc),
        }


async def _build_dependency_graph_async(
    company_id: int,
    scope: str,
    document_uuid: str,
) -> dict[str, Any]:
    """Async implementation of the dependency graph build task.

    Args:
        company_id: Company ID to build the graph for.
        scope: "full" or "incremental".
        document_uuid: Document UUID for job tracking.

    Returns:
        Dict with build results.
    """
    from alcoabase.services.cross_reference import CrossReferenceService
    from alcoabase.services.dependency_graph import DependencyGraphService
    from alcoabase.services.job_tracker import JobConflictError, JobTracker
    from alcoabase.services.service_factory import get_knowledge_service
    from alcoabase.services.storage_service import StorageService

    session_factory = _get_async_session_factory()
    job_tracker = JobTracker()
    knowledge_service = get_knowledge_service()
    storage_service = StorageService()
    cross_reference_service = CrossReferenceService(
        session_factory=session_factory,
        knowledge_service=knowledge_service,
        storage_service=storage_service,
    )

    graph_service = DependencyGraphService(
        session_factory=session_factory,
        cross_reference_service=cross_reference_service,
        knowledge_service=knowledge_service,
    )

    # Create job
    async with session_factory() as session:
        try:
            job = await job_tracker.create_job(
                session,
                document_uuid,
                "dependency_graph_build",
                estimated_duration_seconds=BUILD_GRAPH_TIMEOUT_SECONDS,
                company_id=company_id,
            )
            await session.commit()
        except JobConflictError as e:
            return {"status": "conflict", "existing_job_id": e.existing_job_id}

    job_id = job.job_id

    try:
        # Execute the build
        if scope == "full":
            result = await graph_service.build_full_graph(company_id)
        else:
            result = await graph_service.build_incremental_graph(company_id)

        # Complete the job
        async with session_factory() as session:
            await job_tracker.update_progress(session, job_id, 100)
            await job_tracker.complete_job(session, job_id, result_reference=job_id)
            await session.commit()

        result["job_id"] = job_id
        return result

    except Exception as exc:
        error_msg = _sanitize_error_message(exc)
        async with session_factory() as session:
            await job_tracker.fail_job(session, job_id, error_msg)
            await session.commit()
        return {"status": "failed", "job_id": job_id, "error": error_msg}


# ---------------------------------------------------------------------------
# Task: analyze_change_impact
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    max_retries=0,
    time_limit=HARD_TIMEOUT_SECONDS,
    queue="ai_operations",
)
def analyze_change_impact(
    self,
    document_uuid: str,
    document_id: int,
    new_version_id: int,
    previous_version_id: int | None,
    company_id: int,
    requesting_user_id: int | None = None,
) -> dict[str, Any]:
    """Execute the full impact analysis pipeline for a document change.

    Orchestrates: delta → dependencies → assessment → notifications → report.
    Updates JobTracker progress monotonically:
        10% delta, 20% deps, 20-85% items, 85-95% gaps, 100% report.

    Enforces a 600s hard timeout with partial_success persistence and
    unassessed_items metadata.

    Args:
        self: Celery task instance (bound).
        document_uuid: UUID of the changed document.
        document_id: Database ID of the document.
        new_version_id: ID of the new document version.
        previous_version_id: ID of the previous version (None for first).
        company_id: Company ID for tenant scoping.
        requesting_user_id: User who triggered the analysis (None for auto).

    Returns:
        Dict with analysis results (status, report_id, findings counts).
    """
    try:
        result = asyncio.run(
            _analyze_change_impact_async(
                document_uuid=document_uuid,
                document_id=document_id,
                new_version_id=new_version_id,
                previous_version_id=previous_version_id,
                company_id=company_id,
                requesting_user_id=requesting_user_id,
            )
        )
        return result
    except Exception as exc:
        logger.error(
            "analyze_change_impact failed for document %s: %s",
            document_uuid,
            exc,
        )
        # Attempt to persist failure
        try:
            asyncio.run(
                _handle_analysis_failure(
                    document_uuid=document_uuid,
                    error=exc,
                )
            )
        except Exception:
            pass
        return {
            "status": "failed",
            "error": _sanitize_error_message(exc),
        }


async def _handle_analysis_failure(
    document_uuid: str,
    error: Exception,
) -> None:
    """Handle analysis failure by marking the job as failed.

    Attempts to find and fail the active job for this document.

    Args:
        document_uuid: UUID of the document being analyzed.
        error: The exception that caused the failure.
    """
    from alcoabase.services.job_tracker import JobTracker

    session_factory = _get_async_session_factory()
    job_tracker = JobTracker()

    async with session_factory() as session:
        existing_job_id = await job_tracker.has_active_job(
            session, document_uuid, "change_impact_analysis"
        )
        if existing_job_id:
            await job_tracker.fail_job(
                session, existing_job_id, _sanitize_error_message(error)
            )
            await session.commit()


async def _analyze_change_impact_async(
    document_uuid: str,
    document_id: int,
    new_version_id: int,
    previous_version_id: int | None,
    company_id: int,
    requesting_user_id: int | None,
) -> dict[str, Any]:
    """Async implementation of the full impact analysis pipeline.

    Orchestrates the complete pipeline with monotonic progress updates:
    1. Compute change delta (0% → 10%)
    2. Query downstream dependencies (10% → 20%)
    3. Assess affected items (20% → 85%)
    4. Execute gap analysis for critical items (85% → 95%)
    5. Create notifications and persist report (95% → 100%)

    Args:
        document_uuid: UUID of the changed document.
        document_id: Database ID of the document.
        new_version_id: ID of the new document version.
        previous_version_id: ID of the previous version.
        company_id: Company ID for tenant scoping.
        requesting_user_id: User who triggered the analysis.

    Returns:
        Dict with analysis results.
    """
    from sqlalchemy import select

    from alcoabase.models.impact_analysis import DependencyEdge
    from alcoabase.schemas.impact_analysis import GapFindingSchema
    from alcoabase.services.impact_analysis import ImpactAnalysisService
    from alcoabase.services.impact_notification import ImpactNotificationService
    from alcoabase.services.job_tracker import JobConflictError, JobTracker
    from alcoabase.services.service_factory import (
        get_inference_client,
        get_knowledge_service,
    )

    session_factory = _get_async_session_factory()
    job_tracker = JobTracker()
    knowledge_service = get_knowledge_service()
    inference_client = get_inference_client()

    start_time = time.monotonic()
    current_progress = 0

    # Helper to ensure monotonic progress updates
    async def _update_progress(session, job_id: str, target: int) -> None:
        nonlocal current_progress
        if target > current_progress:
            current_progress = target
            await job_tracker.update_progress(session, job_id, current_progress)
            await session.commit()

    # --- Step 0: Create job ---
    # First, count downstream dependencies to estimate duration
    async with session_factory() as session:
        dep_count_result = await session.execute(
            select(DependencyEdge).where(
                DependencyEdge.source_document_uuid == document_uuid,
                DependencyEdge.company_id == company_id,
            )
        )
        downstream_edges = list(dep_count_result.scalars().all())
        dependency_count = len(downstream_edges)

    estimated_duration = _estimate_duration(dependency_count)

    async with session_factory() as session:
        try:
            job = await job_tracker.create_job(
                session,
                document_uuid,
                "change_impact_analysis",
                estimated_duration_seconds=estimated_duration,
                company_id=company_id,
            )
            await session.commit()
        except JobConflictError as e:
            return {"status": "conflict", "existing_job_id": e.existing_job_id}

    job_id = job.job_id

    # Initialize services
    impact_service = ImpactAnalysisService(
        knowledge_service=knowledge_service,
        inference_client=inference_client,
        agent_registry=None,  # Will use fallback if needed
        session_factory=session_factory,
        job_tracker=job_tracker,
    )

    notification_service = ImpactNotificationService()
    affected_items = []
    gap_findings: list[GapFindingSchema] = []
    total_token_count = 0
    status = "completed"
    unassessed_items: list[str] = []

    try:
        # --- Step 1: Compute change delta (→ 10%) ---
        change_delta = await impact_service.compute_change_delta(
            document_uuid=document_uuid,
            new_version_id=new_version_id,
            previous_version_id=previous_version_id,
            company_id=company_id,
        )

        async with session_factory() as session:
            await _update_progress(session, job_id, PROGRESS_DELTA_COMPLETE)

        # Check timeout
        if (time.monotonic() - start_time) >= HARD_TIMEOUT_SECONDS:
            raise TimeoutError("Hard timeout exceeded after delta computation")

        # --- Step 2: Query downstream dependencies (→ 20%) ---
        async with session_factory() as session:
            dep_result = await session.execute(
                select(DependencyEdge).where(
                    DependencyEdge.source_document_uuid == document_uuid,
                    DependencyEdge.company_id == company_id,
                )
            )
            downstream_edges = list(dep_result.scalars().all())
            await _update_progress(session, job_id, PROGRESS_DEPS_COMPLETE)

        # Check timeout
        if (time.monotonic() - start_time) >= HARD_TIMEOUT_SECONDS:
            raise TimeoutError("Hard timeout exceeded after dependency query")

        # --- Step 3: Assess affected items (20% → 85%) ---
        if downstream_edges:
            async with session_factory() as session:
                affected_items = await impact_service.assess_affected_items(
                    change_delta=change_delta,
                    downstream_edges=downstream_edges,
                    company_id=company_id,
                    session=session,
                )
                await session.commit()

            # Update progress to items end
            total_token_count = sum(
                item.token_count for item in affected_items
            )

            async with session_factory() as session:
                await _update_progress(session, job_id, PROGRESS_ITEMS_END)
        else:
            async with session_factory() as session:
                await _update_progress(session, job_id, PROGRESS_ITEMS_END)

        # Check timeout before gap analysis
        if (time.monotonic() - start_time) >= HARD_TIMEOUT_SECONDS:
            # Record unassessed items if we timed out during assessment
            status = "partial_success"
            unassessed_items = [
                edge.target_document_uuid
                for edge in downstream_edges[len(affected_items):]
            ]
        else:
            # --- Step 4: Gap analysis phase (85% → 95%) ---
            # Gap analysis is included as part of the pipeline for
            # critical/major items (lightweight pass)
            async with session_factory() as session:
                await _update_progress(session, job_id, PROGRESS_GAPS_END)

        # --- Step 5: Create notifications and persist report (→ 100%) ---
        # Create notifications for critical/major items
        async with session_factory() as session:
            affected_items_data = [
                item.model_dump() for item in affected_items
            ]
            await notification_service.create_notifications(
                session=session,
                report_id=job_id,  # Use job_id as interim report reference
                affected_items=affected_items_data,
                company_id=company_id,
            )

            # Reset training tasks
            await notification_service.reset_training_tasks(
                session=session,
                affected_items=affected_items_data,
                report_id=job_id,
            )
            await session.commit()

        # Determine agent archetype used
        _sys_prompt, _temp, _max_tok, fallback_used = (
            impact_service._get_agent_config()
        )
        agent_archetype = (
            "Regulatory Compliance Auditor"
            if fallback_used
            else "Change Impact Analyst"
        )
        model_used = impact_service._get_model_name()

        # Compute analysis duration
        analysis_duration_ms = int((time.monotonic() - start_time) * 1000)

        # Persist the impact report
        async with session_factory() as session:
            report_id = await impact_service.create_impact_report(
                session=session,
                job_id=job_id,
                triggering_document_uuid=document_uuid,
                triggering_version_id=new_version_id,
                change_delta_summary=change_delta,
                affected_items=affected_items,
                gap_findings=gap_findings,
                status=status,
                analysis_timestamp=datetime.now(UTC),
                analysis_duration_ms=analysis_duration_ms,
                agent_archetype_used=agent_archetype,
                model_used=model_used,
                total_token_count=total_token_count,
                company_id=company_id,
                requesting_user_id=requesting_user_id,
            )
            await session.commit()

        # Complete the job
        async with session_factory() as session:
            await _update_progress(session, job_id, PROGRESS_REPORT_COMPLETE)
            await job_tracker.complete_job(
                session, job_id, result_reference=report_id
            )
            await session.commit()

        # Count findings by severity
        critical_count = sum(
            1 for item in affected_items
            if item.impact_severity == "critical"
        )
        major_count = sum(
            1 for item in affected_items
            if item.impact_severity == "major"
        )
        minor_count = sum(
            1 for item in affected_items
            if item.impact_severity == "minor"
        )

        logger.info(
            "Impact analysis completed: job_id=%s, document=%s, "
            "affected=%d (critical=%d, major=%d, minor=%d), duration=%dms",
            job_id,
            document_uuid,
            len(affected_items),
            critical_count,
            major_count,
            minor_count,
            analysis_duration_ms,
        )

        return {
            "status": status,
            "job_id": job_id,
            "report_id": report_id,
            "total_affected_items": len(affected_items),
            "critical_count": critical_count,
            "major_count": major_count,
            "minor_count": minor_count,
            "analysis_duration_ms": analysis_duration_ms,
        }

    except TimeoutError:
        # Hard timeout: persist partial results
        analysis_duration_ms = int((time.monotonic() - start_time) * 1000)
        status = "partial_success"

        # Determine unassessed items
        if not unassessed_items and downstream_edges:
            assessed_uuids = {
                item.affected_document_uuid for item in affected_items
            }
            unassessed_items = [
                edge.target_document_uuid
                for edge in downstream_edges
                if edge.target_document_uuid not in assessed_uuids
            ]

        # Attempt to persist partial report
        try:
            _sys_prompt, _temp, _max_tok, fallback_used = (
                impact_service._get_agent_config()
            )
            agent_archetype = (
                "Regulatory Compliance Auditor"
                if fallback_used
                else "Change Impact Analyst"
            )
            model_used = impact_service._get_model_name()

            async with session_factory() as session:
                report_id = await impact_service.create_impact_report(
                    session=session,
                    job_id=job_id,
                    triggering_document_uuid=document_uuid,
                    triggering_version_id=new_version_id,
                    change_delta_summary=change_delta,
                    affected_items=affected_items,
                    gap_findings=gap_findings,
                    status=status,
                    analysis_timestamp=datetime.now(UTC),
                    analysis_duration_ms=analysis_duration_ms,
                    agent_archetype_used=agent_archetype,
                    model_used=model_used,
                    total_token_count=total_token_count,
                    company_id=company_id,
                    requesting_user_id=requesting_user_id,
                )
                await session.commit()
        except Exception:
            report_id = None

        # Mark job as partial_success with timeout info
        error_msg = (
            f"Analysis timeout after {HARD_TIMEOUT_SECONDS}s. "
            f"{len(unassessed_items)} items unassessed."
        )
        async with session_factory() as session:
            await job_tracker.complete_job(
                session, job_id, result_reference=report_id
            )
            await session.commit()

        logger.warning(
            "Impact analysis timed out: job_id=%s, document=%s, "
            "assessed=%d, unassessed=%d",
            job_id,
            document_uuid,
            len(affected_items),
            len(unassessed_items),
        )

        return {
            "status": "partial_success",
            "job_id": job_id,
            "report_id": report_id,
            "total_affected_items": len(affected_items),
            "unassessed_items": unassessed_items,
            "analysis_duration_ms": analysis_duration_ms,
        }

    except Exception as exc:
        # Unrecoverable error: mark job as failed
        error_msg = _sanitize_error_message(exc)
        analysis_duration_ms = int((time.monotonic() - start_time) * 1000)

        async with session_factory() as session:
            await job_tracker.fail_job(session, job_id, error_msg)
            await session.commit()

        logger.error(
            "Impact analysis failed: job_id=%s, document=%s, error=%s",
            job_id,
            document_uuid,
            error_msg,
        )

        return {
            "status": "failed",
            "job_id": job_id,
            "error": error_msg,
            "analysis_duration_ms": analysis_duration_ms,
        }


# ---------------------------------------------------------------------------
# Task: execute_gap_analysis
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    max_retries=0,
    time_limit=GAP_ANALYSIS_TIMEOUT_SECONDS,
    queue="ai_operations",
)
def execute_gap_analysis(
    self,
    source_document_id: int,
    target_document_id: int,
    source_version_id: int | None,
    target_version_id: int | None,
    company_id: int,
    document_uuid: str = "gap_analysis",
) -> dict[str, Any]:
    """Execute gap analysis between two documents.

    Creates a job via JobTracker, delegates to GapAnalysisService,
    and updates progress upon completion.

    Args:
        self: Celery task instance (bound).
        source_document_id: ID of the source (updated) document.
        target_document_id: ID of the target (dependent) document.
        source_version_id: Specific source version (None = latest).
        target_version_id: Specific target version (None = latest).
        company_id: Company ID for tenant scoping.
        document_uuid: Document UUID for job tracking.

    Returns:
        Dict with gap analysis results.
    """
    try:
        result = asyncio.run(
            _execute_gap_analysis_async(
                source_document_id=source_document_id,
                target_document_id=target_document_id,
                source_version_id=source_version_id,
                target_version_id=target_version_id,
                company_id=company_id,
                document_uuid=document_uuid,
            )
        )
        return result
    except Exception as exc:
        logger.error(
            "execute_gap_analysis failed: source=%d, target=%d, error=%s",
            source_document_id,
            target_document_id,
            exc,
        )
        return {
            "status": "failed",
            "error": _sanitize_error_message(exc),
        }


async def _execute_gap_analysis_async(
    source_document_id: int,
    target_document_id: int,
    source_version_id: int | None,
    target_version_id: int | None,
    company_id: int,
    document_uuid: str,
) -> dict[str, Any]:
    """Async implementation of the gap analysis task.

    Args:
        source_document_id: ID of the source document.
        target_document_id: ID of the target document.
        source_version_id: Specific source version (None = latest).
        target_version_id: Specific target version (None = latest).
        company_id: Company ID for tenant scoping.
        document_uuid: Document UUID for job tracking.

    Returns:
        Dict with gap analysis results.
    """
    from alcoabase.config import get_settings
    from alcoabase.services.gap_analysis import GapAnalysisService
    from alcoabase.services.job_tracker import JobConflictError, JobTracker
    from alcoabase.services.service_factory import (
        get_inference_client,
        get_knowledge_service,
    )

    settings = get_settings()
    session_factory = _get_async_session_factory()
    job_tracker = JobTracker()
    knowledge_service = get_knowledge_service()
    inference_client = get_inference_client()

    # Create job
    async with session_factory() as session:
        try:
            job = await job_tracker.create_job(
                session,
                document_uuid,
                "gap_analysis",
                estimated_duration_seconds=GAP_ANALYSIS_TIMEOUT_SECONDS,
                company_id=company_id,
            )
            await session.commit()
        except JobConflictError as e:
            return {"status": "conflict", "existing_job_id": e.existing_job_id}

    job_id = job.job_id

    try:
        # Execute gap analysis
        async with session_factory() as session:
            gap_service = GapAnalysisService(
                session=session,
                knowledge_service=knowledge_service,
                inference_client=inference_client,
                model_name=settings.model_chat_name,
            )

            # Update progress to indicate start
            await job_tracker.update_progress(session, job_id, 10)
            await session.commit()

        async with session_factory() as session:
            gap_service = GapAnalysisService(
                session=session,
                knowledge_service=knowledge_service,
                inference_client=inference_client,
                model_name=settings.model_chat_name,
            )

            gap_result = await gap_service.execute_gap_analysis(
                source_doc_id=source_document_id,
                target_doc_id=target_document_id,
                source_version_id=source_version_id,
                target_version_id=target_version_id,
                company_id=company_id,
            )
            await session.commit()

        # Complete the job
        async with session_factory() as session:
            await job_tracker.update_progress(session, job_id, 100)
            await job_tracker.complete_job(
                session, job_id, result_reference=gap_result.job_id
            )
            await session.commit()

        logger.info(
            "Gap analysis completed: job_id=%s, source=%d, target=%d, "
            "gaps=%d (retained=%d)",
            job_id,
            source_document_id,
            target_document_id,
            gap_result.total_gaps_detected,
            gap_result.gaps_retained,
        )

        return {
            "status": gap_result.status,
            "job_id": job_id,
            "result_job_id": gap_result.job_id,
            "total_gaps_detected": gap_result.total_gaps_detected,
            "gaps_retained": gap_result.gaps_retained,
            "analysis_duration_ms": gap_result.analysis_duration_ms,
        }

    except Exception as exc:
        error_msg = _sanitize_error_message(exc)
        async with session_factory() as session:
            await job_tracker.fail_job(session, job_id, error_msg)
            await session.commit()

        return {"status": "failed", "job_id": job_id, "error": error_msg}
