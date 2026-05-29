"""FastAPI router for AI-Powered Traceability & Gap Discovery endpoints."""
from __future__ import annotations
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession
from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.models.traceability import TraceabilityMatrix
from alcoabase.models.video import ProcessingJob
from alcoabase.schemas.traceability import (
    AlertFilters, AlertListResponse, CoverageHistoryResponse,
    CoverageSnapshotSchema, CoverageSummaryResponse, DocumentCoverageBreakdown,
    DocumentCoverageResponse, GenerateMatrixRequest, HistoryFilters,
    JobStatusResponse, OrphanRequirementListResponse, OrphanRequirementSchema,
    OrphanTestCaseListResponse, OrphanTestCaseSchema, ResolveAlertRequest,
    TraceabilityAlertResponse, TraceabilityLinkListResponse,
    TraceabilityLinkSchema, TraceabilityMatrixListResponse,
    TraceabilityMatrixResponse,
)
from alcoabase.services.coverage_metrics import CoverageMetricsService
from alcoabase.services.traceability_alert import TraceabilityAlertService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/traceability", tags=["Traceability"])

# ---------------------------------------------------------------------------
# UUID validation
# ---------------------------------------------------------------------------
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_DOC_UUID_RE = re.compile(r"^[0-9a-zA-Z\-]{1,36}$")


def _validate_document_uuid(value: str) -> None:
    """Validate that a string is a valid document UUID format."""
    if not _UUID_RE.match(value) and not _DOC_UUID_RE.match(value):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid document_uuid format: {value}",
        )


# ---------------------------------------------------------------------------
# Service Dependencies
# ---------------------------------------------------------------------------

_coverage_metrics_service: CoverageMetricsService | None = None
_traceability_alert_service: TraceabilityAlertService | None = None


def get_coverage_metrics_service() -> CoverageMetricsService:
    """Provide the CoverageMetricsService instance as a dependency."""
    global _coverage_metrics_service
    if _coverage_metrics_service is None:
        from alcoabase.database import _session_factory
        _coverage_metrics_service = CoverageMetricsService(
            session_factory=_session_factory
        )
    return _coverage_metrics_service


def get_traceability_alert_service() -> TraceabilityAlertService:
    """Provide the TraceabilityAlertService instance as a dependency."""
    global _traceability_alert_service
    if _traceability_alert_service is None:
        from alcoabase.database import _session_factory
        _traceability_alert_service = TraceabilityAlertService(
            session_factory=_session_factory
        )
    return _traceability_alert_service


# ---------------------------------------------------------------------------
# POST /matrices/generate -> 202 + job_id
# ---------------------------------------------------------------------------


@router.post("/matrices/generate", status_code=202)
async def generate_matrix(
    request: GenerateMatrixRequest,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, str]:
    """Trigger async traceability matrix generation."""
    from alcoabase.database import _session_factory as db_session_factory
    from alcoabase.services.job_tracker import JobConflictError, JobTracker
    from alcoabase.services.traceability_matrix import (
        TraceabilityMatrixService,
        _DocumentNotFoundError,
        _ValidationError,
    )

    job_tracker = JobTracker()
    service = TraceabilityMatrixService(
        session_factory=db_session_factory,
        job_tracker=job_tracker,
    )

    try:
        result = await service.validate_and_enqueue(
            request=request,
            company_id=tenant.company_id,
            user_id=tenant.user_id,
        )
    except _DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except _ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except JobConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="A matrix generation job is already in progress.",
            headers={"X-Existing-Job-Id": exc.existing_job_id},
        )

    job_id = result["job_id"]
    try:
        from alcoabase.tasks.celery_app import celery_app
        celery_app.send_task(
            "alcoabase.tasks.traceability_tasks.generate_traceability_matrix",
            kwargs={
                "job_id": job_id,
                "source_document_ids": request.source_document_ids,
                "target_document_ids": request.target_document_ids,
                "matrix_name": request.matrix_name,
                "description": request.description,
                "company_id": tenant.company_id,
                "user_id": tenant.user_id,
            },
            queue="ai_operations",
            task_id=job_id,
        )
    except Exception as exc:
        logger.error("Failed to enqueue traceability matrix generation: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Job tracking service is temporarily unavailable.",
        )

    return {"job_id": job_id}


