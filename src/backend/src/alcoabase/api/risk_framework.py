"""FastAPI router for AI Risk & Compliance Framework endpoints.

Provides endpoints for managing AI task type registry, risk tier definitions,
company risk profiles, HITL checkpoints, operation logs, and dashboard
statistics.

All endpoints require X-Company-Id header (via TenantContext) and
system_admin or doc_admin role. Mutating endpoints (POST, PUT) require
X-Change-Reason header enforced by AuditMiddleware.

References:
    - Design: .kiro/specs/Step_8-1_ai-risk-compliance-framework/design.md
    - Requirements: 1.3, 1.4, 1.5, 2.4, 2.5, 2.6, 3.2, 3.3, 3.4, 3.9,
      5.1, 5.2, 5.8, 6.5, 6.7, 10.1–10.16
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.models.risk_framework import AIOperationLog
from alcoabase.models.user import Role, User, UserRole
from alcoabase.schemas.risk_framework import (
    AIOperationLogResponse,
    AITaskTypeDetailResponse,
    AITaskTypeResponse,
    CheckpointFilters,
    CompanyRiskProfileResponse,
    CreateProfileRequest,
    DashboardStatsResponse,
    HITLCheckpointResponse,
    PaginatedResult,
    ReviewCheckpointRequest,
    TierDefinitionResponse,
    UpdateProfileRequest,
)
from alcoabase.services.hitl_checkpoint_service import (
    CheckpointNotFoundError,
    CheckpointNotPendingError,
    ConcurrentReviewError,
    HITLCheckpointService,
    InsufficientReviewPermissionError,
    RejectionRequiresCommentsError,
)
from alcoabase.services.risk_classification_service import (
    RiskClassificationService,
    TIER_DEFINITIONS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/risk-framework", tags=["Risk Framework"])

# Module-level service instances
_risk_service = RiskClassificationService()
_hitl_service = HITLCheckpointService()


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def _require_risk_framework_role(
    tenant: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> TenantContext:
    """Verify the user has system_admin or doc_admin role.

    This dependency enforces that only users with system_admin or doc_admin
    role can access risk framework endpoints.

    Args:
        tenant: Resolved tenant context.
        session: Active async database session.

    Returns:
        TenantContext on successful authorization.

    Raises:
        HTTPException: 403 if the user lacks the required role.
    """
    stmt = (
        select(func.count())
        .select_from(User)
        .join(UserRole, User.id == UserRole.c.user_id)
        .join(Role, Role.id == UserRole.c.role_id)
        .where(
            and_(
                User.id == tenant.user_id,
                User.is_active.is_(True),
                Role.name.in_(["system_admin", "doc_admin"]),
                (Role.company_id == tenant.company_id) | (Role.company_id.is_(None)),
            )
        )
    )
    result = await session.execute(stmt)
    count = result.scalar_one()

    if count == 0:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions. Requires system_admin or doc_admin role.",
        )

    return tenant


# ---------------------------------------------------------------------------
# GET /task-types — Paginated list of AI task types
# ---------------------------------------------------------------------------


@router.get("/task-types", response_model=PaginatedResult[AITaskTypeResponse])
async def list_task_types(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(_require_risk_framework_role),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResult[AITaskTypeResponse]:
    """Return paginated list of AI task types for the current company.

    Includes both system-defined (global) task types and company-custom
    task types. Each entry includes the company-specific tier override
    if one exists in the active profile.

    Args:
        limit: Maximum items per page (1-100, default 20).
        offset: Number of items to skip (default 0).
        tenant: Resolved tenant context with role check.
        session: Database session.

    Returns:
        PaginatedResult containing AITaskTypeResponse items.
    """
    return await _risk_service.get_task_types(
        session=session,
        company_id=tenant.company_id,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# GET /task-types/{task_type_id} — Single task type detail
# ---------------------------------------------------------------------------


@router.get(
    "/task-types/{task_type_id}",
    response_model=AITaskTypeDetailResponse,
)
async def get_task_type(
    task_type_id: str,
    tenant: TenantContext = Depends(_require_risk_framework_role),
    session: AsyncSession = Depends(get_db_session),
) -> AITaskTypeDetailResponse:
    """Return full detail of a single AI task type.

    Includes risk factors, control set for the effective tier, and
    any company-specific tier override.

    Args:
        task_type_id: The task type string identifier.
        tenant: Resolved tenant context with role check.
        session: Database session.

    Returns:
        AITaskTypeDetailResponse with full details.

    Raises:
        HTTPException: 404 if the task type is not found.
    """
    try:
        return await _risk_service.get_task_type(
            session=session,
            task_type_id=task_type_id,
            company_id=tenant.company_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# GET /tiers — All tier definitions
# ---------------------------------------------------------------------------


@router.get("/tiers", response_model=list[TierDefinitionResponse])
async def list_tiers(
    tenant: TenantContext = Depends(_require_risk_framework_role),
) -> list[TierDefinitionResponse]:
    """Return all three tier definitions with their control sets.

    Returns static data from TIER_DEFINITIONS including all control
    measures, enforcement type, and applicable settings.

    Args:
        tenant: Resolved tenant context with role check.

    Returns:
        List of TierDefinitionResponse for high, medium, and low tiers.
    """
    return list(TIER_DEFINITIONS.values())


# ---------------------------------------------------------------------------
# GET /tiers/{tier_level} — Single tier definition
# ---------------------------------------------------------------------------


@router.get("/tiers/{tier_level}", response_model=TierDefinitionResponse)
async def get_tier(
    tier_level: str,
    tenant: TenantContext = Depends(_require_risk_framework_role),
) -> TierDefinitionResponse:
    """Return a single tier definition with its complete control set.

    Args:
        tier_level: The tier level (high, medium, or low).
        tenant: Resolved tenant context with role check.

    Returns:
        TierDefinitionResponse for the requested tier.

    Raises:
        HTTPException: 400 if tier_level is not valid.
    """
    if tier_level not in TIER_DEFINITIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid tier level: '{tier_level}'. "
                f"Valid values are: high, medium, low."
            ),
        )
    return TIER_DEFINITIONS[tier_level]


# ---------------------------------------------------------------------------
# POST /profiles — Create a Company Risk Profile
# ---------------------------------------------------------------------------


@router.post("/profiles", response_model=CompanyRiskProfileResponse, status_code=201)
async def create_profile(
    data: CreateProfileRequest,
    tenant: TenantContext = Depends(_require_risk_framework_role),
    session: AsyncSession = Depends(get_db_session),
) -> CompanyRiskProfileResponse:
    """Create a new Company Risk Profile.

    Deactivates any previous active profile for the company. Validates
    all override task_type_ids exist in the registry and enforces
    de-escalation rules.

    Requires X-Change-Reason header (enforced by AuditMiddleware).

    Args:
        data: Validated profile creation request.
        tenant: Resolved tenant context with role check.
        session: Database session.

    Returns:
        CompanyRiskProfileResponse for the created profile.

    Raises:
        HTTPException: 422 if validation fails.
    """
    try:
        result = await _risk_service.create_profile(
            session=session,
            company_id=tenant.company_id,
            data=data,
            user_id=tenant.user_id,
        )
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={"detail": "Validation error", "errors": [str(e)]},
        )


# ---------------------------------------------------------------------------
# GET /profiles — Active profile for the company
# ---------------------------------------------------------------------------


@router.get("/profiles", response_model=CompanyRiskProfileResponse)
async def get_active_profile(
    tenant: TenantContext = Depends(_require_risk_framework_role),
    session: AsyncSession = Depends(get_db_session),
) -> CompanyRiskProfileResponse:
    """Return the active Company Risk Profile for the current company.

    Args:
        tenant: Resolved tenant context with role check.
        session: Database session.

    Returns:
        CompanyRiskProfileResponse for the active profile.

    Raises:
        HTTPException: 404 if no active profile exists.
    """
    result = await _risk_service.get_active_profile(
        session=session,
        company_id=tenant.company_id,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No active risk profile configured for this company.",
        )
    return result


# ---------------------------------------------------------------------------
# PUT /profiles/{profile_id} — Update an existing profile
# ---------------------------------------------------------------------------


@router.put("/profiles/{profile_id}", response_model=CompanyRiskProfileResponse)
async def update_profile(
    profile_id: UUID,
    data: UpdateProfileRequest,
    tenant: TenantContext = Depends(_require_risk_framework_role),
    session: AsyncSession = Depends(get_db_session),
) -> CompanyRiskProfileResponse:
    """Update an existing Company Risk Profile.

    Supports partial updates. If overrides are provided, replaces all
    existing overrides (full replacement semantics).

    Requires X-Change-Reason header (enforced by AuditMiddleware).

    Args:
        profile_id: UUID of the profile to update.
        data: Validated partial update request.
        tenant: Resolved tenant context with role check.
        session: Database session.

    Returns:
        CompanyRiskProfileResponse for the updated profile.

    Raises:
        HTTPException: 404 if profile not found, 422 if validation fails.
    """
    try:
        result = await _risk_service.update_profile(
            session=session,
            profile_id=profile_id,
            company_id=tenant.company_id,
            data=data,
        )
        await session.commit()
        return result
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        raise HTTPException(
            status_code=422,
            detail={"detail": "Validation error", "errors": [error_msg]},
        )


# ---------------------------------------------------------------------------
# GET /profiles/history — Paginated profile history
# ---------------------------------------------------------------------------


@router.get(
    "/profiles/history",
    response_model=PaginatedResult[CompanyRiskProfileResponse],
)
async def get_profile_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(_require_risk_framework_role),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResult[CompanyRiskProfileResponse]:
    """Return paginated history of all profiles for the current company.

    Includes both active and deactivated profiles, ordered by
    created_at descending (most recent first).

    Args:
        limit: Maximum items per page (1-100, default 20).
        offset: Number of items to skip (default 0).
        tenant: Resolved tenant context with role check.
        session: Database session.

    Returns:
        PaginatedResult containing CompanyRiskProfileResponse items.
    """
    return await _risk_service.get_profile_history(
        session=session,
        company_id=tenant.company_id,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# GET /checkpoints — Paginated HITL checkpoints
# ---------------------------------------------------------------------------


@router.get("/checkpoints", response_model=PaginatedResult[HITLCheckpointResponse])
async def list_checkpoints(
    task_type_id: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None),
    assigned_reviewer: UUID | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(_require_risk_framework_role),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResult[HITLCheckpointResponse]:
    """Return paginated HITL checkpoints for the current company.

    Supports filtering by task_type_id, status, assigned_reviewer,
    and date range. Results are sorted by expires_at ascending
    (nearest expiry first).

    Args:
        task_type_id: Filter by AI task type identifier.
        status: Filter by checkpoint status (pending, approved, rejected, expired).
        assigned_reviewer: Filter by assigned reviewer UUID.
        start_date: Filter by creation date >= start_date (ISO 8601).
        end_date: Filter by creation date <= end_date (ISO 8601).
        limit: Maximum items per page (1-100, default 20).
        offset: Number of items to skip (default 0).
        tenant: Resolved tenant context with role check.
        session: Database session.

    Returns:
        PaginatedResult containing HITLCheckpointResponse items.
    """
    filters = CheckpointFilters(
        task_type_id=task_type_id,
        status=status,
        assigned_reviewer=assigned_reviewer,
        start_date=start_date,
        end_date=end_date,
    )
    return await _hitl_service.list_checkpoints(
        session=session,
        company_id=tenant.company_id,
        filters=filters,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# POST /checkpoints/{checkpoint_id}/review — Review a checkpoint
# ---------------------------------------------------------------------------


@router.post(
    "/checkpoints/{checkpoint_id}/review",
    response_model=HITLCheckpointResponse,
)
async def review_checkpoint(
    checkpoint_id: UUID,
    data: ReviewCheckpointRequest,
    tenant: TenantContext = Depends(_require_risk_framework_role),
    session: AsyncSession = Depends(get_db_session),
) -> HITLCheckpointResponse:
    """Review a HITL checkpoint (approve or reject).

    Only users with system_admin or doc_admin role can review.
    Checkpoint must be in "pending" status. Rejection requires
    non-empty reviewer_comments.

    Requires X-Change-Reason header (enforced by AuditMiddleware).

    Args:
        checkpoint_id: UUID of the checkpoint to review.
        data: Review action and comments.
        tenant: Resolved tenant context with role check.
        session: Database session.

    Returns:
        HITLCheckpointResponse for the updated checkpoint.

    Raises:
        HTTPException: 403 if insufficient role, 404 if not found,
            409 if already reviewed or concurrent review, 422 if
            rejection without comments.
    """
    try:
        result = await _hitl_service.review_checkpoint(
            session=session,
            checkpoint_id=checkpoint_id,
            company_id=tenant.company_id,
            user_id=tenant.user_id,
            action=data.action,
            comments=data.reviewer_comments,
            reviewed_sections=data.reviewed_sections,
        )
        await session.commit()
        return result
    except InsufficientReviewPermissionError:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions. Requires system_admin or doc_admin role.",
        )
    except CheckpointNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint '{checkpoint_id}' not found.",
        )
    except CheckpointNotPendingError as e:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Checkpoint is already in state '{e.current_status}'. "
                f"Only pending checkpoints can be reviewed."
            ),
        )
    except ConcurrentReviewError:
        raise HTTPException(
            status_code=409,
            detail="Checkpoint was already reviewed by another user.",
        )
    except RejectionRequiresCommentsError:
        raise HTTPException(
            status_code=422,
            detail="reviewer_comments is required when action is 'reject'.",
        )


# ---------------------------------------------------------------------------
# GET /operation-logs — Paginated operation logs
# ---------------------------------------------------------------------------


@router.get(
    "/operation-logs",
    response_model=PaginatedResult[AIOperationLogResponse],
)
async def list_operation_logs(
    task_type_id: str | None = Query(default=None, max_length=100),
    risk_tier: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(_require_risk_framework_role),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResult[AIOperationLogResponse]:
    """Return paginated AI operation logs for the current company.

    Supports filtering by task_type_id, risk_tier, user_id, and date
    range. Results are ordered by created_at descending (most recent first).

    Args:
        task_type_id: Filter by AI task type identifier.
        risk_tier: Filter by risk tier (high, medium, low).
        user_id: Filter by user who initiated the operation.
        start_date: Filter by created_at >= start_date (ISO 8601).
        end_date: Filter by created_at <= end_date (ISO 8601).
        limit: Maximum items per page (1-100, default 20).
        offset: Number of items to skip (default 0).
        tenant: Resolved tenant context with role check.
        session: Database session.

    Returns:
        PaginatedResult containing AIOperationLogResponse items.
    """
    # Clamp pagination parameters
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    # Build filter conditions
    conditions = [AIOperationLog.company_id == tenant.company_id]

    if task_type_id is not None:
        conditions.append(AIOperationLog.task_type_id == task_type_id)
    if risk_tier is not None:
        conditions.append(AIOperationLog.risk_tier == risk_tier)
    if user_id is not None:
        conditions.append(AIOperationLog.user_id == user_id)
    if start_date is not None:
        conditions.append(AIOperationLog.created_at >= start_date)
    if end_date is not None:
        conditions.append(AIOperationLog.created_at <= end_date)

    where_clause = and_(*conditions)

    # Count total matching records
    count_stmt = (
        select(func.count())
        .select_from(AIOperationLog)
        .where(where_clause)
    )
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    # Fetch paginated logs ordered by created_at descending
    query = (
        select(AIOperationLog)
        .where(where_clause)
        .order_by(AIOperationLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(query)
    logs = result.scalars().all()

    items = [
        AIOperationLogResponse(
            id=log.id,
            company_id=log.company_id,
            task_type_id=log.task_type_id,
            risk_tier=log.risk_tier,
            user_id=log.user_id,
            audit_depth=log.audit_depth,
            input_data=log.input_data,
            output_data=log.output_data,
            model_name=log.model_name,
            inference_duration_ms=log.inference_duration_ms,
            token_count_input=log.token_count_input,
            token_count_output=log.token_count_output,
            gate_result=log.gate_result,
            blocking_reason=log.blocking_reason,
            source_document_ids=log.source_document_ids,
            created_at=log.created_at,
        )
        for log in logs
    ]

    return PaginatedResult[AIOperationLogResponse](
        items=items, total=total, limit=limit, offset=offset
    )


# ---------------------------------------------------------------------------
# GET /dashboard-stats — Dashboard statistics
# ---------------------------------------------------------------------------


@router.get("/dashboard-stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    tenant: TenantContext = Depends(_require_risk_framework_role),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardStatsResponse:
    """Return dashboard statistics for the risk framework.

    Computes counts of AI operations by tier (last 30 days), pending
    and expired checkpoints, blocked operations, and active profile name.

    Args:
        tenant: Resolved tenant context with role check.
        session: Database session.

    Returns:
        DashboardStatsResponse with computed statistics.
    """
    return await _risk_service.get_dashboard_stats(
        session=session,
        company_id=tenant.company_id,
    )
