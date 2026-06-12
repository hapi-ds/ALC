"""FastAPI router for Periodic Safety Report endpoints.

Provides endpoints for:
- List reports with pagination and filters (GET /)
- Get full report content (GET /{report_id})
- Advance report status lifecycle (PUT /{report_id}/status)
- Generate a new report (POST /generate)

Exception handlers:
- ReportNotFoundError → HTTP 404 Not Found
- InvalidReportStatusTransitionError → HTTP 422 Unprocessable Entity

References:
    - Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from math import ceil
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.vigilance.exceptions import (
    InvalidReportStatusTransitionError,
    ReportNotFoundError,
)
from alcoabase.literature.vigilance.schemas.report import (
    PeriodicSafetyReportResponseSchema,
    ReportGenerateRequestSchema,
    ReportStatusUpdateSchema,
)
from alcoabase.literature.vigilance.services.periodic_report_service import (
    PeriodicReportService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vigilance/reports", tags=["vigilance-reports"])


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
# Service instantiation helper
# ─────────────────────────────────────────────────────────────────────────────

_report_service = PeriodicReportService()


# ─────────────────────────────────────────────────────────────────────────────
# GET / — List reports (paginated, filtered)
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "",
    summary="List periodic safety reports",
    responses={
        403: {"description": "Insufficient permissions"},
    },
)
async def list_reports(
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
    product_id: Annotated[
        int | None, Query(description="Filter by medical product ID")
    ] = None,
    status: Annotated[
        str | None, Query(description="Filter by report status")
    ] = None,
    period_start: Annotated[
        date | None, Query(description="Filter reports with period starting on or after this date")
    ] = None,
    period_end: Annotated[
        date | None, Query(description="Filter reports with period ending on or before this date")
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Records per page (max 100)")
    ] = 20,
) -> dict[str, Any]:
    """List periodic safety reports for the current company.

    Supports filtering by product_id, status, and period dates. Results
    are paginated and ordered by generated_at descending.

    Requires at least ``member`` role.

    Args:
        session: Async database session.
        ctx: Resolved tenant context.
        product_id: Optional product filter.
        status: Optional status filter (generated, reviewed, approved, submitted).
        period_start: Optional period start filter.
        period_end: Optional period end filter.
        page: Page number (1-indexed).
        page_size: Number of records per page (max 100).

    Returns:
        Paginated list of reports with metadata.
    """
    reports, total = await _report_service.list_reports(
        session,
        company_id=ctx.company_id,
        product_id=product_id,
        status=status,
        period_start=period_start,
        period_end=period_end,
        page=page,
        page_size=page_size,
    )

    total_pages = ceil(total / page_size) if total > 0 else 1

    return {
        "items": reports,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /{report_id} — Get full report content
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{report_id}",
    summary="Get full periodic safety report",
    responses={
        403: {"description": "Insufficient permissions"},
        404: {"description": "Report not found"},
    },
)
async def get_report(
    report_id: Annotated[int, Path(description="Report ID")],
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
) -> dict[str, Any]:
    """Get full periodic safety report content by ID.

    Returns the complete report including report_content JSON body.
    Scoped to the requesting company — returns 404 for cross-tenant access.

    Requires at least ``member`` role.

    Args:
        report_id: The report to retrieve.
        session: Async database session.
        ctx: Resolved tenant context.

    Returns:
        Full report dict with report_content.

    Raises:
        HTTPException 404: If report not found in this company.
    """
    try:
        report = await _report_service.get_report(
            session,
            report_id=report_id,
            company_id=ctx.company_id,
        )
    except ReportNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Report with id {report_id} not found.",
        )

    return report


# ─────────────────────────────────────────────────────────────────────────────
# PUT /{report_id}/status — Advance report status
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/{report_id}/status",
    summary="Advance report lifecycle status",
    responses={
        403: {"description": "Insufficient permissions"},
        404: {"description": "Report not found"},
        422: {"description": "Invalid status transition"},
    },
)
async def update_report_status(
    report_id: Annotated[int, Path(description="Report ID")],
    body: ReportStatusUpdateSchema,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_document_admin),
    x_change_reason: Annotated[
        str, Header(description="Reason for the status change")
    ] = ...,
) -> dict[str, Any]:
    """Advance a report through its lifecycle.

    Valid transitions: generated → reviewed → approved → submitted.
    Requires document_admin or system_admin role and X-Change-Reason header.

    Args:
        report_id: Target report ID.
        body: Status update request with target status and optional comment.
        session: Async database session.
        ctx: Resolved tenant context (document_admin+ enforced).
        x_change_reason: Required change reason for audit compliance.

    Returns:
        Updated report dict.

    Raises:
        HTTPException 404: If report not found in this company.
        HTTPException 422: If the status transition is invalid.
    """
    try:
        updated_report = await _report_service.advance_status(
            session,
            report_id=report_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            new_status=body.status,
            comment=body.comment,
        )
    except ReportNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Report with id {report_id} not found.",
        )
    except InvalidReportStatusTransitionError as e:
        raise HTTPException(
            status_code=422,
            detail=e.message,
        )

    await session.commit()
    return updated_report


# ─────────────────────────────────────────────────────────────────────────────
# POST /generate — Dispatch report generation task
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/generate",
    status_code=202,
    summary="Generate a periodic safety report",
    responses={
        403: {"description": "Insufficient permissions"},
        503: {"description": "Task queue unavailable"},
    },
)
async def generate_report(
    body: ReportGenerateRequestSchema,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_document_admin),
    x_change_reason: Annotated[
        str, Header(description="Reason for report generation")
    ] = ...,
) -> dict[str, str]:
    """Generate a new periodic safety report asynchronously.

    Dispatches a Celery task for report generation. Returns HTTP 202 with
    the task_id for progress tracking.

    Requires document_admin or system_admin role and X-Change-Reason header.

    Args:
        body: Generation request with product_id, period_start, period_end.
        session: Async database session.
        ctx: Resolved tenant context (document_admin+ enforced).
        x_change_reason: Required change reason for audit compliance.

    Returns:
        Dict with task_id for the enqueued generation task.

    Raises:
        HTTPException 503: If the task queue is unavailable.
    """
    task_id = str(uuid.uuid4())

    try:
        from alcoabase.tasks.celery_app import celery_app

        celery_app.send_task(
            "alcoabase.tasks.vigilance_tasks.generate_periodic_report",
            kwargs={
                "product_id": body.product_id,
                "company_id": ctx.company_id,
                "user_id": ctx.user_id,
                "period_start": body.period_start.isoformat(),
                "period_end": body.period_end.isoformat(),
            },
            queue="literature_ingestion",
            task_id=task_id,
        )
    except Exception as exc:
        logger.error("Failed to enqueue report generation task: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Task queue is temporarily unavailable.",
        )

    return JSONResponse(
        status_code=202,
        content={"task_id": task_id},
    )