# ---------------------------------------------------------------------------
# GET /matrices -> paginated matrices list
# ---------------------------------------------------------------------------


@router.get("/matrices", response_model=TraceabilityMatrixListResponse)
async def list_matrices(
    source_document_uuid: str | None = Query(default=None),
    target_document_uuid: str | None = Query(default=None),
    status: str | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> TraceabilityMatrixListResponse:
    """List traceability matrices with filtering and pagination."""
    conditions: list[Any] = [
        TraceabilityMatrix.company_id == tenant.company_id,
        TraceabilityMatrix.deleted_at.is_(None),
    ]
    if source_document_uuid:
        conditions.append(TraceabilityMatrix.source_document_uuids.contains([source_document_uuid]))
    if target_document_uuid:
        conditions.append(TraceabilityMatrix.target_document_uuids.contains([target_document_uuid]))
    if status:
        conditions.append(TraceabilityMatrix.status == status)
    if start_date:
        conditions.append(TraceabilityMatrix.generation_timestamp >= start_date)
    if end_date:
        conditions.append(TraceabilityMatrix.generation_timestamp <= end_date)

    count_stmt = select(sa_func.count(TraceabilityMatrix.id)).where(*conditions)
    count_result = await session.execute(count_stmt)
    total_count = count_result.scalar_one()

    query = (
        select(TraceabilityMatrix)
        .where(*conditions)
        .order_by(TraceabilityMatrix.generation_timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(query)
    matrices = list(result.scalars().all())

    matrix_responses = [TraceabilityMatrixResponse.model_validate(m) for m in matrices]
    return TraceabilityMatrixListResponse(matrices=matrix_responses, total_count=total_count)


# ---------------------------------------------------------------------------
# GET /matrices/{matrix_id} -> full matrix detail
# ---------------------------------------------------------------------------


@router.get("/matrices/{matrix_id}", response_model=TraceabilityMatrixResponse)
async def get_matrix(
    matrix_id: str,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> TraceabilityMatrixResponse:
    """Get full traceability matrix detail by matrix_id."""
    try:
        uuid.UUID(matrix_id)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid matrix_id format: {matrix_id}. Expected a valid UUID.")

    result = await session.execute(
        select(TraceabilityMatrix).where(
            TraceabilityMatrix.matrix_id == matrix_id,
            TraceabilityMatrix.company_id == tenant.company_id,
        )
    )
    matrix = result.scalar_one_or_none()
    if matrix is None:
        raise HTTPException(status_code=404, detail=f"Matrix not found: {matrix_id}")
    return TraceabilityMatrixResponse.model_validate(matrix)


# ---------------------------------------------------------------------------
# GET /matrices/{matrix_id}/links -> paginated traceability links
# ---------------------------------------------------------------------------


@router.get("/matrices/{matrix_id}/links", response_model=TraceabilityLinkListResponse)
async def get_matrix_links(
    matrix_id: str,
    source_document_uuid: str | None = Query(default=None),
    target_document_uuid: str | None = Query(default=None),
    link_confidence_min: float | None = Query(default=None),
    link_method: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> TraceabilityLinkListResponse:
    """Get paginated traceability links for a specific matrix."""
    try:
        uuid.UUID(matrix_id)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid matrix_id format: {matrix_id}. Expected a valid UUID.")

    if link_confidence_min is not None and (link_confidence_min < 0.0 or link_confidence_min > 1.0):
        raise HTTPException(status_code=422, detail="link_confidence_min must be between 0.0 and 1.0 inclusive.")

    result = await session.execute(
        select(TraceabilityMatrix).where(
            TraceabilityMatrix.matrix_id == matrix_id,
            TraceabilityMatrix.company_id == tenant.company_id,
        )
    )
    matrix = result.scalar_one_or_none()
    if matrix is None:
        raise HTTPException(status_code=404, detail=f"Matrix not found: {matrix_id}")

    links = matrix.traceability_links or []
    if source_document_uuid:
        links = [lnk for lnk in links if lnk.get("source_document_uuid") == source_document_uuid]
    if target_document_uuid:
        links = [lnk for lnk in links if lnk.get("target_document_uuid") == target_document_uuid]
    if link_confidence_min is not None:
        links = [lnk for lnk in links if lnk.get("link_confidence", 0.0) >= link_confidence_min]
    if link_method:
        links = [lnk for lnk in links if lnk.get("link_method") == link_method]

    total_count = len(links)
    paginated_links = links[offset: offset + limit]
    link_schemas = [TraceabilityLinkSchema.model_validate(link) for link in paginated_links]
    return TraceabilityLinkListResponse(links=link_schemas, total_count=total_count)


# ---------------------------------------------------------------------------
# GET /matrices/{matrix_id}/orphan-requirements
# ---------------------------------------------------------------------------


@router.get("/matrices/{matrix_id}/orphan-requirements", response_model=OrphanRequirementListResponse)
async def get_orphan_requirements(
    matrix_id: str,
    severity: str | None = Query(default=None),
    source_document_uuid: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> OrphanRequirementListResponse:
    """Get paginated orphan requirements for a specific matrix."""
    try:
        uuid.UUID(matrix_id)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid matrix_id format: {matrix_id}. Expected a valid UUID.")

    result = await session.execute(
        select(TraceabilityMatrix).where(
            TraceabilityMatrix.matrix_id == matrix_id,
            TraceabilityMatrix.company_id == tenant.company_id,
        )
    )
    matrix = result.scalar_one_or_none()
    if matrix is None:
        raise HTTPException(status_code=404, detail=f"Matrix not found: {matrix_id}")

    orphans = matrix.orphan_requirements or []
    if severity:
        orphans = [o for o in orphans if o.get("severity") == severity]
    if source_document_uuid:
        orphans = [o for o in orphans if o.get("source_document_uuid") == source_document_uuid]

    total_count = len(orphans)
    paginated_orphans = orphans[offset: offset + limit]
    orphan_schemas = [OrphanRequirementSchema.model_validate(o) for o in paginated_orphans]
    return OrphanRequirementListResponse(orphan_requirements=orphan_schemas, total_count=total_count)


# ---------------------------------------------------------------------------
# GET /matrices/{matrix_id}/orphan-test-cases
# ---------------------------------------------------------------------------


@router.get("/matrices/{matrix_id}/orphan-test-cases", response_model=OrphanTestCaseListResponse)
async def get_orphan_test_cases(
    matrix_id: str,
    risk_level: str | None = Query(default=None),
    target_document_uuid: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> OrphanTestCaseListResponse:
    """Get paginated orphan test cases, ordered by risk_level desc then test_case_id asc."""
    try:
        uuid.UUID(matrix_id)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid matrix_id format: {matrix_id}. Expected a valid UUID.")

    result = await session.execute(
        select(TraceabilityMatrix).where(
            TraceabilityMatrix.matrix_id == matrix_id,
            TraceabilityMatrix.company_id == tenant.company_id,
        )
    )
    matrix = result.scalar_one_or_none()
    if matrix is None:
        raise HTTPException(status_code=404, detail=f"Matrix not found: {matrix_id}")

    orphans = matrix.orphan_test_cases or []
    if risk_level:
        orphans = [o for o in orphans if o.get("risk_level") == risk_level]
    if target_document_uuid:
        orphans = [o for o in orphans if o.get("target_document_uuid") == target_document_uuid]

    risk_level_order = {"high": 0, "medium": 1, "low": 2}
    orphans.sort(key=lambda o: (risk_level_order.get(o.get("risk_level", "low"), 3), o.get("test_case_id", "")))

    total_count = len(orphans)
    paginated_orphans = orphans[offset: offset + limit]
    orphan_schemas = [OrphanTestCaseSchema.model_validate(o) for o in paginated_orphans]
    return OrphanTestCaseListResponse(orphan_test_cases=orphan_schemas, total_count=total_count)


# ---------------------------------------------------------------------------
# DELETE /matrices/{matrix_id} -> soft-delete (204)
# ---------------------------------------------------------------------------


@router.delete("/matrices/{matrix_id}", status_code=204)
async def delete_matrix(
    matrix_id: str,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> Response:
    """Soft-delete a traceability matrix."""
    try:
        uuid.UUID(matrix_id)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid matrix_id format: {matrix_id}. Expected a valid UUID.")

    result = await session.execute(
        select(TraceabilityMatrix).where(
            TraceabilityMatrix.matrix_id == matrix_id,
            TraceabilityMatrix.company_id == tenant.company_id,
            TraceabilityMatrix.deleted_at.is_(None),
        )
    )
    matrix = result.scalar_one_or_none()
    if matrix is None:
        raise HTTPException(status_code=404, detail=f"Matrix not found: {matrix_id}")

    matrix.deleted_at = datetime.now(timezone.utc)
    session.add(matrix)
    await session.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# GET /documents/{document_uuid}/coverage -> document coverage status
# Requirements: 5.4, 7.6
# ---------------------------------------------------------------------------


@router.get("/documents/{document_uuid}/coverage", response_model=DocumentCoverageResponse)
async def get_document_coverage(
    document_uuid: str,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CoverageMetricsService = Depends(get_coverage_metrics_service),
) -> DocumentCoverageResponse:
    """Get the latest coverage status for a document as a source.

    Returns null values if the document has never been in a matrix as source.

    Raises:
        HTTPException: 422 if document_uuid is not a valid UUID format.
    """
    _validate_document_uuid(document_uuid)
    result = await service.get_document_coverage(
        document_uuid=document_uuid,
        company_id=tenant.company_id,
    )
    return DocumentCoverageResponse(**result)


# ---------------------------------------------------------------------------
# GET /coverage/summary -> aggregated coverage summary
# Requirements: 7.3, 7.7
# ---------------------------------------------------------------------------


@router.get("/coverage/summary", response_model=CoverageSummaryResponse)
async def get_coverage_summary(
    tenant: TenantContext = Depends(get_tenant_context),
    service: CoverageMetricsService = Depends(get_coverage_metrics_service),
) -> CoverageSummaryResponse:
    """Get aggregated coverage summary across all non-deleted matrices.

    Returns 0 values if no matrices exist for the company.
    """
    result = await service.get_coverage_summary(company_id=tenant.company_id)
    breakdown = [DocumentCoverageBreakdown(**item) for item in result.get("breakdown", [])]
    return CoverageSummaryResponse(
        total_matrices_generated=result["total_matrices_generated"],
        latest_matrix_date=result.get("latest_matrix_date"),
        average_coverage_percentage=result["average_coverage_percentage"],
        total_orphan_requirements=result["total_orphan_requirements"],
        total_orphan_test_cases=result["total_orphan_test_cases"],
        average_compliance_readiness_score=result["average_compliance_readiness_score"],
        breakdown=breakdown,
    )


# ---------------------------------------------------------------------------
# GET /coverage/history -> paginated coverage snapshots
# Requirements: 7.4, 7.6, 7.7
# ---------------------------------------------------------------------------


@router.get("/coverage/history", response_model=CoverageHistoryResponse)
async def get_coverage_history(
    source_document_uuid: str | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(get_tenant_context),
    service: CoverageMetricsService = Depends(get_coverage_metrics_service),
) -> CoverageHistoryResponse:
    """Get paginated coverage snapshots over time."""
    filters = HistoryFilters(
        source_document_uuid=source_document_uuid,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    result = await service.get_coverage_history(company_id=tenant.company_id, filters=filters)
    snapshots = [CoverageSnapshotSchema.model_validate(s) for s in result.get("snapshots", [])]
    return CoverageHistoryResponse(snapshots=snapshots, total_count=result["total_count"])


# ---------------------------------------------------------------------------
# GET /alerts -> unresolved alerts sorted by severity then created_at
# Requirements: 9.2, 9.6
# ---------------------------------------------------------------------------


@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    alert_severity: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(get_tenant_context),
    service: TraceabilityAlertService = Depends(get_traceability_alert_service),
) -> AlertListResponse:
    """List unresolved traceability alerts for the current company.

    Sorted by severity (critical first) then created_at (newest first).
    """
    filters = AlertFilters(
        alert_severity=alert_severity,
        is_resolved=False,
        limit=limit,
        offset=offset,
    )
    alerts, total_count = await service.get_alerts(company_id=tenant.company_id, filters=filters)
    alert_responses = [TraceabilityAlertResponse.model_validate(alert) for alert in alerts]
    return AlertListResponse(alerts=alert_responses, total_count=total_count)


# ---------------------------------------------------------------------------
# POST /alerts/{alert_id}/resolve -> resolve alert
# Requirements: 9.3, 9.6
# ---------------------------------------------------------------------------


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    request: ResolveAlertRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: TraceabilityAlertService = Depends(get_traceability_alert_service),
) -> dict[str, Any]:
    """Resolve a traceability alert. Requires X-Change-Reason header.

    Raises:
        HTTPException: 404 if alert not found or wrong company.
        HTTPException: 409 if alert is already resolved.
    """
    alert, status_code = await service.resolve_alert(
        alert_id=alert_id,
        user_id=tenant.user_id,
        resolution_action=request.resolution_action,
        resolution_note=request.resolution_note,
        company_id=tenant.company_id,
    )
    if status_code == 404:
        raise HTTPException(status_code=404, detail=f"Alert not found: {alert_id}")
    if status_code == 409:
        raise HTTPException(status_code=409, detail="Alert has already been resolved.")
    if status_code != 200 or alert is None:
        raise HTTPException(status_code=500, detail="Failed to resolve alert.")
    return {"status": "resolved", "alert": TraceabilityAlertResponse.model_validate(alert)}


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/status -> job status with progress
# Requirements: 11.3, 11.6, 11.7
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> JobStatusResponse:
    """Get job status and progress for a traceability matrix generation job.

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
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    status = job.status
    if status not in ("processing", "completed", "partial_success", "failed"):
        status = "processing"

    progress = job.progress_percent or 0
    current_phase = _determine_traceability_phase(progress)

    requirements_extracted = 0
    test_cases_extracted = 0
    links_established = 0
    orphans_detected = 0
    matrix_id = None
    total_requirements = None
    total_test_cases = None
    total_links = None
    coverage_percentage = None
    orphan_requirements_count = None
    orphan_test_cases_count = None
    compliance_readiness_score = None
    generation_duration_ms = None
    summary_sentence = None

    if job.result_reference:
        try:
            result_data = json.loads(job.result_reference)
            matrix_id = result_data.get("matrix_id")
            total_requirements = result_data.get("total_requirements")
            total_test_cases = result_data.get("total_test_cases")
            total_links = result_data.get("total_links")
            coverage_percentage = result_data.get("coverage_percentage")
            orphan_requirements_count = result_data.get("orphan_requirements_count")
            orphan_test_cases_count = result_data.get("orphan_test_cases_count")
            compliance_readiness_score = result_data.get("compliance_readiness_score")
            generation_duration_ms = result_data.get("generation_duration_ms")
            summary_sentence = result_data.get("summary_sentence")
            requirements_extracted = result_data.get("requirements_extracted", 0)
            test_cases_extracted = result_data.get("test_cases_extracted", 0)
            links_established = result_data.get("links_established", 0)
            orphans_detected = result_data.get("orphans_detected", 0)
        except (json.JSONDecodeError, TypeError):
            pass

    return JobStatusResponse(
        job_id=job.job_id,
        status=status,
        progress_percent=progress,
        current_phase=current_phase,
        requirements_extracted=requirements_extracted,
        test_cases_extracted=test_cases_extracted,
        links_established=links_established,
        orphans_detected=orphans_detected,
        error_message=job.error_message,
        matrix_id=matrix_id,
        total_requirements=total_requirements,
        total_test_cases=total_test_cases,
        total_links=total_links,
        coverage_percentage=coverage_percentage,
        orphan_requirements_count=orphan_requirements_count,
        orphan_test_cases_count=orphan_test_cases_count,
        compliance_readiness_score=compliance_readiness_score,
        generation_duration_ms=generation_duration_ms,
        summary_sentence=summary_sentence,
    )


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _determine_traceability_phase(progress_percent: int) -> str:
    """Determine the current traceability generation phase from progress."""
    if progress_percent <= 5:
        return "validating"
    elif progress_percent <= 30:
        return "extracting_requirements"
    elif progress_percent <= 60:
        return "extracting_test_cases"
    elif progress_percent <= 85:
        return "establishing_links"
    elif progress_percent <= 90:
        return "detecting_orphans"
    elif progress_percent <= 95:
        return "computing_metrics"
    else:
        return "persisting_matrix"
