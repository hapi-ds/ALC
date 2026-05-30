"""FastAPI router for audit trail viewer endpoints.

Provides endpoints for listing, filtering, searching, and viewing
audit events across all versioned record types. All endpoints are
read-only and protected by RBAC (audit_logs:read permission).

References:
    - Design doc: Components > Audit Trail Router
    - Requirements 1–6: Aggregation, pagination, filtering, tenant scoping, search, detail
    - Requirements 9.1–9.4: Role-based access control
    - Requirement 11.1: Audit of audit trail access
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.rbac import require_permission
from alcoabase.dependencies.tenant import TenantContext
from alcoabase.schemas.audit_trail import (
    AuditEventDetail,
    AuditTrailFilters,
    AuditTrailPage,
    ExportRequest,
    ExportStatusResponse,
)
from alcoabase.services.audit_access_logger import AuditAccessLogger
from alcoabase.services.audit_pdf_exporter import AuditPDFExporter
from alcoabase.services.audit_trail_service import AuditTrailService
from alcoabase.services.rbac import RBACService

router = APIRouter(prefix="/audit-trail", tags=["Audit Trail"])

# Module-level service instances
_audit_trail_service = AuditTrailService()
_audit_access_logger = AuditAccessLogger()
_audit_pdf_exporter = AuditPDFExporter()
_rbac_service = RBACService()


def _get_audit_trail_service() -> AuditTrailService:
    """Provide the AuditTrailService instance as a dependency."""
    return _audit_trail_service


def _get_audit_access_logger() -> AuditAccessLogger:
    """Provide the AuditAccessLogger instance as a dependency."""
    return _audit_access_logger


def _get_audit_pdf_exporter() -> AuditPDFExporter:
    """Provide the AuditPDFExporter instance as a dependency."""
    return _audit_pdf_exporter


@router.get("", response_model=AuditTrailPage)
async def list_audit_events(
    request: Request,
    cursor: str | None = Query(default=None),
    page_size: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    date_start: datetime | None = Query(default=None),
    date_end: datetime | None = Query(default=None),
    record_type: str | None = Query(default=None),
    operation_type: Literal["INSERT", "UPDATE", "DELETE"] | None = Query(
        default=None
    ),
    cross_company: bool = Query(default=False),
    ctx: TenantContext = Depends(require_permission("audit_logs", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: AuditTrailService = Depends(_get_audit_trail_service),
    access_logger: AuditAccessLogger = Depends(_get_audit_access_logger),
) -> AuditTrailPage:
    """List, filter, and search audit events with cursor-based pagination.

    Returns a paginated list of audit events aggregated from all version
    tables, ordered by timestamp descending (most recent first).

    Args:
        request: The incoming HTTP request.
        cursor: Opaque cursor for pagination (None for first page).
        page_size: Number of events per page (1–200, default 50).
        search: Optional substring search query.
        user_id: Filter by user who performed the action.
        date_start: Filter by start date (inclusive).
        date_end: Filter by end date (inclusive).
        record_type: Filter by record type.
        operation_type: Filter by operation type (INSERT, UPDATE, DELETE).
        cross_company: If True, query across all companies (system_admin only).
        ctx: Resolved tenant context with RBAC enforcement.
        session: Active async database session.
        service: AuditTrailService dependency.
        access_logger: AuditAccessLogger dependency.

    Returns:
        AuditTrailPage with events, next_cursor, total_count, and warnings.

    Raises:
        HTTPException 400: If no X-Company-Id header and cross_company is False.
        HTTPException 403: If cross_company=True and user is not system_admin.
    """
    # Cross-company query support (Requirements 4.1, 4.2, 4.3)
    if cross_company:
        # Verify user has system_admin role
        role = await _rbac_service.get_role_for_user(
            ctx.user_id, ctx.company_id, session
        )
        if role is None or role.name != "system_admin":
            raise HTTPException(
                status_code=403,
                detail="Cross-company queries require system_admin role.",
            )
    else:
        # Ensure X-Company-Id header is present when not cross-company
        company_id_header = request.headers.get("X-Company-Id")
        if not company_id_header:
            raise HTTPException(
                status_code=400,
                detail="X-Company-Id header is required for tenant-scoped queries.",
            )

    # Build filters from query params
    filters = AuditTrailFilters(
        user_id=user_id,
        date_start=date_start,
        date_end=date_end,
        record_type=record_type,
        operation_type=operation_type,
    )

    # Query audit events
    result = await service.list_events(
        session=session,
        company_id=ctx.company_id,
        filters=filters,
        search_query=search,
        cursor=cursor,
        page_size=page_size,
        cross_company=cross_company,
    )

    # Log access (fire-and-forget pattern)
    active_filters = _build_active_filters(
        user_id=user_id,
        date_start=date_start,
        date_end=date_end,
        record_type=record_type,
        operation_type=operation_type,
        search=search,
    )
    await access_logger.log_access(
        session=session,
        user_id=ctx.user_id,
        company_id=ctx.company_id,
        action="view",
        filters_applied=active_filters if active_filters else None,
    )

    return result


@router.get(
    "/{record_type}/{record_id}/{transaction_id}",
    response_model=AuditEventDetail,
)
async def get_audit_event_detail(
    record_type: str,
    record_id: int,
    transaction_id: int,
    ctx: TenantContext = Depends(require_permission("audit_logs", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: AuditTrailService = Depends(_get_audit_trail_service),
) -> AuditEventDetail:
    """Get full detail for a specific audit event including field-level changes.

    Returns the complete version snapshot with field changes showing
    previous and new values for each modified field.

    Args:
        record_type: The type of record (e.g., documents, templates).
        record_id: The record's primary key.
        transaction_id: The version entry's transaction ID.
        ctx: Resolved tenant context with RBAC enforcement.
        session: Active async database session.
        service: AuditTrailService dependency.

    Returns:
        AuditEventDetail with full field-level change information.

    Raises:
        HTTPException: 404 if the event is not found.
    """
    detail = await service.get_event_detail(
        session=session,
        company_id=ctx.company_id,
        record_type=record_type,
        record_id=record_id,
        transaction_id=transaction_id,
    )

    if detail is None:
        raise HTTPException(
            status_code=404,
            detail="Audit event not found.",
        )

    return detail


def _build_active_filters(
    user_id: int | None,
    date_start: datetime | None,
    date_end: datetime | None,
    record_type: str | None,
    operation_type: str | None,
    search: str | None,
) -> dict:
    """Build a dict of active filter parameters for access logging.

    Only includes parameters that were actually provided (non-None).

    Args:
        user_id: User ID filter value.
        date_start: Start date filter value.
        date_end: End date filter value.
        record_type: Record type filter value.
        operation_type: Operation type filter value.
        search: Search query value.

    Returns:
        Dict of active filter key-value pairs.
    """
    active: dict = {}
    if user_id is not None:
        active["user_id"] = user_id
    if date_start is not None:
        active["date_start"] = date_start.isoformat()
    if date_end is not None:
        active["date_end"] = date_end.isoformat()
    if record_type is not None:
        active["record_type"] = record_type
    if operation_type is not None:
        active["operation_type"] = operation_type
    if search is not None:
        active["search"] = search
    return active


# ---------------------------------------------------------------------------
# Export endpoints
# ---------------------------------------------------------------------------


@router.post("/export", response_model=None)
async def trigger_export(
    request: Request,
    body: ExportRequest,
    ctx: TenantContext = Depends(require_permission("audit_logs", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: AuditTrailService = Depends(_get_audit_trail_service),
    exporter: AuditPDFExporter = Depends(_get_audit_pdf_exporter),
    access_logger: AuditAccessLogger = Depends(_get_audit_access_logger),
):
    """Trigger a PDF export of audit trail events.

    If total matching events == 0: returns HTTP 400.
    If total matching events ≤ 10,000: generates PDF synchronously.
    If total matching events > 10,000: dispatches async Celery task.

    Args:
        request: The incoming HTTP request.
        body: Export request with optional filters and search query.
        ctx: Resolved tenant context with RBAC enforcement.
        session: Active async database session.
        service: AuditTrailService dependency.
        exporter: AuditPDFExporter dependency.
        access_logger: AuditAccessLogger dependency.

    Returns:
        PDF file response (sync) or ExportStatusResponse (async).

    Raises:
        HTTPException 400: If no events match the current filters.
    """
    filters = body.filters or AuditTrailFilters()

    # Get total count of matching events
    total_count = await service.get_total_count(
        session=session,
        company_id=ctx.company_id,
        filters=filters,
        search_query=body.search_query,
    )

    if total_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No events match the current filters for export",
        )

    if total_count <= 10_000:
        # Synchronous export
        pdf_bytes = await exporter.export_sync(
            session=session,
            company_id=ctx.company_id,
            filters=body.filters,
            search_query=body.search_query,
            requesting_user_id=ctx.user_id,
        )

        # Log export access
        await access_logger.log_access(
            session=session,
            user_id=ctx.user_id,
            company_id=ctx.company_id,
            action="export",
            filters_applied=filters.model_dump(exclude_none=True) or None,
            event_count=total_count,
        )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=audit-trail-export.pdf"
            },
        )
    else:
        # Async export via Celery
        job_id = await exporter.export_async(
            session=session,
            company_id=ctx.company_id,
            filters=body.filters,
            search_query=body.search_query,
            requesting_user_id=ctx.user_id,
        )

        # Log export access
        await access_logger.log_access(
            session=session,
            user_id=ctx.user_id,
            company_id=ctx.company_id,
            action="export",
            filters_applied=filters.model_dump(exclude_none=True) or None,
            event_count=total_count,
        )

        return ExportStatusResponse(
            job_id=job_id,
            status="pending",
        )


@router.get("/export/{job_id}", response_model=ExportStatusResponse)
async def get_export_status(
    job_id: str,
    ctx: TenantContext = Depends(require_permission("audit_logs", "read")),
    exporter: AuditPDFExporter = Depends(_get_audit_pdf_exporter),
) -> ExportStatusResponse:
    """Check the status of an async export job.

    Args:
        job_id: The UUID of the export job to check.
        ctx: Resolved tenant context with RBAC enforcement.
        exporter: AuditPDFExporter dependency.

    Returns:
        ExportStatusResponse with current status and download_url if completed.
    """
    return exporter.get_export_status(job_id)


# ---------------------------------------------------------------------------
# Immutability enforcement — PUT, PATCH, DELETE all return HTTP 403
# Per ALCOA+ and CFR 21 Part 11, audit records cannot be modified or deleted.
# These handlers enforce immutability regardless of the requesting user's
# role or permissions.
# ---------------------------------------------------------------------------

_IMMUTABILITY_MESSAGE = (
    "Audit records are immutable per ALCOA+ and CFR 21 Part 11"
)


@router.api_route(
    "/",
    methods=["PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def block_audit_trail_root_mutations() -> None:
    """Block all PUT, PATCH, DELETE requests on the audit trail root.

    Raises:
        HTTPException: Always raises HTTP 403 Forbidden.
    """
    raise HTTPException(
        status_code=403,
        detail=_IMMUTABILITY_MESSAGE,
    )


@router.api_route(
    "/{path:path}",
    methods=["PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def block_audit_trail_path_mutations(path: str) -> None:
    """Block all PUT, PATCH, DELETE requests on any audit trail sub-path.

    Args:
        path: The requested path (captured but unused).

    Raises:
        HTTPException: Always raises HTTP 403 Forbidden.
    """
    raise HTTPException(
        status_code=403,
        detail=_IMMUTABILITY_MESSAGE,
    )
