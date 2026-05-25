"""FastAPI router for AI-Driven Change Impact Analysis endpoints.

Provides endpoints for dependency graph management, impact analysis triggering,
gap analysis, report retrieval, job status tracking, notifications, and
document impact status.

All endpoints are scoped by X-Company-Id header via the TenantContext dependency.
Mutation endpoints (POST) require X-Change-Reason header enforced by AuditMiddleware.

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: 1.1, 1.8, 1.9, 1.11, 1.15, 2.4, 2.5, 2.7, 3.7, 4.1, 4.5,
      4.6, 4.8, 4.11, 5.3, 5.4, 5.6, 6.3, 6.6, 6.7, 6.8, 6.9, 8.2, 8.3, 8.5, 8.6
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.models.impact_analysis import (
    GapAnalysisResult,
    ImpactReport,
)
from alcoabase.models.video import ProcessingJob
from alcoabase.schemas.impact_analysis import (
    BuildGraphRequest,
    DependencyEdgeResponse,
    DocumentImpactStatusResponse,
    GapAnalysisRequest,
    GraphFilters,
    ImpactReportListResponse,
    ImpactReportResponse,
    JobStatusResponse,
    PaginationParams,
    TriggerAnalysisRequest,
)
from alcoabase.services.dependency_graph import DependencyGraphService
from alcoabase.services.impact_notification import ImpactNotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/impact-analysis", tags=["Impact Analysis"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STALENESS_THRESHOLD_SECONDS = 600
IMPACT_ANALYSIS_OPERATION = "change_impact_analysis"
DEPENDENCY_GRAPH_BUILD_OPERATION = "dependency_graph_build"
GAP_ANALYSIS_OPERATION = "gap_analysis"


# ---------------------------------------------------------------------------
# Service Dependencies
# ---------------------------------------------------------------------------

_dependency_graph_service: DependencyGraphService | None = None
_notification_service: ImpactNotificationService | None = None


def get_dependency_graph_service() -> DependencyGraphService:
    """Provide the DependencyGraphService instance as a dependency."""
    global _dependency_graph_service
    if _dependency_graph_service is None:
        _dependency_graph_service = DependencyGraphService()
    return _dependency_graph_service


def get_notification_service() -> ImpactNotificationService:
    """Provide the ImpactNotificationService instance as a dependency."""
    global _notification_service
    if _notification_service is None:
        _notification_service = ImpactNotificationService()
    return _notification_service


# ---------------------------------------------------------------------------
# POST /dependency-graph/build → 202 + job_id
# ---------------------------------------------------------------------------


@router.post("/dependency-graph/build", status_code=202)
async def build_dependency_graph(
    request: BuildGraphRequest = BuildGraphRequest(),
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, str]:
    """Trigger async dependency graph build.

    Enqueues a Celery task to build or update the dependency graph for
    the current company. Returns 202 with a job_id for tracking.

    Args:
        request: Build parameters (scope: "full" or "incremental").
        session: Database session dependency.
        tenant: Resolved tenant context.

    Returns:
        Dict with job_id for the enqueued task.

    Raises:
        HTTPException: 503 if task enqueue fails.
    """
    job_id = str(uuid.uuid4())

    try:
        from alcoabase.tasks.celery_app import celery_app

        celery_app.send_task(
            "alcoabase.tasks.impact_analysis_tasks.build_dependency_graph",
            kwargs={
                "company_id": tenant.company_id,
                "scope": request.scope,
            },
            queue="ai_operations",
            task_id=job_id,
        )
    except Exception as exc:
        logger.error(
            "Failed to enqueue dependency graph build: %s", exc
        )
        raise HTTPException(
            status_code=503,
            detail="Job tracking service is temporarily unavailable.",
        )

    return {"job_id": job_id}


# ---------------------------------------------------------------------------
# GET /dependency-graph → paginated edges
# ---------------------------------------------------------------------------


@router.get("/dependency-graph")
async def list_dependency_edges(
    source_document_uuid: str | None = Query(default=None),
    target_document_uuid: str | None = Query(default=None),
    dependency_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
    service: DependencyGraphService = Depends(get_dependency_graph_service),
) -> dict[str, Any]:
    """List dependency graph edges with filtering and pagination.

    Args:
        source_document_uuid: Filter by source document UUID.
        target_document_uuid: Filter by target document UUID.
        dependency_type: Filter by dependency type.
        limit: Maximum items to return (1-200, default 50).
        offset: Number of items to skip (default 0).
        session: Database session dependency.
        tenant: Resolved tenant context.
        service: DependencyGraphService dependency.

    Returns:
        Dict with edges list and total_count.
    """
    try:
        filters = GraphFilters(
            source_document_uuid=source_document_uuid,
            target_document_uuid=target_document_uuid,
            dependency_type=dependency_type,
        )
    except Exception:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid dependency_type: {dependency_type}. "
            "Must be one of: validates, references, implements, "
            "trains_on, derived_from.",
        )
    pagination = PaginationParams(limit=limit, offset=offset)

    result = await service.get_edges(
        session=session,
        company_id=tenant.company_id,
        filters=filters,
        pagination=pagination,
    )

    edges = [
        DependencyEdgeResponse.model_validate(edge)
        for edge in result["edges"]
    ]
    return {"edges": edges, "total_count": result["total_count"]}


# ---------------------------------------------------------------------------
# GET /dependency-graph/{document_uuid} → grouped dependencies
# ---------------------------------------------------------------------------


@router.get("/dependency-graph/{document_uuid}")
async def get_document_dependencies(
    document_uuid: str,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
    service: DependencyGraphService = Depends(get_dependency_graph_service),
) -> dict[str, Any]:
    """Get all dependencies for a specific document grouped by type.

    Returns upstream and downstream edges grouped by dependency_type.
    Returns empty groups if no edges exist. Returns 404 if the document
    is not found in the company scope.

    Args:
        document_uuid: UUID of the document to query.
        session: Database session dependency.
        tenant: Resolved tenant context.
        service: DependencyGraphService dependency.

    Returns:
        Dict with document_uuid, upstream, and downstream grouped edges.

    Raises:
        HTTPException: 404 if document not found in company scope.
    """
    result = await service.get_document_dependencies(
        session=session,
        company_id=tenant.company_id,
        document_uuid=document_uuid,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {document_uuid}",
        )

    # Serialize edges in each group
    upstream_serialized = {
        dep_type: [
            DependencyEdgeResponse.model_validate(edge)
            for edge in edges
        ]
        for dep_type, edges in result["upstream"].items()
    }
    downstream_serialized = {
        dep_type: [
            DependencyEdgeResponse.model_validate(edge)
            for edge in edges
        ]
        for dep_type, edges in result["downstream"].items()
    }

    return {
        "document_uuid": result["document_uuid"],
        "upstream": upstream_serialized,
        "downstream": downstream_serialized,
    }


# ---------------------------------------------------------------------------
# POST /trigger → 202 + job_id, 409 if concurrent
# ---------------------------------------------------------------------------


@router.post("/trigger", status_code=202)
async def trigger_impact_analysis(
    request: TriggerAnalysisRequest,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, str]:
    """Manually trigger impact analysis for a document.

    Enqueues the analyze_change_impact Celery task. Returns 409 if an
    active non-stale job already exists for the same document.

    Args:
        request: Trigger parameters (document_id, optional version_id).
        session: Database session dependency.
        tenant: Resolved tenant context.

    Returns:
        Dict with job_id for the enqueued task.

    Raises:
        HTTPException: 409 if concurrent job exists, 503 if enqueue fails.
    """
    from alcoabase.models.document import Document

    # Look up the document to get document_uuid
    doc_result = await session.execute(
        select(Document).where(
            Document.id == request.document_id,
            Document.company_id == tenant.company_id,
        )
    )
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document with id {request.document_id} not found.",
        )

    # Check for active non-stale job (conflict detection)
    existing_job_id = await _check_active_job(
        session, document.id, IMPACT_ANALYSIS_OPERATION
    )
    if existing_job_id is not None:
        raise HTTPException(
            status_code=409,
            detail=f"An impact analysis job is already in progress.",
            headers={"X-Existing-Job-Id": existing_job_id},
        )

    # Enqueue the Celery task
    job_id = str(uuid.uuid4())
    try:
        from alcoabase.tasks.celery_app import celery_app

        celery_app.send_task(
            "alcoabase.tasks.impact_analysis_tasks.analyze_change_impact",
            kwargs={
                "document_uuid": document.document_uuid,
                "document_id": document.id,
                "version_id": request.document_version_id,
                "company_id": tenant.company_id,
                "uploaded_by": tenant.user_id,
            },
            queue="ai_operations",
            task_id=job_id,
        )
    except Exception as exc:
        logger.error("Failed to enqueue impact analysis: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Job tracking service is temporarily unavailable.",
        )

    return {"job_id": job_id}


# ---------------------------------------------------------------------------
# POST /gap-analysis → 202 + job_id
# ---------------------------------------------------------------------------


@router.post("/gap-analysis", status_code=202)
async def trigger_gap_analysis(
    request: GapAnalysisRequest,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, str]:
    """Trigger gap analysis between two documents.

    Validates that documents exist, are distinct, and have a dependency
    relationship. Enqueues the gap analysis Celery task.

    Args:
        request: Gap analysis parameters (source/target doc IDs, versions).
        session: Database session dependency.
        tenant: Resolved tenant context.

    Returns:
        Dict with job_id for the enqueued task.

    Raises:
        HTTPException: 422 if same doc or no dependency, 404 if not found,
            503 if enqueue fails.
    """
    from alcoabase.models.document import Document
    from alcoabase.models.impact_analysis import DependencyEdge

    # Validate: same-document check
    if request.source_document_id == request.target_document_id:
        raise HTTPException(
            status_code=422,
            detail="Gap analysis requires two distinct documents. "
            "source_document_id and target_document_id must differ.",
        )

    # Validate document existence
    source_result = await session.execute(
        select(Document).where(
            Document.id == request.source_document_id,
            Document.company_id == tenant.company_id,
        )
    )
    source_doc = source_result.scalar_one_or_none()
    if source_doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source document with id {request.source_document_id} "
            f"not found in company scope.",
        )

    target_result = await session.execute(
        select(Document).where(
            Document.id == request.target_document_id,
            Document.company_id == tenant.company_id,
        )
    )
    target_doc = target_result.scalar_one_or_none()
    if target_doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Target document with id {request.target_document_id} "
            f"not found in company scope.",
        )

    # Validate dependency exists with confidence >= 0.5
    dep_result = await session.execute(
        select(DependencyEdge.id).where(
            DependencyEdge.source_document_uuid == source_doc.document_uuid,
            DependencyEdge.target_document_uuid == target_doc.document_uuid,
            DependencyEdge.company_id == tenant.company_id,
            DependencyEdge.confidence_score >= 0.5,
        )
    )
    if dep_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=422,
            detail="No dependency relationship with confidence_score >= 0.5 "
            "exists between the specified documents. Build the dependency "
            "graph first using POST /api/impact-analysis/dependency-graph/build.",
        )

    # Enqueue the Celery task
    job_id = str(uuid.uuid4())
    try:
        from alcoabase.tasks.celery_app import celery_app

        celery_app.send_task(
            "alcoabase.tasks.impact_analysis_tasks.execute_gap_analysis",
            kwargs={
                "source_doc_id": request.source_document_id,
                "target_doc_id": request.target_document_id,
                "source_version_id": request.source_version_id,
                "target_version_id": request.target_version_id,
                "company_id": tenant.company_id,
            },
            queue="ai_operations",
            task_id=job_id,
        )
    except Exception as exc:
        logger.error("Failed to enqueue gap analysis: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Job tracking service is temporarily unavailable.",
        )

    return {"job_id": job_id}


# ---------------------------------------------------------------------------
# GET /gap-analysis/{job_id}/results → findings with pagination
# ---------------------------------------------------------------------------


@router.get("/gap-analysis/{job_id}/results")
async def get_gap_analysis_results(
    job_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    severity: str | None = Query(default=None),
    gap_type: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Get gap analysis findings for a completed job.

    Returns 202 if the job is still processing. Returns 200 with empty
    findings and failure reason if the job failed.

    Args:
        job_id: Job identifier for the gap analysis.
        limit: Maximum findings to return (1-100, default 20).
        offset: Number of findings to skip (default 0).
        severity: Filter by severity (critical, major, minor).
        gap_type: Filter by gap type (missing, contradicts, incomplete, outdated).
        session: Database session dependency.
        tenant: Resolved tenant context.

    Returns:
        Dict with gap findings, pagination info, and job metadata.

    Raises:
        HTTPException: 202 if processing, 404 if job not found.
    """
    # Check job status first
    job_result = await session.execute(
        select(ProcessingJob).where(
            ProcessingJob.job_id == job_id,
            ProcessingJob.company_id == tenant.company_id,
        )
    )
    job = job_result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job not found: {job_id}",
        )

    # If still processing, return 202 with progress
    if job.status == "processing":
        raise HTTPException(
            status_code=202,
            detail={
                "job_id": job_id,
                "status": "processing",
                "progress_percent": job.progress_percent,
            },
        )

    # If failed, return 200 with empty findings and reason
    if job.status == "failed":
        return {
            "job_id": job_id,
            "status": "failed",
            "gap_findings": [],
            "total_count": 0,
            "failure_reason": job.error_message,
        }

    # Job completed or partial_success — retrieve results
    gap_result = await session.execute(
        select(GapAnalysisResult).where(
            GapAnalysisResult.job_id == job_id,
            GapAnalysisResult.company_id == tenant.company_id,
        )
    )
    gap_analysis = gap_result.scalar_one_or_none()

    if gap_analysis is None:
        return {
            "job_id": job_id,
            "status": job.status,
            "gap_findings": [],
            "total_count": 0,
        }

    # Apply filters to gap_findings
    findings = gap_analysis.gap_findings or []
    if severity:
        findings = [f for f in findings if f.get("severity") == severity]
    if gap_type:
        findings = [f for f in findings if f.get("gap_type") == gap_type]

    total_count = len(findings)
    paginated_findings = findings[offset : offset + limit]

    return {
        "job_id": job_id,
        "status": gap_analysis.status,
        "source_document_uuid": gap_analysis.source_document_uuid,
        "target_document_uuid": gap_analysis.target_document_uuid,
        "gap_findings": paginated_findings,
        "total_count": total_count,
        "total_gaps_detected": gap_analysis.total_gaps_detected,
        "gaps_retained": gap_analysis.gaps_retained,
    }


