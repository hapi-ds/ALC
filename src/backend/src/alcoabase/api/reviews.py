"""FastAPI router for review pipeline endpoints.

Provides endpoints for submitting documents for multi-agent review,
listing review sessions, viewing session details, approving/rejecting
reviews, and managing action items.

Endpoints:
    - POST /api/reviews: Submit document for review (returns 202)
    - GET /api/reviews: List review sessions (paginated, filterable)
    - GET /api/reviews/{session_id}: Get session detail with reports
    - POST /api/reviews/{session_id}/approve: Approve review
    - POST /api/reviews/{session_id}/reject: Reject review
    - GET /api/reviews/{session_id}/action-items: List action items
    - POST /api/reviews/{session_id}/action-items: Create action item
    - PATCH /api/reviews/{session_id}/action-items/{item_id}: Update action item

References:
    - Requirements 10.1–10.8
    - Design: FastAPI Routers — Reviews Router
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.schemas.review import (
    ActionItemCreateRequest,
    ActionItemResponse,
    ActionItemUpdateRequest,
    ReviewSessionResponse,
    ReviewSubmitRequest,
)
from alcoabase.services.review_pipeline import ConflictError, ReviewPipelineService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviews", tags=["Reviews"])


# ---------------------------------------------------------------------------
# Dependency: ReviewPipelineService
# ---------------------------------------------------------------------------

_review_pipeline_service: ReviewPipelineService | None = None


def set_review_pipeline_service(service: ReviewPipelineService) -> None:
    """Set the module-level ReviewPipelineService instance.

    Called during application startup to wire the service into the router.

    Args:
        service: The initialized ReviewPipelineService instance.
    """
    global _review_pipeline_service
    _review_pipeline_service = service


def get_review_pipeline_service() -> ReviewPipelineService:
    """Provide the ReviewPipelineService as a FastAPI dependency.

    Returns:
        The module-level ReviewPipelineService instance.

    Raises:
        HTTPException 503: If the service has not been initialized.
    """
    if _review_pipeline_service is None:
        raise HTTPException(
            status_code=503,
            detail="Review pipeline service is not available.",
        )
    return _review_pipeline_service


# ---------------------------------------------------------------------------
# Review Session Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=202)
async def submit_review(
    request: ReviewSubmitRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ReviewPipelineService = Depends(get_review_pipeline_service),
) -> dict:
    """Submit a document for multi-agent review.

    Creates a new review session and dispatches agent review tasks
    in parallel via Celery. Returns HTTP 202 (Accepted) with the
    session ID.

    Args:
        request: Review submission request body.
        tenant: Resolved tenant context (company_id, user_id).
        service: ReviewPipelineService dependency.

    Returns:
        Dict with session_id and status "Pending".

    Raises:
        HTTPException 409: If document already has an active review session.
    """
    try:
        session = await service.submit_review(
            document_id=request.document_id,
            document_version_id=request.document_version_id,
            audit_profile_id=request.audit_profile_id,
            company_id=tenant.company_id,
            user_id=tenant.user_id,
        )
    except ConflictError:
        raise HTTPException(
            status_code=409,
            detail="Document already has an active review session",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {"session_id": session.id, "status": session.status}


@router.get("", response_model=dict)
async def list_reviews(
    status: str | None = Query(default=None, description="Filter by status"),
    document_type: str | None = Query(default=None, description="Filter by document type"),
    date_from: datetime | None = Query(default=None, description="Filter from date"),
    date_to: datetime | None = Query(default=None, description="Filter to date"),
    min_score: float | None = Query(default=None, ge=0.0, le=100.0, description="Minimum compliance score"),
    max_score: float | None = Query(default=None, ge=0.0, le=100.0, description="Maximum compliance score"),
    limit: int = Query(default=20, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    tenant: TenantContext = Depends(get_tenant_context),
    service: ReviewPipelineService = Depends(get_review_pipeline_service),
) -> dict:
    """List review sessions for the current company.

    Supports pagination and filtering by status, document type,
    date range, and compliance score range.

    Args:
        status: Optional status filter.
        document_type: Optional document type filter.
        date_from: Optional start date filter.
        date_to: Optional end date filter.
        min_score: Optional minimum compliance score filter.
        max_score: Optional maximum compliance score filter.
        limit: Page size (default 20, max 100).
        offset: Page offset (default 0).
        tenant: Resolved tenant context (company_id).
        service: ReviewPipelineService dependency.

    Returns:
        Dict with items list and total count.
    """
    sessions, total = await service.list_sessions(
        company_id=tenant.company_id,
        status=status,
        document_type=document_type,
        date_from=date_from,
        date_to=date_to,
        min_score=min_score,
        max_score=max_score,
        limit=limit,
        offset=offset,
    )

    return {
        "items": [
            ReviewSessionResponse.model_validate(s, from_attributes=True)
            for s in sessions
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{session_id}", response_model=ReviewSessionResponse)
async def get_review_session(
    session_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ReviewPipelineService = Depends(get_review_pipeline_service),
) -> ReviewSessionResponse:
    """Get full review session detail including agent reports and master summary.

    Args:
        session_id: The review session primary key.
        tenant: Resolved tenant context (company_id).
        service: ReviewPipelineService dependency.

    Returns:
        Full review session detail.

    Raises:
        HTTPException 404: If session not found or wrong company.
    """
    session = await service.get_session(
        session_id=session_id, company_id=tenant.company_id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Review session not found")

    return ReviewSessionResponse.model_validate(session, from_attributes=True)


@router.post("/{session_id}/approve", response_model=ReviewSessionResponse)
async def approve_review(
    session_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ReviewPipelineService = Depends(get_review_pipeline_service),
) -> ReviewSessionResponse:
    """Approve a completed review session.

    Only sessions with status "Completed" can be approved.

    Args:
        session_id: The review session primary key.
        tenant: Resolved tenant context (company_id).
        service: ReviewPipelineService dependency.

    Returns:
        The updated review session.

    Raises:
        HTTPException 404: If session not found or wrong company.
        HTTPException 409: If session is not in Completed status.
    """
    try:
        session = await service.approve_session(
            session_id=session_id, company_id=tenant.company_id
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail="Review session not found")
        raise HTTPException(status_code=409, detail=error_msg)

    return ReviewSessionResponse.model_validate(session, from_attributes=True)


@router.post("/{session_id}/reject", response_model=ReviewSessionResponse)
async def reject_review(
    session_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ReviewPipelineService = Depends(get_review_pipeline_service),
) -> ReviewSessionResponse:
    """Reject a completed review session.

    Only sessions with status "Completed" can be rejected.

    Args:
        session_id: The review session primary key.
        tenant: Resolved tenant context (company_id).
        service: ReviewPipelineService dependency.

    Returns:
        The updated review session.

    Raises:
        HTTPException 404: If session not found or wrong company.
        HTTPException 409: If session is not in Completed status.
    """
    try:
        session = await service.reject_session(
            session_id=session_id, company_id=tenant.company_id
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail="Review session not found")
        raise HTTPException(status_code=409, detail=error_msg)

    return ReviewSessionResponse.model_validate(session, from_attributes=True)


# ---------------------------------------------------------------------------
# Action Item Endpoints
# ---------------------------------------------------------------------------


@router.get("/{session_id}/action-items", response_model=list[ActionItemResponse])
async def list_action_items(
    session_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ReviewPipelineService = Depends(get_review_pipeline_service),
) -> list[ActionItemResponse]:
    """List action items for a review session.

    Args:
        session_id: The review session primary key.
        tenant: Resolved tenant context (company_id).
        service: ReviewPipelineService dependency.

    Returns:
        List of action items for the session.

    Raises:
        HTTPException 404: If session not found or wrong company.
    """
    try:
        items = await service.list_action_items(
            session_id=session_id, company_id=tenant.company_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return [
        ActionItemResponse.model_validate(item, from_attributes=True)
        for item in items
    ]


@router.post(
    "/{session_id}/action-items",
    response_model=ActionItemResponse,
    status_code=201,
)
async def create_action_item(
    session_id: int,
    request: ActionItemCreateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ReviewPipelineService = Depends(get_review_pipeline_service),
) -> ActionItemResponse:
    """Create a new action item from a review finding.

    Args:
        session_id: The review session primary key.
        request: Action item creation request body.
        tenant: Resolved tenant context (company_id).
        service: ReviewPipelineService dependency.

    Returns:
        The created action item with HTTP 201.

    Raises:
        HTTPException 404: If session not found or wrong company.
    """
    try:
        item = await service.create_action_item(
            session_id=session_id,
            finding_id=request.finding_id,
            title=request.title,
            description=request.description,
            severity=request.severity,
            assigned_to=request.assigned_to,
            company_id=tenant.company_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return ActionItemResponse.model_validate(item, from_attributes=True)


@router.patch(
    "/{session_id}/action-items/{item_id}",
    response_model=ActionItemResponse,
)
async def update_action_item(
    session_id: int,
    item_id: int,
    request: ActionItemUpdateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: ReviewPipelineService = Depends(get_review_pipeline_service),
) -> ActionItemResponse:
    """Update an action item's status.

    Args:
        session_id: The review session primary key.
        item_id: The action item primary key.
        request: Action item update request body.
        tenant: Resolved tenant context (company_id).
        service: ReviewPipelineService dependency.

    Returns:
        The updated action item.

    Raises:
        HTTPException 404: If session or action item not found.
    """
    try:
        item = await service.update_action_item(
            session_id=session_id,
            item_id=item_id,
            status=request.status,
            resolution_note=request.resolution_note,
            company_id=tenant.company_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return ActionItemResponse.model_validate(item, from_attributes=True)
