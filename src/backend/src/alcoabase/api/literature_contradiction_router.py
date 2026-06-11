"""FastAPI router for Contradiction Alert and Novelty Flag endpoints.

Provides endpoints for:
- Listing contradiction alerts with filters (GET /contradictions)
- Contradiction summary statistics (GET /contradictions/summary)
- Getting full alert details (GET /contradictions/{alert_id})
- Updating alert status (PUT /contradictions/{alert_id}/status)
- Listing novelty flags with filters (GET /novelty)
- Updating novelty flag status (PUT /novelty/{flag_id}/status)

Exception handlers:
- AlertNotFoundError → HTTP 404
- FlagNotFoundError → HTTP 404
- InvalidStateTransitionError → HTTP 409

References:
    - Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from math import ceil
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from sqlalchemy import case, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.review.exceptions import (
    AlertNotFoundError,
    FlagNotFoundError,
)
from alcoabase.literature.review.models.contradiction_alert import (
    ContradictionAlert,
)
from alcoabase.literature.review.models.novelty_flag import NoveltyFlag
from alcoabase.literature.review.schemas.contradiction import (
    ContradictionStatusUpdateSchema,
    ContradictionSummarySchema,
)
from alcoabase.literature.review.schemas.novelty import (
    NoveltyStatusUpdateSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/literature", tags=["Literature Contradictions & Novelty"])


# ─────────────────────────────────────────────────────────────────────────────
# Valid state transitions
# ─────────────────────────────────────────────────────────────────────────────

CONTRADICTION_TRANSITIONS: dict[str, list[str]] = {
    "new": ["acknowledged"],
    "acknowledged": ["resolved", "dismissed"],
}

NOVELTY_TRANSITIONS: dict[str, list[str]] = {
    "new": ["acknowledged"],
    "acknowledged": ["integrated", "dismissed"],
}


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


def _validate_company_header(x_company_id: str | None) -> None:
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
# X-Change-Reason header validation
# ─────────────────────────────────────────────────────────────────────────────


def _validate_change_reason_header(x_change_reason: str | None) -> None:
    """Validate that X-Change-Reason header is present for mutations.

    Args:
        x_change_reason: The X-Change-Reason header value.

    Raises:
        HTTPException 400: If header is missing or empty.
    """
    if not x_change_reason:
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header is required for mutating requests.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# GET /contradictions — List Contradiction Alerts
# Requirements: 10.1
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/contradictions",
    summary="List contradiction alerts with pagination and filters",
)
async def list_contradictions(
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
    severity: Annotated[
        str | None,
        Query(description="Filter by severity (critical, major, minor)"),
    ] = None,
    status: Annotated[
        str | None,
        Query(description="Filter by status (new, acknowledged, resolved, dismissed)"),
    ] = None,
    ingestion_record_id: Annotated[
        int | None,
        Query(description="Filter by ingestion record ID"),
    ] = None,
    internal_document_id: Annotated[
        str | None,
        Query(description="Filter by internal document ID"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Items per page (max 100)")
    ] = 20,
) -> dict[str, Any]:
    """List contradiction alerts for the current company with filters.

    Results are ordered by severity descending (critical > major > minor)
    then by created_at descending.

    Requires at least ``member`` role.

    Args:
        session: Async database session.
        ctx: Resolved tenant context.
        x_company_id: Required company header.
        severity: Optional severity filter.
        status: Optional status filter.
        ingestion_record_id: Optional ingestion record filter.
        internal_document_id: Optional internal document filter.
        page: Page number (1-indexed).
        page_size: Items per page (max 100).

    Returns:
        Paginated list of contradiction alerts.

    Raises:
        HTTPException 400: If X-Company-Id header is missing.
    """
    _validate_company_header(x_company_id)

    conditions = [ContradictionAlert.company_id == ctx.company_id]

    if severity is not None:
        conditions.append(ContradictionAlert.severity == severity)
    if status is not None:
        conditions.append(ContradictionAlert.status == status)
    if ingestion_record_id is not None:
        conditions.append(
            ContradictionAlert.ingestion_record_id == ingestion_record_id
        )
    if internal_document_id is not None:
        conditions.append(
            ContradictionAlert.internal_document_id == internal_document_id
        )

    # Count total
    count_stmt = select(func.count(ContradictionAlert.id)).where(*conditions)
    total_result = await session.execute(count_stmt)
    total_count = total_result.scalar_one()

    # Severity ordering: critical=1, major=2, minor=3 (ascending → severity desc)
    severity_order = case(
        (ContradictionAlert.severity == "critical", 1),
        (ContradictionAlert.severity == "major", 2),
        (ContradictionAlert.severity == "minor", 3),
        else_=4,
    )

    offset = (page - 1) * page_size
    list_stmt = (
        select(ContradictionAlert)
        .where(*conditions)
        .order_by(severity_order.asc(), ContradictionAlert.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(list_stmt)
    alerts = result.scalars().all()

    items = [_alert_to_response(a) for a in alerts]
    total_pages = ceil(total_count / page_size) if total_count > 0 else 0

    return {
        "items": items,
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /contradictions/summary — Contradiction Summary Statistics
# Requirements: 10.3
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/contradictions/summary",
    summary="Get contradiction alert summary statistics",
    response_model=ContradictionSummarySchema,
)
async def get_contradiction_summary(
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
) -> dict[str, Any]:
    """Get aggregate statistics for contradiction alerts.

    Returns total open alerts by severity, resolved count this month,
    average time to resolution, and top affected documents.

    Requires at least ``member`` role.

    Args:
        session: Async database session.
        ctx: Resolved tenant context.
        x_company_id: Required company header.

    Returns:
        Contradiction summary statistics.

    Raises:
        HTTPException 400: If X-Company-Id header is missing.
    """
    _validate_company_header(x_company_id)

    company_id = ctx.company_id

    # 1. Total open by severity (status: new or acknowledged)
    open_severity_stmt = (
        select(
            ContradictionAlert.severity,
            func.count(ContradictionAlert.id),
        )
        .where(
            ContradictionAlert.company_id == company_id,
            ContradictionAlert.status.in_(["new", "acknowledged"]),
        )
        .group_by(ContradictionAlert.severity)
    )
    open_result = await session.execute(open_severity_stmt)
    total_open_by_severity: dict[str, int] = {}
    for sev, count in open_result.all():
        total_open_by_severity[sev] = count

    # 2. Resolved this month
    now = datetime.now(timezone.utc)
    resolved_stmt = (
        select(func.count(ContradictionAlert.id))
        .where(
            ContradictionAlert.company_id == company_id,
            ContradictionAlert.status == "resolved",
            ContradictionAlert.resolved_at.isnot(None),
            extract("year", ContradictionAlert.resolved_at) == now.year,
            extract("month", ContradictionAlert.resolved_at) == now.month,
        )
    )
    resolved_result = await session.execute(resolved_stmt)
    resolved_this_month = resolved_result.scalar_one()

    # 3. Average time to resolution (hours)
    avg_resolution_stmt = (
        select(
            func.avg(
                extract(
                    "epoch",
                    ContradictionAlert.resolved_at - ContradictionAlert.created_at,
                )
            )
        )
        .where(
            ContradictionAlert.company_id == company_id,
            ContradictionAlert.status == "resolved",
            ContradictionAlert.resolved_at.isnot(None),
        )
    )
    avg_result = await session.execute(avg_resolution_stmt)
    avg_seconds = avg_result.scalar_one()
    avg_time_to_resolution_hours: float | None = None
    if avg_seconds is not None:
        avg_time_to_resolution_hours = round(avg_seconds / 3600.0, 2)

    # 4. Top affected documents (top 10 by alert count)
    top_docs_stmt = (
        select(
            ContradictionAlert.internal_document_id,
            func.count(ContradictionAlert.id).label("alert_count"),
        )
        .where(ContradictionAlert.company_id == company_id)
        .group_by(ContradictionAlert.internal_document_id)
        .order_by(func.count(ContradictionAlert.id).desc())
        .limit(10)
    )
    top_docs_result = await session.execute(top_docs_stmt)
    top_affected_docs: list[dict[str, Any]] = []
    for doc_id, alert_count in top_docs_result.all():
        top_affected_docs.append(
            {"internal_document_id": doc_id, "alert_count": alert_count}
        )

    return {
        "total_open_by_severity": total_open_by_severity,
        "resolved_this_month": resolved_this_month,
        "avg_time_to_resolution_hours": avg_time_to_resolution_hours,
        "top_affected_docs": top_affected_docs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /contradictions/{alert_id} — Get Alert Details
# Requirements: 10.2
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/contradictions/{alert_id}",
    summary="Get full contradiction alert details",
    responses={
        404: {"description": "Alert not found"},
    },
)
async def get_contradiction(
    alert_id: Annotated[int, Path(description="Contradiction Alert ID")],
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
) -> dict[str, Any]:
    """Get full contradiction alert details.

    Includes literature/internal doc metadata, status history,
    and linked impact report reference.

    Returns HTTP 404 for cross-tenant access attempts (not 403).

    Requires at least ``member`` role.

    Args:
        alert_id: Contradiction Alert primary key.
        session: Async database session.
        ctx: Resolved tenant context.
        x_company_id: Required company header.

    Returns:
        Full alert details.

    Raises:
        HTTPException 400: If X-Company-Id header is missing.
        HTTPException 404: If alert not found or belongs to different company.
    """
    _validate_company_header(x_company_id)

    try:
        alert = await _get_alert_or_404(session, alert_id, ctx.company_id)
    except AlertNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    return _alert_to_detail_response(alert)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /contradictions/{alert_id}/status — Update Alert Status
# Requirements: 10.4
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/contradictions/{alert_id}/status",
    summary="Update contradiction alert status",
    responses={
        404: {"description": "Alert not found"},
        409: {"description": "Invalid state transition"},
    },
)
async def update_contradiction_status(
    alert_id: Annotated[int, Path(description="Contradiction Alert ID")],
    body: ContradictionStatusUpdateSchema,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_document_admin),
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> dict[str, Any]:
    """Update the status of a contradiction alert.

    Enforces state transitions:
        new → acknowledged → (resolved | dismissed)

    Dismissing requires document_admin or system_admin role.
    Requires ``X-Change-Reason`` header.

    Args:
        alert_id: Contradiction Alert primary key.
        body: Status update payload with new status and optional notes.
        session: Async database session.
        ctx: Resolved tenant context.
        x_company_id: Required company header.
        x_change_reason: Required change reason for audit.

    Returns:
        Updated alert details.

    Raises:
        HTTPException 400: If X-Company-Id or X-Change-Reason missing.
        HTTPException 403: If dismiss attempted without proper role.
        HTTPException 404: If alert not found or belongs to different company.
        HTTPException 409: If state transition is invalid.
    """
    _validate_company_header(x_company_id)
    _validate_change_reason_header(x_change_reason)

    # Enforce dismiss requires document_admin or system_admin
    if body.status == "dismissed":
        dismiss_roles = {"document_admin", "system_admin", "admin"}
        if ctx.membership_role not in dismiss_roles:
            raise HTTPException(
                status_code=403,
                detail="Dismissing alerts requires document_admin or system_admin role.",
            )

    try:
        alert = await _get_alert_or_404(session, alert_id, ctx.company_id)
    except AlertNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    # Validate state transition
    current_status = alert.status
    allowed_targets = CONTRADICTION_TRANSITIONS.get(current_status, [])
    if body.status not in allowed_targets:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot transition from '{current_status}' to '{body.status}'. "
                f"Allowed transitions: {allowed_targets}"
            ),
        )

    # Apply status update
    now = datetime.now(timezone.utc)
    alert.status = body.status

    if body.status == "acknowledged":
        alert.acknowledged_by = ctx.user_id
        alert.acknowledged_at = now
    elif body.status == "resolved":
        alert.resolution_note = body.resolution_note
        alert.change_request_id = body.change_request_id
        alert.resolved_by = ctx.user_id
        alert.resolved_at = now
    elif body.status == "dismissed":
        alert.dismissal_reason = body.dismissal_reason
        alert.dismissed_by = ctx.user_id
        alert.dismissed_at = now

    await session.commit()
    await session.refresh(alert)

    return _alert_to_detail_response(alert)


# ─────────────────────────────────────────────────────────────────────────────
# GET /novelty — List Novelty Flags
# Requirements: 10.5
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/novelty",
    summary="List novelty flags with pagination and filters",
)
async def list_novelty_flags(
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
    status: Annotated[
        str | None,
        Query(description="Filter by status (new, acknowledged, integrated, dismissed)"),
    ] = None,
    relevance_score_min: Annotated[
        float | None,
        Query(ge=0.0, le=1.0, description="Minimum relevance score filter"),
    ] = None,
    high_priority: Annotated[
        bool | None,
        Query(description="Filter by high priority flag"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Items per page (max 100)")
    ] = 20,
) -> dict[str, Any]:
    """List novelty flags for the current company with filters.

    Results are ordered by relevance_score descending then
    created_at descending.

    Requires at least ``member`` role.

    Args:
        session: Async database session.
        ctx: Resolved tenant context.
        x_company_id: Required company header.
        status: Optional status filter.
        relevance_score_min: Optional minimum relevance score filter.
        high_priority: Optional high priority filter.
        page: Page number (1-indexed).
        page_size: Items per page (max 100).

    Returns:
        Paginated list of novelty flags.

    Raises:
        HTTPException 400: If X-Company-Id header is missing.
    """
    _validate_company_header(x_company_id)

    conditions = [NoveltyFlag.company_id == ctx.company_id]

    if status is not None:
        conditions.append(NoveltyFlag.status == status)
    if relevance_score_min is not None:
        conditions.append(NoveltyFlag.relevance_score >= relevance_score_min)
    if high_priority is not None:
        conditions.append(NoveltyFlag.high_priority == high_priority)

    # Count total
    count_stmt = select(func.count(NoveltyFlag.id)).where(*conditions)
    total_result = await session.execute(count_stmt)
    total_count = total_result.scalar_one()

    offset = (page - 1) * page_size
    list_stmt = (
        select(NoveltyFlag)
        .where(*conditions)
        .order_by(
            NoveltyFlag.relevance_score.desc(),
            NoveltyFlag.created_at.desc(),
        )
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(list_stmt)
    flags = result.scalars().all()

    items = [_flag_to_response(f) for f in flags]
    total_pages = ceil(total_count / page_size) if total_count > 0 else 0

    return {
        "items": items,
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PUT /novelty/{flag_id}/status — Update Novelty Flag Status
# Requirements: 10.6
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/novelty/{flag_id}/status",
    summary="Update novelty flag status",
    responses={
        404: {"description": "Flag not found"},
        409: {"description": "Invalid state transition"},
    },
)
async def update_novelty_status(
    flag_id: Annotated[int, Path(description="Novelty Flag ID")],
    body: NoveltyStatusUpdateSchema,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_document_admin),
    x_company_id: Annotated[str | None, Header(alias="X-Company-Id")] = None,
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> dict[str, Any]:
    """Update the status of a novelty flag.

    Enforces state transitions:
        new → acknowledged → (integrated | dismissed)

    Requires ``document_admin`` role and ``X-Change-Reason`` header.

    Args:
        flag_id: Novelty Flag primary key.
        body: Status update payload with new status and optional fields.
        session: Async database session.
        ctx: Resolved tenant context.
        x_company_id: Required company header.
        x_change_reason: Required change reason for audit.

    Returns:
        Updated flag details.

    Raises:
        HTTPException 400: If X-Company-Id or X-Change-Reason missing.
        HTTPException 404: If flag not found or belongs to different company.
        HTTPException 409: If state transition is invalid.
    """
    _validate_company_header(x_company_id)
    _validate_change_reason_header(x_change_reason)

    try:
        flag = await _get_flag_or_404(session, flag_id, ctx.company_id)
    except FlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    # Validate state transition
    current_status = flag.status
    allowed_targets = NOVELTY_TRANSITIONS.get(current_status, [])
    if body.status not in allowed_targets:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot transition from '{current_status}' to '{body.status}'. "
                f"Allowed transitions: {allowed_targets}"
            ),
        )

    # Apply status update
    now = datetime.now(timezone.utc)
    flag.status = body.status

    if body.status == "acknowledged":
        flag.acknowledged_by = ctx.user_id
        flag.acknowledged_at = now
    elif body.status == "integrated":
        if body.linked_document_id is not None:
            flag.linked_document_id = str(body.linked_document_id)
        flag.integrated_by = ctx.user_id
        flag.integrated_at = now
    elif body.status == "dismissed":
        flag.dismissal_reason = body.reason
        flag.dismissed_by = ctx.user_id
        flag.dismissed_at = now

    await session.commit()
    await session.refresh(flag)

    return _flag_to_response(flag)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Fetch alert or raise 404
# ─────────────────────────────────────────────────────────────────────────────


async def _get_alert_or_404(
    session: AsyncSession,
    alert_id: int,
    company_id: int,
) -> ContradictionAlert:
    """Fetch a ContradictionAlert scoped to company or raise 404.

    Returns HTTP 404 (not 403) for cross-tenant access attempts.

    Args:
        session: Async database session.
        alert_id: Alert primary key.
        company_id: Requesting company ID.

    Returns:
        The ContradictionAlert instance.

    Raises:
        AlertNotFoundError: If alert does not exist or belongs to another company.
    """
    stmt = select(ContradictionAlert).where(
        ContradictionAlert.id == alert_id,
        ContradictionAlert.company_id == company_id,
    )
    result = await session.execute(stmt)
    alert = result.scalar_one_or_none()

    if alert is None:
        raise AlertNotFoundError(
            "Contradiction alert not found.",
            alert_id=alert_id,
            company_id=company_id,
        )

    return alert


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Fetch novelty flag or raise 404
# ─────────────────────────────────────────────────────────────────────────────


async def _get_flag_or_404(
    session: AsyncSession,
    flag_id: int,
    company_id: int,
) -> NoveltyFlag:
    """Fetch a NoveltyFlag scoped to company or raise 404.

    Returns HTTP 404 (not 403) for cross-tenant access attempts.

    Args:
        session: Async database session.
        flag_id: Flag primary key.
        company_id: Requesting company ID.

    Returns:
        The NoveltyFlag instance.

    Raises:
        FlagNotFoundError: If flag does not exist or belongs to another company.
    """
    stmt = select(NoveltyFlag).where(
        NoveltyFlag.id == flag_id,
        NoveltyFlag.company_id == company_id,
    )
    result = await session.execute(stmt)
    flag = result.scalar_one_or_none()

    if flag is None:
        raise FlagNotFoundError(
            "Novelty flag not found.",
            flag_id=flag_id,
            company_id=company_id,
        )

    return flag


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Convert ContradictionAlert to list response dict
# ─────────────────────────────────────────────────────────────────────────────


def _alert_to_response(alert: ContradictionAlert) -> dict[str, Any]:
    """Convert a ContradictionAlert ORM instance to a list-level response dict.

    Args:
        alert: The ContradictionAlert ORM instance.

    Returns:
        Dict suitable for JSON response in list views.
    """
    return {
        "id": alert.id,
        "ingestion_record_id": alert.ingestion_record_id,
        "internal_document_id": alert.internal_document_id,
        "company_id": alert.company_id,
        "severity": alert.severity,
        "description": alert.contradiction_description,
        "evidence": alert.evidence_from_literature,
        "recommended_action": alert.recommended_action,
        "confidence": alert.confidence,
        "status": alert.status,
        "impact_report_id": alert.impact_report_id,
        "created_at": (
            alert.created_at.isoformat() if alert.created_at else None
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Convert ContradictionAlert to detail response dict
# ─────────────────────────────────────────────────────────────────────────────


def _alert_to_detail_response(alert: ContradictionAlert) -> dict[str, Any]:
    """Convert a ContradictionAlert ORM instance to a full detail response dict.

    Includes status history fields and linked impact report reference.

    Args:
        alert: The ContradictionAlert ORM instance.

    Returns:
        Dict with full alert details suitable for JSON response.
    """
    return {
        "id": alert.id,
        "ingestion_record_id": alert.ingestion_record_id,
        "internal_document_id": alert.internal_document_id,
        "company_id": alert.company_id,
        "severity": alert.severity,
        "description": alert.contradiction_description,
        "evidence": alert.evidence_from_literature,
        "recommended_action": alert.recommended_action,
        "confidence": alert.confidence,
        "affected_internal_sections": alert.affected_internal_sections or [],
        "status": alert.status,
        "acknowledged_by": alert.acknowledged_by,
        "acknowledged_at": (
            alert.acknowledged_at.isoformat() if alert.acknowledged_at else None
        ),
        "resolution_note": alert.resolution_note,
        "change_request_id": alert.change_request_id,
        "resolved_by": alert.resolved_by,
        "resolved_at": (
            alert.resolved_at.isoformat() if alert.resolved_at else None
        ),
        "dismissal_reason": alert.dismissal_reason,
        "dismissed_by": alert.dismissed_by,
        "dismissed_at": (
            alert.dismissed_at.isoformat() if alert.dismissed_at else None
        ),
        "impact_report_id": alert.impact_report_id,
        "created_at": (
            alert.created_at.isoformat() if alert.created_at else None
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Convert NoveltyFlag to response dict
# ─────────────────────────────────────────────────────────────────────────────


def _flag_to_response(flag: NoveltyFlag) -> dict[str, Any]:
    """Convert a NoveltyFlag ORM instance to a JSON-serializable dict.

    Args:
        flag: The NoveltyFlag ORM instance.

    Returns:
        Dict suitable for JSON response.
    """
    return {
        "id": flag.id,
        "ingestion_record_id": flag.ingestion_record_id,
        "company_id": flag.company_id,
        "novelty_description": flag.novelty_description,
        "relevance_score": flag.relevance_score,
        "high_priority": flag.high_priority,
        "suggested_document_types": flag.suggested_document_types or [],
        "status": flag.status,
        "group_id": flag.group_id,
        "linked_document_id": flag.linked_document_id,
        "acknowledged_by": flag.acknowledged_by,
        "acknowledged_at": (
            flag.acknowledged_at.isoformat() if flag.acknowledged_at else None
        ),
        "integrated_by": flag.integrated_by,
        "integrated_at": (
            flag.integrated_at.isoformat() if flag.integrated_at else None
        ),
        "dismissed_by": flag.dismissed_by,
        "dismissed_at": (
            flag.dismissed_at.isoformat() if flag.dismissed_at else None
        ),
        "dismissal_reason": flag.dismissal_reason,
        "created_at": (
            flag.created_at.isoformat() if flag.created_at else None
        ),
    }