# ---------------------------------------------------------------------------
# GET /reports → paginated reports with filters
# ---------------------------------------------------------------------------


@router.get("/reports", response_model=ImpactReportListResponse)
async def list_reports(
    triggering_document_uuid: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> ImpactReportListResponse:
    """List impact reports with filtering and pagination.

    Sorted by analysis_timestamp descending (newest first).

    Args:
        triggering_document_uuid: Filter by triggering document UUID.
        severity: Filter by reports containing findings of this severity.
        start_date: Filter by analysis_timestamp >= start_date.
        end_date: Filter by analysis_timestamp <= end_date.
        status: Filter by report status.
        limit: Maximum reports to return (1-100, default 20).
        offset: Number of reports to skip (default 0).
        session: Database session dependency.
        tenant: Resolved tenant context.

    Returns:
        ImpactReportListResponse with reports and total_count.
    """
    from sqlalchemy import func as sa_func

    conditions = [ImpactReport.company_id == tenant.company_id]

    if triggering_document_uuid:
        conditions.append(
            ImpactReport.triggering_document_uuid == triggering_document_uuid
        )
    if status:
        conditions.append(ImpactReport.status == status)
    if start_date:
        conditions.append(ImpactReport.analysis_timestamp >= start_date)
    if end_date:
        conditions.append(ImpactReport.analysis_timestamp <= end_date)

    # Count total matching reports
    count_stmt = select(sa_func.count(ImpactReport.id)).where(*conditions)
    count_result = await session.execute(count_stmt)
    total_count = count_result.scalar_one()

    # Query reports with pagination
    query = (
        select(ImpactReport)
        .where(*conditions)
        .order_by(ImpactReport.analysis_timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(query)
    reports = list(result.scalars().all())

    # Apply severity filter in-memory (checks affected_items JSONB)
    if severity:
        filtered_reports = []
        for report in reports:
            items = report.affected_items or []
            if any(
                item.get("impact_severity") == severity for item in items
            ):
                filtered_reports.append(report)
        reports = filtered_reports
        # Recount for severity filter (approximate — full accuracy
        # would require a JSONB query)
        total_count = len(filtered_reports)

    report_responses = [
        ImpactReportResponse.model_validate(r) for r in reports
    ]
    return ImpactReportListResponse(
        reports=report_responses, total_count=total_count
    )


# ---------------------------------------------------------------------------
# GET /reports/{report_id} → full report
# ---------------------------------------------------------------------------


@router.get("/reports/{report_id}", response_model=ImpactReportResponse)
async def get_report(
    report_id: str,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> ImpactReportResponse:
    """Get a full impact report by report_id.

    Args:
        report_id: UUID identifier of the report.
        session: Database session dependency.
        tenant: Resolved tenant context.

    Returns:
        Full ImpactReportResponse.

    Raises:
        HTTPException: 404 if not found/wrong company, 422 if invalid UUID.
    """
    # Validate UUID format
    try:
        uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid report_id format: {report_id}. "
            "Expected a valid UUID.",
        )

    result = await session.execute(
        select(ImpactReport).where(
            ImpactReport.report_id == report_id,
            ImpactReport.company_id == tenant.company_id,
        )
    )
    report = result.scalar_one_or_none()

    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"Report not found: {report_id}",
        )

    return ImpactReportResponse.model_validate(report)


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/status → job status with progress
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> JobStatusResponse:
    """Get job status and progress for an impact analysis job.

    Args:
        job_id: UUID identifier of the job.
        session: Database session dependency.
        tenant: Resolved tenant context.

    Returns:
        JobStatusResponse with progress details.

    Raises:
        HTTPException: 404 if job not found or wrong company.
    """
    result = await session.execute(
        select(ProcessingJob).where(
            ProcessingJob.job_id == job_id,
            ProcessingJob.company_id == tenant.company_id,
        )
    )
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job not found: {job_id}",
        )

    # Map job status to response status
    status = job.status
    if status not in ("processing", "completed", "partial_success", "failed"):
        status = "processing"

    # Determine current phase from progress_percent
    current_phase = _determine_phase(job.progress_percent)

    return JobStatusResponse(
        job_id=job.job_id,
        status=status,
        progress_percent=job.progress_percent or 0,
        current_phase=current_phase,
        items_assessed=0,
        items_total=0,
        critical_findings_count=0,
        major_findings_count=0,
        minor_findings_count=0,
        error_message=job.error_message,
    )


# ---------------------------------------------------------------------------
# GET /notifications → unacknowledged notifications for current user
# ---------------------------------------------------------------------------


@router.get("/notifications")
async def list_notifications(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
    service: ImpactNotificationService = Depends(get_notification_service),
) -> dict[str, Any]:
    """List unacknowledged notifications for the current user.

    Sorted by severity (critical first) then created_at (newest first).

    Args:
        limit: Maximum notifications to return (1-200, default 20).
        offset: Number of notifications to skip (default 0).
        session: Database session dependency.
        tenant: Resolved tenant context.
        service: ImpactNotificationService dependency.

    Returns:
        Dict with notifications list and total_count.
    """
    pagination = PaginationParams(limit=limit, offset=offset)

    result = await service.get_unacknowledged(
        session=session,
        user_id=tenant.user_id,
        company_id=tenant.company_id,
        pagination=pagination,
    )

    return {
        "notifications": result["notifications"],
        "total_count": result["total_count"],
    }


# ---------------------------------------------------------------------------
# POST /notifications/{notification_id}/acknowledge → 200 (idempotent)
# ---------------------------------------------------------------------------


@router.post("/notifications/{notification_id}/acknowledge")
async def acknowledge_notification(
    notification_id: int,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
    service: ImpactNotificationService = Depends(get_notification_service),
) -> dict[str, Any]:
    """Acknowledge a notification (idempotent).

    Marks the notification as acknowledged. If already acknowledged,
    returns the existing acknowledgment details without modification.

    Args:
        notification_id: ID of the notification to acknowledge.
        session: Database session dependency.
        tenant: Resolved tenant context.
        service: ImpactNotificationService dependency.

    Returns:
        Dict with acknowledgment status and notification details.

    Raises:
        HTTPException: 404 if notification not found or wrong company.
    """
    result = await service.acknowledge_notification(
        session=session,
        notification_id=notification_id,
        user_id=tenant.user_id,
        company_id=tenant.company_id,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Notification not found: {notification_id}",
        )

    await session.commit()
    return {"status": "acknowledged", "notification": result}


# ---------------------------------------------------------------------------
# GET /documents/{document_uuid}/status → document impact status
# ---------------------------------------------------------------------------


@router.get(
    "/documents/{document_uuid}/status",
    response_model=DocumentImpactStatusResponse,
)
async def get_document_impact_status(
    document_uuid: str,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
    service: ImpactNotificationService = Depends(get_notification_service),
) -> DocumentImpactStatusResponse:
    """Get the impact analysis status for a document.

    Returns outstanding critical/major finding counts and whether
    the document is up-to-date.

    Args:
        document_uuid: UUID of the document to check.
        session: Database session dependency.
        tenant: Resolved tenant context.
        service: ImpactNotificationService dependency.

    Returns:
        DocumentImpactStatusResponse with status details.
    """
    return await service.get_document_status(
        session=session,
        document_uuid=document_uuid,
        company_id=tenant.company_id,
    )


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


async def _check_active_job(
    session: AsyncSession,
    document_id: int,
    operation: str,
) -> str | None:
    """Check for an active non-stale processing job.

    A job is considered active if its status is "processing" and its
    started_at timestamp is within STALENESS_THRESHOLD_SECONDS of now.

    Args:
        session: Active database session.
        document_id: Document ID to check for active jobs.
        operation: Operation type to check.

    Returns:
        The job_id of the active non-stale job if one exists, None otherwise.
    """
    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(ProcessingJob.job_id, ProcessingJob.started_at).where(
            ProcessingJob.document_id == document_id,
            ProcessingJob.operation == operation,
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
        return job_id

    # Job is stale, allow new trigger
    return None


def _determine_phase(progress_percent: int | None) -> str:
    """Determine the current analysis phase from progress percentage.

    Maps progress percentage to the corresponding pipeline phase.

    Args:
        progress_percent: Current progress (0-100).

    Returns:
        Phase name string.
    """
    progress = progress_percent or 0

    if progress < 10:
        return "computing_delta"
    elif progress < 20:
        return "querying_dependencies"
    elif progress < 85:
        return "assessing_impact"
    elif progress < 95:
        return "analyzing_gaps"
    else:
        return "persisting_report"
