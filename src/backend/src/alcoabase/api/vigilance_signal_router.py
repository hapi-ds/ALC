"""FastAPI router for vigilance signal and execution endpoints.

Provides endpoints for:
- Vigilance Signals: list, detail, disposition update, summary
- Vigilance Search Executions: list, detail

Exception handlers:
- SignalNotFoundError → HTTP 404
- InvalidDispositionTransitionError → HTTP 422

References:
    - Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9
    - Design: .kiro/specs/Step_9-5_regulatory-medical-device-vigilance-pms/design.md
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from math import ceil
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.vigilance.audit import log_signal_disposition_changed
from alcoabase.literature.vigilance.models.medical_product import MedicalProduct
from alcoabase.literature.vigilance.models.vigilance_search_execution import (
    VigilanceSearchExecution,
)
from alcoabase.literature.vigilance.models.vigilance_search_profile import (
    VigilanceSearchProfile,
)
from alcoabase.literature.vigilance.models.vigilance_signal import VigilanceSignal
from alcoabase.literature.vigilance.schemas.signal import (
    SignalDispositionUpdateSchema,
    VigilanceSignalResponseSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vigilance", tags=["Vigilance Signals"])


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
# Valid disposition transitions (state machine)
# ─────────────────────────────────────────────────────────────────────────────

VALID_DISPOSITION_TRANSITIONS: dict[str, set[str]] = {
    "under_review": {"confirmed", "dismissed", "escalated"},
    "confirmed": {"escalated"},
}

# Severity ordering for sorting (higher = more severe)
SEVERITY_ORDER = {"critical": 3, "major": 2, "minor": 1}


# ─────────────────────────────────────────────────────────────────────────────
# GET /signals — List Vigilance Signals
# Requirements: 10.1, 10.8, 10.9
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/signals",
    summary="List vigilance signals",
)
async def list_signals(
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_db_session),
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    severity: Annotated[str | None, Query(description="Filter by severity")] = None,
    disposition: Annotated[str | None, Query(description="Filter by disposition")] = None,
    product_id: Annotated[int | None, Query(description="Filter by product ID")] = None,
    profile_id: Annotated[int | None, Query(description="Filter by profile ID")] = None,
) -> dict[str, Any]:
    """List vigilance signals for the requesting company with pagination.

    Supports filtering by severity, disposition, product_id, and profile_id.
    Results are ordered by severity descending then detection_timestamp descending.
    Requires at least the ``member`` role.

    Args:
        ctx: Resolved tenant context.
        session: Async database session.
        page: Page number (1-indexed).
        page_size: Items per page (1–100).
        severity: Optional severity filter (critical, major, minor).
        disposition: Optional disposition filter.
        product_id: Optional product ID filter.
        profile_id: Optional profile ID filter.

    Returns:
        Paginated list of signals with total count and page metadata.
    """
    # Build base query scoped to company
    stmt = select(VigilanceSignal).where(
        VigilanceSignal.company_id == ctx.company_id
    )

    # Apply optional filters
    if severity:
        stmt = stmt.where(VigilanceSignal.severity == severity)
    if disposition:
        stmt = stmt.where(VigilanceSignal.disposition == disposition)
    if product_id:
        stmt = stmt.where(VigilanceSignal.product_id == product_id)
    if profile_id:
        stmt = stmt.where(VigilanceSignal.profile_id == profile_id)

    # Count total matching records
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = (await session.execute(count_stmt)).scalar_one()

    # Order by severity desc (critical > major > minor) then detection_timestamp desc
    severity_sort = case(
        (VigilanceSignal.severity == "critical", 3),
        (VigilanceSignal.severity == "major", 2),
        (VigilanceSignal.severity == "minor", 1),
        else_=0,
    )
    stmt = stmt.order_by(
        desc(severity_sort),
        desc(VigilanceSignal.detection_timestamp),
    )

    # Apply pagination
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    result = await session.execute(stmt)
    signals = result.scalars().all()

    total_pages = ceil(total_count / page_size) if total_count > 0 else 0

    return {
        "items": [
            VigilanceSignalResponseSchema.model_validate(s).model_dump()
            for s in signals
        ],
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /signals/summary — Signal Summary Aggregations
# Requirements: 10.4, 10.8
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/signals/summary",
    summary="Get vigilance signal summary statistics",
)
async def get_signal_summary(
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Return aggregate statistics for vigilance signals.

    Includes: total open signals by severity by product, signals escalated
    this period, average time-to-disposition, and 12-month trend data.
    Requires at least the ``member`` role.

    Args:
        ctx: Resolved tenant context.
        session: Async database session.

    Returns:
        Signal summary with aggregated statistics.
    """
    company_id = ctx.company_id

    # Open signals = under_review or confirmed
    open_dispositions = ("under_review", "confirmed")

    # Total open signals
    total_open_stmt = select(func.count()).where(
        VigilanceSignal.company_id == company_id,
        VigilanceSignal.disposition.in_(open_dispositions),
    )
    total_open = (await session.execute(total_open_stmt)).scalar_one()

    # Open signals by product and severity
    signals_by_product_stmt = (
        select(
            VigilanceSignal.product_id,
            MedicalProduct.name.label("product_name"),
            VigilanceSignal.severity,
            func.count().label("count"),
        )
        .join(MedicalProduct, MedicalProduct.id == VigilanceSignal.product_id)
        .where(
            VigilanceSignal.company_id == company_id,
            VigilanceSignal.disposition.in_(open_dispositions),
        )
        .group_by(
            VigilanceSignal.product_id,
            MedicalProduct.name,
            VigilanceSignal.severity,
        )
    )
    product_severity_rows = (await session.execute(signals_by_product_stmt)).all()

    # Aggregate into per-product structure
    product_map: dict[int, dict[str, Any]] = {}
    for row in product_severity_rows:
        pid = row.product_id
        if pid not in product_map:
            product_map[pid] = {
                "product_id": pid,
                "product_name": row.product_name,
                "critical": 0,
                "major": 0,
                "minor": 0,
            }
        product_map[pid][row.severity] = row.count

    signals_by_product = list(product_map.values())

    # Escalated this period (current calendar month)
    now = datetime.utcnow()
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    escalated_stmt = select(func.count()).where(
        VigilanceSignal.company_id == company_id,
        VigilanceSignal.disposition == "escalated",
        VigilanceSignal.updated_at >= period_start,
    )
    escalated_this_period = (await session.execute(escalated_stmt)).scalar_one()

    # Average time-to-disposition (for signals that have been dispositioned)
    # Only consider signals moved out of under_review
    avg_disposition_stmt = select(
        func.avg(
            func.extract(
                "epoch",
                VigilanceSignal.updated_at - VigilanceSignal.detection_timestamp,
            )
        )
    ).where(
        VigilanceSignal.company_id == company_id,
        VigilanceSignal.disposition.notin_(["under_review"]),
    )
    avg_seconds = (await session.execute(avg_disposition_stmt)).scalar_one()
    avg_time_to_disposition_hours = (
        round(avg_seconds / 3600, 2) if avg_seconds else None
    )

    # Trend: signals per month over last 12 months
    twelve_months_ago = now.replace(day=1)
    # Go back 12 months
    month = twelve_months_ago.month - 12
    year = twelve_months_ago.year
    if month <= 0:
        year -= 1
        month += 12
    twelve_months_ago = twelve_months_ago.replace(year=year, month=month)

    trend_stmt = (
        select(
            func.date_trunc("month", VigilanceSignal.detection_timestamp).label(
                "month"
            ),
            func.count().label("count"),
        )
        .where(
            VigilanceSignal.company_id == company_id,
            VigilanceSignal.detection_timestamp >= twelve_months_ago,
        )
        .group_by(func.date_trunc("month", VigilanceSignal.detection_timestamp))
        .order_by(func.date_trunc("month", VigilanceSignal.detection_timestamp))
    )
    trend_rows = (await session.execute(trend_stmt)).all()
    trend = [
        {"month": row.month.isoformat() if row.month else None, "count": row.count}
        for row in trend_rows
    ]

    return {
        "total_open_signals": total_open,
        "signals_by_product": signals_by_product,
        "escalated_this_period": escalated_this_period,
        "avg_time_to_disposition_hours": avg_time_to_disposition_hours,
        "trend": trend,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /signals/{signal_id} — Get Signal Details
# Requirements: 10.2, 10.8, 10.9
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/signals/{signal_id}",
    summary="Get vigilance signal details",
)
async def get_signal(
    signal_id: Annotated[int, Path(description="Signal ID")],
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Get full vigilance signal details with related metadata.

    Includes literature metadata, product metadata, disposition history,
    linked impact reports, and linked contradiction alerts.
    Requires at least the ``member`` role.

    Args:
        signal_id: Target signal ID.
        ctx: Resolved tenant context.
        session: Async database session.

    Returns:
        Full signal details with linked resources.

    Raises:
        HTTPException 404: If signal not found in this company.
    """
    stmt = (
        select(VigilanceSignal)
        .options(
            selectinload(VigilanceSignal.product),
            selectinload(VigilanceSignal.profile),
        )
        .where(
            VigilanceSignal.id == signal_id,
            VigilanceSignal.company_id == ctx.company_id,
        )
    )
    result = await session.execute(stmt)
    signal = result.scalar_one_or_none()

    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found.")

    # Build response with signal data
    signal_data = VigilanceSignalResponseSchema.model_validate(signal).model_dump()

    # Add product metadata
    product_metadata = None
    if signal.product:
        product_metadata = {
            "id": signal.product.id,
            "name": signal.product.name,
            "device_class": signal.product.device_class,
            "intended_purpose": signal.product.intended_purpose,
            "udi": signal.product.udi,
            "status": signal.product.status,
        }

    # Add profile metadata
    profile_metadata = None
    if signal.profile:
        profile_metadata = {
            "id": signal.profile.id,
            "name": signal.profile.name,
            "search_terms": signal.profile.search_terms,
        }

    # Disposition history from versioning (if available)
    disposition_history: list[dict[str, Any]] = []
    try:
        if hasattr(signal, "versions"):
            for version in signal.versions:
                if hasattr(version, "disposition"):
                    disposition_history.append(
                        {
                            "disposition": version.disposition,
                            "reviewer_user_id": getattr(
                                version, "reviewer_user_id", None
                            ),
                            "updated_at": (
                                version.updated_at.isoformat()
                                if hasattr(version, "updated_at")
                                and version.updated_at
                                else None
                            ),
                        }
                    )
    except Exception:
        # Gracefully handle if versioning is not available
        pass

    # Linked impact reports (placeholder — will be populated when
    # ImpactAnalysisService integration is complete)
    linked_impact_reports: list[dict[str, Any]] = []

    # Linked contradiction alerts (placeholder — will be populated when
    # ContradictionDetectionService integration is complete)
    linked_contradiction_alerts: list[dict[str, Any]] = []

    return {
        **signal_data,
        "product_metadata": product_metadata,
        "profile_metadata": profile_metadata,
        "disposition_history": disposition_history,
        "linked_impact_reports": linked_impact_reports,
        "linked_contradiction_alerts": linked_contradiction_alerts,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PUT /signals/{signal_id}/disposition — Update Signal Disposition
# Requirements: 10.3, 10.7, 10.8, 10.9
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/signals/{signal_id}/disposition",
    summary="Update signal disposition",
)
async def update_signal_disposition(
    signal_id: Annotated[int, Path(description="Signal ID")],
    payload: SignalDispositionUpdateSchema,
    ctx: TenantContext = Depends(require_document_admin),
    session: AsyncSession = Depends(get_db_session),
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> dict[str, Any]:
    """Update a signal's disposition status.

    Valid transitions:
        under_review → confirmed | dismissed | escalated
        confirmed → escalated

    When disposition is 'confirmed', confirmation_note is required.
    When disposition is 'dismissed', dismissal_reason is required.
    Requires ``document_admin`` or ``system_admin`` role.
    Requires ``X-Change-Reason`` header.

    Args:
        signal_id: Target signal ID.
        payload: Disposition update with target state and notes.
        ctx: Resolved tenant context.
        session: Async database session.
        x_change_reason: Required audit trail reason (enforced by middleware).

    Returns:
        Updated signal data with HTTP 200.

    Raises:
        HTTPException 404: If signal not found in this company.
        HTTPException 422: If transition is invalid.
    """
    # Load signal
    stmt = select(VigilanceSignal).where(
        VigilanceSignal.id == signal_id,
        VigilanceSignal.company_id == ctx.company_id,
    )
    result = await session.execute(stmt)
    signal = result.scalar_one_or_none()

    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found.")

    # Validate disposition transition
    current = signal.disposition
    requested = payload.disposition
    allowed_transitions = VALID_DISPOSITION_TRANSITIONS.get(current, set())

    if requested not in allowed_transitions:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid disposition transition from '{current}' to '{requested}'. "
                f"Allowed transitions from '{current}': {sorted(allowed_transitions) if allowed_transitions else 'none'}."
            ),
        )

    # Apply disposition update
    signal.disposition = requested
    signal.reviewer_user_id = ctx.user_id

    if requested == "confirmed":
        signal.confirmation_note = payload.confirmation_note
    elif requested == "dismissed":
        signal.dismissal_reason = payload.dismissal_reason

    await session.commit()
    await session.refresh(signal)

    # Structured audit log for disposition change (Requirement 12.3)
    log_signal_disposition_changed(
        signal_id=signal_id,
        company_id=ctx.company_id,
        previous_disposition=current,
        new_disposition=requested,
        acting_user_id=ctx.user_id,
        confirmation_note=payload.confirmation_note if requested == "confirmed" else None,
        dismissal_reason=payload.dismissal_reason if requested == "dismissed" else None,
    )

    logger.info(
        "Signal %d disposition updated: %s → %s by user %d",
        signal_id,
        current,
        requested,
        ctx.user_id,
    )

    return VigilanceSignalResponseSchema.model_validate(signal).model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# GET /executions — List Search Executions
# Requirements: 10.5, 10.8, 10.9
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/executions",
    summary="List vigilance search executions",
)
async def list_executions(
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_db_session),
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    profile_id: Annotated[int | None, Query(description="Filter by profile ID")] = None,
    product_id: Annotated[int | None, Query(description="Filter by product ID")] = None,
    status: Annotated[str | None, Query(description="Filter by status")] = None,
    date_from: Annotated[date | None, Query(description="Filter from date (ISO-8601)")] = None,
    date_to: Annotated[date | None, Query(description="Filter to date (ISO-8601)")] = None,
) -> dict[str, Any]:
    """List vigilance search executions for the requesting company.

    Supports filtering by profile_id, product_id, status, and date range.
    Results are ordered by execution_timestamp descending.
    Requires at least the ``member`` role.

    Args:
        ctx: Resolved tenant context.
        session: Async database session.
        page: Page number (1-indexed).
        page_size: Items per page (1–100).
        profile_id: Optional profile ID filter.
        product_id: Optional product ID filter (via profile join).
        status: Optional status filter.
        date_from: Optional start date filter.
        date_to: Optional end date filter.

    Returns:
        Paginated list of executions with total count and page metadata.
    """
    # Build base query scoped to company
    stmt = select(VigilanceSearchExecution).where(
        VigilanceSearchExecution.company_id == ctx.company_id
    )

    # Apply optional filters
    if profile_id:
        stmt = stmt.where(VigilanceSearchExecution.profile_id == profile_id)
    if product_id:
        # Join through profile to filter by product_id
        stmt = stmt.join(
            VigilanceSearchProfile,
            VigilanceSearchProfile.id == VigilanceSearchExecution.profile_id,
        ).where(VigilanceSearchProfile.product_id == product_id)
    if status:
        stmt = stmt.where(VigilanceSearchExecution.status == status)
    if date_from:
        stmt = stmt.where(
            VigilanceSearchExecution.execution_timestamp >= datetime.combine(date_from, datetime.min.time())
        )
    if date_to:
        stmt = stmt.where(
            VigilanceSearchExecution.execution_timestamp <= datetime.combine(date_to, datetime.max.time())
        )

    # Count total matching records
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = (await session.execute(count_stmt)).scalar_one()

    # Order by execution_timestamp descending
    stmt = stmt.order_by(desc(VigilanceSearchExecution.execution_timestamp))

    # Apply pagination
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    result = await session.execute(stmt)
    executions = result.scalars().all()

    total_pages = ceil(total_count / page_size) if total_count > 0 else 0

    return {
        "items": [
            {
                "id": e.id,
                "profile_id": e.profile_id,
                "company_id": e.company_id,
                "execution_timestamp": e.execution_timestamp.isoformat()
                if e.execution_timestamp
                else None,
                "search_parameters": e.search_parameters,
                "sources_queried": e.sources_queried,
                "total_results_found": e.total_results_found,
                "results_after_exclusion": e.results_after_exclusion,
                "results_ingested": e.results_ingested,
                "results_duplicate": e.results_duplicate,
                "execution_duration_ms": e.execution_duration_ms,
                "status": e.status,
            }
            for e in executions
        ],
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /executions/{execution_id} — Get Execution Details
# Requirements: 10.6, 10.8, 10.9
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/executions/{execution_id}",
    summary="Get vigilance search execution details",
)
async def get_execution(
    execution_id: Annotated[int, Path(description="Execution ID")],
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Get full execution details including parameters, sources, counts, and signals.

    Includes search parameters, sources queried, result counts,
    and signal detection outcomes for records from this execution.
    Requires at least the ``member`` role.

    Args:
        execution_id: Target execution ID.
        ctx: Resolved tenant context.
        session: Async database session.

    Returns:
        Full execution details with signal outcomes.

    Raises:
        HTTPException 404: If execution not found in this company.
    """
    stmt = (
        select(VigilanceSearchExecution)
        .options(selectinload(VigilanceSearchExecution.profile))
        .where(
            VigilanceSearchExecution.id == execution_id,
            VigilanceSearchExecution.company_id == ctx.company_id,
        )
    )
    result = await session.execute(stmt)
    execution = result.scalar_one_or_none()

    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found.")

    # Get signal outcomes for this execution (signals from records linked to this profile)
    signal_outcomes_stmt = (
        select(
            VigilanceSignal.id,
            VigilanceSignal.severity,
            VigilanceSignal.disposition,
            VigilanceSignal.confidence,
            VigilanceSignal.detection_timestamp,
        )
        .where(
            VigilanceSignal.company_id == ctx.company_id,
            VigilanceSignal.profile_id == execution.profile_id,
            VigilanceSignal.detection_timestamp >= execution.execution_timestamp,
        )
    )
    signal_rows = (await session.execute(signal_outcomes_stmt)).all()
    signal_outcomes = [
        {
            "signal_id": row.id,
            "severity": row.severity,
            "disposition": row.disposition,
            "confidence": row.confidence,
            "detection_timestamp": row.detection_timestamp.isoformat()
            if row.detection_timestamp
            else None,
        }
        for row in signal_rows
    ]

    # Build profile info
    profile_info = None
    if execution.profile:
        profile_info = {
            "id": execution.profile.id,
            "name": execution.profile.name,
            "product_id": execution.profile.product_id,
        }

    return {
        "id": execution.id,
        "profile_id": execution.profile_id,
        "company_id": execution.company_id,
        "execution_timestamp": execution.execution_timestamp.isoformat()
        if execution.execution_timestamp
        else None,
        "search_parameters": execution.search_parameters,
        "sources_queried": execution.sources_queried,
        "total_results_found": execution.total_results_found,
        "results_after_exclusion": execution.results_after_exclusion,
        "results_ingested": execution.results_ingested,
        "results_duplicate": execution.results_duplicate,
        "execution_duration_ms": execution.execution_duration_ms,
        "status": execution.status,
        "profile": profile_info,
        "signal_outcomes": signal_outcomes,
    }
