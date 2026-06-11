"""FastAPI router for SLR Review management endpoints.

Provides endpoints for:
- Creating SLR Reviews (POST /)
- Listing reviews with pagination and filters (GET /)
- Getting full review details (GET /{review_id})
- Initiating screening runs (POST /{review_id}/screen)
- Listing screening decisions with filters (GET /{review_id}/decisions)
- Recording human overrides (PUT /{review_id}/decisions/{decision_id}/override)
- Getting real-time progress (GET /{review_id}/progress)
- Generating SLR summary reports (GET /{review_id}/report)

Exception handlers:
- ReviewNotFoundError → HTTP 404
- ProtocolNotFoundError → HTTP 404
- DecisionNotFoundError → HTTP 404
- InvalidStateTransitionError → HTTP 409

References:
    - Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.review.exceptions import (
    DecisionNotFoundError,
    InvalidStateTransitionError,
    ProtocolNotFoundError,
    ReviewNotFoundError,
)
from alcoabase.literature.review.models.screening_decision import (
    ScreeningDecision,
)
from alcoabase.literature.review.models.screening_run import ScreeningRun
from alcoabase.literature.review.schemas.decision import (
    HumanOverrideRequestSchema,
)
from alcoabase.literature.review.schemas.review import (
    SLRReviewCreateSchema,
)
from alcoabase.literature.review.services.slr_review_service import (
    SLRReviewService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/literature/reviews", tags=["Literature Reviews"])


# ─────────────────────────────────────────────────────────────────────────────
# Role-checking dependencies
# ─────────────────────────────────────────────────────────────────────────────


def _require_member():
    """Return a dependency enforcing at least member role.

    Returns:
        A FastAPI dependency function that raises HTTP 403 if the user
        does not have at least a member-level membership role.
    """

    async def _check(
        tenant: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        allowed_roles = {"member", "document_admin", "system_admin", "admin"}
        if tenant.membership_role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions. Requires at least member role.",
            )
        return tenant

    return _check


def _require_document_admin():
    """Return a dependency enforcing document_admin or higher role.

    Returns:
        A FastAPI dependency function that raises HTTP 403 if the user
        does not have document_admin, system_admin, or admin role.
    """

    async def _check(
        tenant: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        allowed_roles = {"document_admin", "system_admin", "admin"}
        if tenant.membership_role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="Requires document_admin or system_admin role.",
            )
        return tenant

    return _check


require_member = _require_member()
require_document_admin = _require_document_admin()


# ─────────────────────────────────────────────────────────────────────────────
# X-Company-Id header validation
# ─────────────────────────────────────────────────────────────────────────────


def _validate_company_header(
    x_company_id: str | None,
) -> None:
    """Validate that X-Company-Id header is present.

    Args:
        x_company_id: The X-Company-Id header value.

    Raises:
        HTTPException 400: If header is missing or empty.
    """
    if not x_company_id:
        raise HTTPException(
            status_code=400,
            detail="X-Company-Id header is required.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Service instantiation helper
# ─────────────────────────────────────────────────────────────────────────────


def _get_review_service() -> SLRReviewService:
    """Instantiate the SLR Review service.

    Returns:
        SLRReviewService instance.
    """
    return SLRReviewService()


# ─────────────────────────────────────────────────────────────────────────────
# POST / — Create SLR Review
# Requirements: 9.1
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "",
    status_code=201,
    summary="Create a new SLR Review",
    responses={
        404: {"description": "Protocol not found"},
    },
)
async def create_review(
    body: SLRReviewCreateSchema,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_document_admin),
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> JSONResponse:
    """Create a new Systematic Literature Review.

    Associates the review with a screening protocol and defines the
    set of records to screen via a filter. The review starts in
    ``protocol_defined`` state.

    Requires ``document_admin`` or higher role.

    Args:
        body: Request body with review creation fields.
        request: FastAPI request for app state access.
        session: Async database session.
        ctx: Resolved tenant context.
        x_company_id: Required company header.
        x_change_reason: Required audit trail reason (enforced by middleware).

    Returns:
        HTTP 201 with created review details.

    Raises:
        HTTPException 400: If X-Company-Id header is missing.
        HTTPException 404: If referenced protocol not found.
    """
    _validate_company_header(x_company_id)

    service = _get_review_service()

    try:
        result = await service.create_review(
            session,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            protocol_id=body.protocol_id,
            name=body.name,
            description=body.description,
            record_filter=body.record_filter,
        )
    except ProtocolNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    return JSONResponse(status_code=201, content=result)


# ─────────────────────────────────────────────────────────────────────────────
# GET / — List SLR Reviews
# Requirements: 9.2
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "",
    summary="List SLR Reviews with pagination and PRISMA summary",
)
async def list_reviews(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
    status: Annotated[
        str | None, Query(description="Filter by review status")
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Items per page (max 100)")
    ] = 20,
) -> JSONResponse:
    """List SLR Reviews for the current company with PRISMA flow summaries.

    Supports pagination and optional status filtering.

    Requires at least ``member`` role.

    Args:
        request: FastAPI request for app state access.
        session: Async database session.
        ctx: Resolved tenant context.
        x_company_id: Required company header.
        status: Optional status filter.
        page: Page number (1-indexed).
        page_size: Items per page (max 100).

    Returns:
        Paginated list of reviews with PRISMA summaries.

    Raises:
        HTTPException 400: If X-Company-Id header is missing.
    """
    _validate_company_header(x_company_id)

    service = _get_review_service()

    reviews, total_count = await service.list_reviews(
        session,
        company_id=ctx.company_id,
        status=status,
        page=page,
        page_size=page_size,
    )

    # Enrich each review with PRISMA flow summary
    enriched_reviews = []
    for review_data in reviews:
        try:
            prisma = await service.get_prisma_flow(
                session,
                review_id=review_data["id"],
                company_id=ctx.company_id,
            )
            review_data["prisma_flow"] = prisma
        except ReviewNotFoundError:
            review_data["prisma_flow"] = None
        enriched_reviews.append(review_data)

    return JSONResponse(
        content={
            "items": enriched_reviews,
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /{review_id} — Get SLR Review Details
# Requirements: 9.3
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{review_id}",
    summary="Get full SLR Review details",
    responses={
        404: {"description": "Review not found"},
    },
)
async def get_review(
    review_id: Annotated[int, Path(description="SLR Review ID")],
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
) -> JSONResponse:
    """Get full SLR Review details with PRISMA, progress, and inter-rater metrics.

    Returns comprehensive review information including the protocol reference,
    PRISMA flow statistics, progress metrics, and inter-rater reliability
    metrics (when human overrides exist).

    Requires at least ``member`` role.

    Args:
        review_id: SLR Review primary key.
        request: FastAPI request for app state access.
        session: Async database session.
        ctx: Resolved tenant context.
        x_company_id: Required company header.

    Returns:
        Full review details with enriched metrics.

    Raises:
        HTTPException 400: If X-Company-Id header is missing.
        HTTPException 404: If review not found.
    """
    _validate_company_header(x_company_id)

    service = _get_review_service()

    try:
        review_data = await service.get_review(
            session, review_id=review_id, company_id=ctx.company_id
        )

        # Enrich with PRISMA flow
        prisma = await service.get_prisma_flow(
            session, review_id=review_id, company_id=ctx.company_id
        )
        review_data["prisma_flow"] = prisma

        # Enrich with progress
        progress = await service.get_progress(
            session, review_id=review_id, company_id=ctx.company_id
        )
        review_data["progress"] = progress

        # Enrich with inter-rater reliability
        irr = await service.compute_inter_rater_reliability(
            session, review_id=review_id, company_id=ctx.company_id
        )
        review_data["inter_rater_reliability"] = irr

    except ReviewNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    return JSONResponse(content=review_data)


# ─────────────────────────────────────────────────────────────────────────────
# POST /{review_id}/screen — Initiate Screening Run
# Requirements: 9.4
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{review_id}/screen",
    status_code=202,
    summary="Initiate a screening run for the review",
    responses={
        404: {"description": "Review not found"},
        409: {"description": "Invalid state transition"},
    },
)
async def initiate_screening(
    review_id: Annotated[int, Path(description="SLR Review ID")],
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_document_admin),
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
    batch_size: Annotated[
        int, Query(ge=1, le=100, description="Records per batch (1–100)")
    ] = 20,
    re_screen_uncertain: Annotated[
        bool, Query(description="Whether to re-screen uncertain records only")
    ] = False,
) -> JSONResponse:
    """Initiate a screening run for the SLR Review.

    Creates a ScreeningRun record, transitions the review to
    screening_in_progress, and dispatches a Celery task for
    asynchronous execution.

    Requires ``document_admin`` or higher role.

    Args:
        review_id: SLR Review primary key.
        request: FastAPI request for app state access.
        session: Async database session.
        ctx: Resolved tenant context.
        x_company_id: Required company header.
        x_change_reason: Required audit trail reason (enforced by middleware).
        batch_size: Records per batch (1–100, default 20).
        re_screen_uncertain: Whether to re-screen uncertain records only.

    Returns:
        HTTP 202 with task_id for progress tracking.

    Raises:
        HTTPException 400: If X-Company-Id header is missing.
        HTTPException 404: If review not found.
        HTTPException 409: If review is not in a valid state for screening.
    """
    _validate_company_header(x_company_id)

    service = _get_review_service()

    try:
        result = await service.initiate_screening(
            session,
            review_id=review_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            batch_size=batch_size,
            re_screen_uncertain=re_screen_uncertain,
        )
    except ReviewNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=409, detail=e.message)

    return JSONResponse(status_code=202, content=result)


# ─────────────────────────────────────────────────────────────────────────────
# GET /{review_id}/decisions — List Screening Decisions
# Requirements: 9.5
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{review_id}/decisions",
    summary="List screening decisions with filters",
    responses={
        404: {"description": "Review not found"},
    },
)
async def list_decisions(
    review_id: Annotated[int, Path(description="SLR Review ID")],
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
    verdict: Annotated[
        str | None, Query(description="Filter by verdict (include, exclude, uncertain)")
    ] = None,
    confidence_min: Annotated[
        float | None, Query(ge=0.0, le=1.0, description="Minimum confidence score")
    ] = None,
    has_human_override: Annotated[
        bool | None, Query(description="Filter by presence of human override")
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Items per page (max 100)")
    ] = 20,
) -> JSONResponse:
    """List screening decisions for a review with pagination and filters.

    Supports filtering by verdict, minimum confidence score, and
    presence of human override.

    Requires at least ``member`` role.

    Args:
        review_id: SLR Review primary key.
        request: FastAPI request for app state access.
        session: Async database session.
        ctx: Resolved tenant context.
        x_company_id: Required company header.
        verdict: Optional verdict filter.
        confidence_min: Optional minimum confidence filter.
        has_human_override: Optional human override presence filter.
        page: Page number (1-indexed).
        page_size: Items per page (max 100).

    Returns:
        Paginated list of screening decisions.

    Raises:
        HTTPException 400: If X-Company-Id header is missing.
        HTTPException 404: If review not found.
    """
    _validate_company_header(x_company_id)

    # Validate review exists in this company
    service = _get_review_service()
    try:
        await service.get_review(
            session, review_id=review_id, company_id=ctx.company_id
        )
    except ReviewNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    # Get screening run IDs for this review
    run_ids_stmt = select(ScreeningRun.id).where(
        ScreeningRun.review_id == review_id,
        ScreeningRun.company_id == ctx.company_id,
    )

    # Build filter conditions for decisions
    conditions = [
        ScreeningDecision.screening_run_id.in_(run_ids_stmt),
        ScreeningDecision.company_id == ctx.company_id,
    ]

    if verdict is not None:
        conditions.append(ScreeningDecision.verdict == verdict)

    if confidence_min is not None:
        conditions.append(ScreeningDecision.confidence >= confidence_min)

    if has_human_override is True:
        conditions.append(ScreeningDecision.human_verdict.isnot(None))
    elif has_human_override is False:
        conditions.append(ScreeningDecision.human_verdict.is_(None))

    # Count total matching decisions
    count_stmt = select(func.count(ScreeningDecision.id)).where(*conditions)
    total_result = await session.execute(count_stmt)
    total_count = total_result.scalar_one()

    # Fetch paginated decisions
    offset = (page - 1) * page_size
    list_stmt = (
        select(ScreeningDecision)
        .where(*conditions)
        .order_by(ScreeningDecision.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(list_stmt)
    decisions = result.scalars().all()

    items = [_decision_to_response(d) for d in decisions]

    return JSONResponse(
        content={
            "items": items,
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# PUT /{review_id}/decisions/{decision_id}/override — Human Override
# Requirements: 9.6
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/{review_id}/decisions/{decision_id}/override",
    status_code=200,
    summary="Record a human override on a screening decision",
    responses={
        404: {"description": "Review or decision not found"},
    },
)
async def record_human_override(
    review_id: Annotated[int, Path(description="SLR Review ID")],
    decision_id: Annotated[int, Path(description="Screening Decision ID")],
    body: HumanOverrideRequestSchema,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_document_admin),
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> JSONResponse:
    """Record a human override on a screening decision.

    Stores the human verdict and rationale, recording the override with
    the reviewer's user_id and timestamp.

    Requires ``document_admin`` or higher role.

    Args:
        review_id: SLR Review primary key.
        decision_id: Screening Decision primary key.
        body: Human override payload with verdict and rationale.
        request: FastAPI request for app state access.
        session: Async database session.
        ctx: Resolved tenant context.
        x_company_id: Required company header.
        x_change_reason: Required audit trail reason (enforced by middleware).

    Returns:
        HTTP 200 with updated decision details.

    Raises:
        HTTPException 400: If X-Company-Id header is missing.
        HTTPException 404: If review or decision not found.
    """
    _validate_company_header(x_company_id)

    service = _get_review_service()

    try:
        result = await service.record_human_override(
            session,
            review_id=review_id,
            decision_id=decision_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            human_verdict=body.human_verdict,
            human_rationale=body.human_rationale,
        )
    except ReviewNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except DecisionNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    return JSONResponse(status_code=200, content=result)


# ─────────────────────────────────────────────────────────────────────────────
# GET /{review_id}/progress — Real-time Progress
# Requirements: 9.8
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{review_id}/progress",
    summary="Get real-time screening progress",
    responses={
        404: {"description": "Review not found"},
    },
)
async def get_progress(
    review_id: Annotated[int, Path(description="SLR Review ID")],
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
) -> JSONResponse:
    """Get real-time screening progress for an SLR Review.

    Returns progress metrics including total records, screened count,
    pending count, verdict breakdown, and estimated time remaining.

    Requires at least ``member`` role.

    Args:
        review_id: SLR Review primary key.
        request: FastAPI request for app state access.
        session: Async database session.
        ctx: Resolved tenant context.
        x_company_id: Required company header.

    Returns:
        Progress metrics as JSON.

    Raises:
        HTTPException 400: If X-Company-Id header is missing.
        HTTPException 404: If review not found.
    """
    _validate_company_header(x_company_id)

    service = _get_review_service()

    try:
        progress = await service.get_progress(
            session, review_id=review_id, company_id=ctx.company_id
        )
    except ReviewNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    return JSONResponse(content=progress)


# ─────────────────────────────────────────────────────────────────────────────
# GET /{review_id}/report — Generate SLR Report
# Requirements: 9.7
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{review_id}/report",
    summary="Generate and return the SLR summary report",
    responses={
        404: {"description": "Review not found"},
    },
)
async def get_report(
    review_id: Annotated[int, Path(description="SLR Review ID")],
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
) -> JSONResponse:
    """Generate and return the SLR summary report as JSON.

    Compiles review metadata, PRISMA flow, screening statistics,
    rationale summaries, and inter-rater reliability metrics into a
    comprehensive report suitable for regulatory submissions.

    Requires at least ``member`` role.

    Args:
        review_id: SLR Review primary key.
        request: FastAPI request for app state access.
        session: Async database session.
        ctx: Resolved tenant context.
        x_company_id: Required company header.

    Returns:
        SLR summary report as JSON.

    Raises:
        HTTPException 400: If X-Company-Id header is missing.
        HTTPException 404: If review not found.
    """
    _validate_company_header(x_company_id)

    service = _get_review_service()

    try:
        report = await service.generate_report(
            session, review_id=review_id, company_id=ctx.company_id
        )
    except ReviewNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    return JSONResponse(content=report)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Convert ScreeningDecision ORM to response dict
# ─────────────────────────────────────────────────────────────────────────────


def _decision_to_response(decision: ScreeningDecision) -> dict[str, Any]:
    """Convert a ScreeningDecision ORM instance to a JSON-serializable dict.

    Args:
        decision: The ScreeningDecision ORM instance.

    Returns:
        Dict suitable for JSON response.
    """
    return {
        "id": decision.id,
        "screening_run_id": decision.screening_run_id,
        "ingestion_record_id": decision.ingestion_record_id,
        "verdict": decision.verdict,
        "confidence": decision.confidence,
        "rationale": decision.rationale,
        "matched_inclusion_criteria": decision.matched_inclusion_criteria or [],
        "matched_exclusion_criteria": decision.matched_exclusion_criteria or [],
        "human_verdict": decision.human_verdict,
        "human_rationale": decision.human_rationale,
        "reviewer_user_id": decision.human_reviewer_id,
        "override_timestamp": (
            decision.human_override_at.isoformat()
            if decision.human_override_at
            else None
        ),
        "created_at": (
            decision.created_at.isoformat() if decision.created_at else None
        ),
    }
