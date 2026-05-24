"""FastAPI router for AI Training Planner endpoints.

Provides endpoints for:
- POST /api/training/planner/generate — Request async schedule generation
- GET /api/training/planner/schedule/{user_id} — Get user's training schedule
- GET /api/training/planner/gaps — Company-wide skill gap report
- GET /api/training/planner/gaps/{user_id} — Individual user skill gaps

All endpoints are scoped to the company identified by the X-Company-Id header
via the TenantContext dependency. The AuditMiddleware enforces X-Change-Reason
on POST requests.

References:
    - Design doc Section 7: Training Planner Router
    - Requirements 1.6, 1.7, 1.8, 2.1, 2.4, 2.6, 2.7, 2.8
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.models.document import Document
from alcoabase.schemas.training_ecosystem import (
    CompanyGapReportResponse,
    JobAcceptedResponse,
    ScheduleGenerateRequest,
    SkillGapResponse,
    TrainingScheduleResponse,
)
from alcoabase.services.training_planner import TrainingPlannerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/training/planner", tags=["training-planner"])


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_training_planner_service() -> TrainingPlannerService:
    """Provide the TrainingPlannerService as a FastAPI dependency.

    Uses the service factory to obtain the shared InferenceClient and
    AgentRegistryService, combined with the database session factory.

    Returns:
        A properly wired TrainingPlannerService instance.
    """
    from alcoabase.database import _session_factory
    from alcoabase.services.service_factory import get_inference_client

    # AgentRegistryService is wired at app startup; import the getter
    from alcoabase.api.agents import get_agent_registry_service

    if _session_factory is None:
        raise RuntimeError(
            "Database not initialized. Call init_db() during application startup."
        )

    return TrainingPlannerService(
        session_factory=_session_factory,
        inference_client=get_inference_client(),
        agent_registry=get_agent_registry_service(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/generate",
    response_model=JobAcceptedResponse,
    status_code=202,
    summary="Request training schedule generation",
    description=(
        "Dispatches an async Celery task to generate a personalized training "
        "schedule for the specified user. Requires X-Change-Reason header."
    ),
)
async def generate_schedule(
    request: ScheduleGenerateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: TrainingPlannerService = Depends(get_training_planner_service),
) -> JobAcceptedResponse:
    """Request async schedule generation for a user.

    The X-Change-Reason header is enforced by the AuditMiddleware for
    all POST requests.

    Args:
        request: Request body containing user_id.
        tenant: Resolved tenant context (company_id from X-Company-Id).
        service: TrainingPlannerService dependency.

    Returns:
        HTTP 202 with job_id and status "pending".

    Raises:
        HTTPException 404: If user does not exist.
        HTTPException 400: If user has no assigned documents.
    """
    job_id = await service.request_schedule_generation(
        user_id=request.user_id,
        company_id=tenant.company_id,
    )
    return JobAcceptedResponse(job_id=job_id, status="pending")


@router.get(
    "/schedule/{user_id}",
    response_model=TrainingScheduleResponse,
    summary="Get user's training schedule",
    description=(
        "Returns the current training schedule for a user including "
        "compliance percentage, completed items, and schedule data."
    ),
)
async def get_schedule(
    user_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: TrainingPlannerService = Depends(get_training_planner_service),
) -> TrainingScheduleResponse:
    """Retrieve the current training schedule for a user.

    Args:
        user_id: The user's primary key.
        tenant: Resolved tenant context (company_id from X-Company-Id).
        service: TrainingPlannerService dependency.

    Returns:
        The user's training schedule with compliance percentage.

    Raises:
        HTTPException 404: If no schedule exists for the user.
    """
    schedule = await service.get_schedule(
        user_id=user_id,
        company_id=tenant.company_id,
    )
    if schedule is None:
        raise HTTPException(
            status_code=404,
            detail=f"No training schedule found for user {user_id}.",
        )
    return TrainingScheduleResponse.model_validate(schedule)


@router.get(
    "/gaps",
    response_model=CompanyGapReportResponse,
    summary="Company-wide skill gap report",
    description=(
        "Returns an aggregated skill gap report for the current company "
        "with pagination support for top-documents and top-users lists."
    ),
)
async def get_company_gaps(
    limit: int = Query(default=20, ge=1, le=100, description="Max items per list"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    tenant: TenantContext = Depends(get_tenant_context),
    service: TrainingPlannerService = Depends(get_training_planner_service),
) -> CompanyGapReportResponse:
    """Get company-wide skill gap report.

    Args:
        limit: Maximum number of items in top lists (default 20, max 100).
        offset: Offset for pagination (default 0).
        tenant: Resolved tenant context (company_id from X-Company-Id).
        service: TrainingPlannerService dependency.

    Returns:
        Aggregated gap report with compliance percentages and top lists.
    """
    report = await service.get_company_gaps(
        company_id=tenant.company_id,
        limit=limit,
        offset=offset,
    )
    return CompanyGapReportResponse(**report)


@router.get(
    "/gaps/{user_id}",
    response_model=list[SkillGapResponse],
    summary="Individual user skill gaps",
    description=(
        "Returns the skill gap detail for a specific user including "
        "documents requiring training, priority, and access blocking status."
    ),
)
async def get_user_gaps(
    user_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: TrainingPlannerService = Depends(get_training_planner_service),
    session: AsyncSession = Depends(get_db_session),
) -> list[SkillGapResponse]:
    """Get individual skill gaps for a user.

    Args:
        user_id: The user's primary key.
        tenant: Resolved tenant context (company_id from X-Company-Id).
        service: TrainingPlannerService dependency.
        session: Database session for document title lookup.

    Returns:
        List of skill gaps with document titles and priority levels.

    Raises:
        HTTPException 404: If user does not exist.
    """
    gaps = await service.get_user_gaps(
        user_id=user_id,
        company_id=tenant.company_id,
    )

    # Enrich gaps with document titles
    result: list[SkillGapResponse] = []
    for gap in gaps:
        # Look up document title
        doc_result = await session.execute(
            select(Document.title).where(Document.id == gap.document_id)
        )
        doc_title = doc_result.scalar_one_or_none() or "Unknown Document"

        result.append(
            SkillGapResponse(
                id=gap.id,
                document_id=gap.document_id,
                document_title=doc_title,
                gap_type=gap.gap_type.value if hasattr(gap.gap_type, "value") else str(gap.gap_type),
                priority=gap.priority.value if hasattr(gap.priority, "value") else str(gap.priority),
                days_overdue=gap.days_overdue,
                blocks_access=gap.blocks_access,
                identified_at=gap.identified_at,
            )
        )

    return result
