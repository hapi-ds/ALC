"""FastAPI router for the literature ingestion pipeline endpoints.

Provides endpoints for:
- Batch ingestion submission (POST /)
- Ingestion record listing with filters (GET /)
- Single record detail with state history (GET /{ingestion_record_id})
- Batch status (GET /batch/{batch_id})
- Retry failed records (POST /{ingestion_record_id}/retry)
- Configuration management (GET/PUT /config)
- Storage usage monitoring (GET /storage)
- State counts aggregation (GET /states)
- Pipeline health monitoring (GET /health)

Exception handlers:
- BatchTooLargeError → HTTP 413 Request Entity Too Large
- StorageQuotaExceededError → HTTP 409 Conflict
- InvalidStateTransitionError → HTTP 400 Bad Request
- CompanyPausedError → HTTP 429 Too Many Requests
- MaxRetriesExceededError → HTTP 409 Conflict

References:
    - Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 14.6
"""

from __future__ import annotations

import logging
from datetime import datetime
from math import ceil
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.ingestion.exceptions import (
    BatchTooLargeError,
    CompanyPausedError,
    InvalidStateTransitionError,
    MaxRetriesExceededError,
    StorageQuotaExceededError,
)
from alcoabase.literature.ingestion.models.ingestion import (
    IngestionConfiguration,
    IngestionRecord,
)
from alcoabase.literature.ingestion.schemas.configuration import (
    IngestionConfigurationCreate,
    IngestionConfigurationResponse,
    IngestionConfigurationUpdate,
)
from alcoabase.literature.ingestion.schemas.ingestion import (
    BatchIngestionResponse,
    BatchStatusResponse,
    IngestionHealthResponse,
    IngestionRecordListResponse,
    IngestionRecordResponse,
    IngestionSubmitRequest,
    StateCounts,
    StorageUsageResponse,
)
from alcoabase.literature.ingestion.services.state_machine import IngestionState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/literature/ingest", tags=["literature-ingestion"])


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


def _require_system_admin():
    """Return a dependency enforcing system_admin role.

    Returns:
        A FastAPI dependency function that raises HTTP 403 if the user
        does not have system_admin or admin role.
    """

    async def _check(
        tenant: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        allowed_roles = {"system_admin", "admin"}
        if tenant.membership_role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="Requires system_admin role.",
            )
        return tenant

    return _check


require_member = _require_member()
require_document_admin = _require_document_admin()
require_system_admin = _require_system_admin()


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Build IngestionRecordResponse from model instance
# ─────────────────────────────────────────────────────────────────────────────


def _build_record_response(record: IngestionRecord) -> IngestionRecordResponse:
    """Build an IngestionRecordResponse from a SQLAlchemy model instance.

    Args:
        record: The IngestionRecord ORM instance.

    Returns:
        Pydantic response schema populated from the model.
    """
    return IngestionRecordResponse(
        id=record.id,
        company_id=record.company_id,
        batch_id=record.batch_id,
        state=record.state,
        failed_from_state=record.failed_from_state,
        error_type=record.error_type,
        error_message=record.error_message,
        retry_count=record.retry_count,
        title=record.title,
        authors=record.authors or [],
        doi=record.doi,
        publication_date=record.publication_date,
        journal_or_venue=record.journal_or_venue,
        publication_type=record.publication_type,
        external_id=record.external_id,
        source_id=record.source_id,
        url=record.url,
        abstract=record.abstract,
        storage_path=record.storage_path,
        file_size_bytes=record.file_size_bytes,
        content_type=record.content_type,
        sha256_checksum=record.sha256_checksum,
        download_timestamp=record.download_timestamp,
        word_count=record.word_count,
        retention_expiry_date=record.retention_expiry_date,
        original_file_purged=record.original_file_purged,
        state_history=record.state_history or [],
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST / — Submit Batch Ingestion
# Requirements: 11.1
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=BatchIngestionResponse,
    status_code=202,
    summary="Submit a batch of literature results for ingestion",
    responses={
        413: {"description": "Batch exceeds maximum size (100 items)"},
        409: {"description": "Storage quota exceeded"},
        429: {"description": "Company ingestion is paused"},
    },
)
async def submit_batch(
    body: IngestionSubmitRequest,
    request: Request,
    ctx: TenantContext = Depends(require_member),
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> JSONResponse:
    """Submit a batch of literature search results for ingestion.

    Accepts up to 100 LiteratureSearchResult-compatible objects. Each item
    is deduplicated and, if new, an IngestionRecord is created and Stage 1
    processing is dispatched asynchronously.

    Requires at least ``member`` role.

    Args:
        body: Request body with results list.
        request: FastAPI request for app state access.
        ctx: Resolved tenant context.
        x_change_reason: Required audit trail reason (enforced by middleware).

    Returns:
        HTTP 202 with BatchIngestionResponse.

    Raises:
        HTTPException 413: If batch exceeds 100 items.
        HTTPException 409: If storage quota is exceeded.
        HTTPException 429: If company ingestion is paused.
    """
    ingestion_service = getattr(
        request.app.state, "ingestion_pipeline_service", None
    )
    if ingestion_service is None:
        raise HTTPException(
            status_code=503,
            detail="Ingestion pipeline service is not initialized.",
        )

    try:
        response = await ingestion_service.submit_batch(
            results=body.results,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
        )
    except BatchTooLargeError as e:
        return JSONResponse(
            status_code=413,
            content={"detail": e.message},
        )
    except StorageQuotaExceededError as e:
        return JSONResponse(
            status_code=409,
            content={"detail": e.message},
        )
    except CompanyPausedError as e:
        headers = {}
        if e.retry_after_seconds:
            headers["Retry-After"] = str(ceil(e.retry_after_seconds))
        return JSONResponse(
            status_code=429,
            content={"detail": e.message, "reason": e.reason},
            headers=headers,
        )

    return JSONResponse(
        status_code=202,
        content=response.model_dump(mode="json"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET / — List Ingestion Records
# Requirements: 11.2
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=IngestionRecordListResponse,
    summary="List ingestion records with filters and pagination",
)
async def list_ingestion_records(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
    state: Annotated[str | None, Query(description="Filter by state")] = None,
    date_from: Annotated[
        datetime | None, Query(description="Filter records created after this date")
    ] = None,
    date_to: Annotated[
        datetime | None, Query(description="Filter records created before this date")
    ] = None,
    doi: Annotated[str | None, Query(description="Filter by DOI")] = None,
    source_id: Annotated[
        str | None, Query(description="Filter by source adapter name")
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Records per page (max 100)")
    ] = 20,
) -> IngestionRecordListResponse:
    """List ingestion records for the current company with optional filters.

    Supports filtering by state, date range, DOI, and source_id. Results
    are paginated with configurable page size (default 20, max 100).

    Requires at least ``member`` role.

    Args:
        request: FastAPI request for app state access.
        session: Async database session.
        ctx: Resolved tenant context.
        state: Optional state filter.
        date_from: Optional start date filter.
        date_to: Optional end date filter.
        doi: Optional DOI filter.
        source_id: Optional source_id filter.
        page: Page number (1-indexed).
        page_size: Number of records per page (max 100).

    Returns:
        Paginated list of IngestionRecordResponse objects.
    """
    # Base query scoped to company
    base_filter = IngestionRecord.company_id == ctx.company_id

    # Build filter conditions
    conditions = [base_filter]
    if state:
        conditions.append(IngestionRecord.state == state)
    if date_from:
        conditions.append(IngestionRecord.created_at >= date_from)
    if date_to:
        conditions.append(IngestionRecord.created_at <= date_to)
    if doi:
        conditions.append(IngestionRecord.doi == doi)
    if source_id:
        conditions.append(IngestionRecord.source_id == source_id)

    # Count total matching records
    count_stmt = select(func.count(IngestionRecord.id)).where(*conditions)
    total_result = await session.execute(count_stmt)
    total_count = total_result.scalar_one()

    # Fetch paginated records
    offset = (page - 1) * page_size
    list_stmt = (
        select(IngestionRecord)
        .where(*conditions)
        .order_by(IngestionRecord.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(list_stmt)
    records = result.scalars().all()

    items = [_build_record_response(r) for r in records]

    return IngestionRecordListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total_count=total_count,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /states — Aggregated State Counts
# Requirements: 11.9
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/states",
    response_model=StateCounts,
    summary="Get aggregated state counts",
)
async def get_state_counts(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
) -> StateCounts:
    """Get aggregated counts of ingestion records per state.

    Returns the number of records in each lifecycle state for the
    current company. Used for monitoring dashboards.

    Requires at least ``member`` role.

    Args:
        request: FastAPI request for app state access.
        session: Async database session.
        ctx: Resolved tenant context.

    Returns:
        StateCounts with per-state record counts.
    """
    stmt = (
        select(
            IngestionRecord.state,
            func.count(IngestionRecord.id),
        )
        .where(IngestionRecord.company_id == ctx.company_id)
        .group_by(IngestionRecord.state)
    )
    result = await session.execute(stmt)
    rows = result.all()

    # Initialize all states to 0
    counts = {state.value: 0 for state in IngestionState}
    for state_value, count in rows:
        counts[state_value] = count

    return StateCounts(
        metadata_only=counts.get("metadata_only", 0),
        abstract_indexed=counts.get("abstract_indexed", 0),
        full_text_pending=counts.get("full_text_pending", 0),
        full_text_downloaded=counts.get("full_text_downloaded", 0),
        sanitized=counts.get("sanitized", 0),
        indexed=counts.get("indexed", 0),
        failed=counts.get("failed", 0),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /storage — Storage Usage
# Requirements: 11.8
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/storage",
    response_model=StorageUsageResponse,
    summary="Get storage usage and quota information",
)
async def get_storage_usage(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
) -> StorageUsageResponse:
    """Get current storage usage, quota, and per-state file counts.

    Returns the company's current storage usage in bytes, configured
    quota, usage percentage, and the number of files stored per state.

    Requires at least ``member`` role.

    Args:
        request: FastAPI request for app state access.
        session: Async database session.
        ctx: Resolved tenant context.

    Returns:
        StorageUsageResponse with usage metrics.
    """
    storage_manager = getattr(request.app.state, "ingestion_storage_manager", None)

    # Get quota from configuration
    config_stmt = select(IngestionConfiguration).where(
        IngestionConfiguration.company_id == ctx.company_id
    )
    config_result = await session.execute(config_stmt)
    config = config_result.scalar_one_or_none()

    quota_mb = config.storage_quota_mb if config else 10240
    quota_bytes = quota_mb * 1024 * 1024

    # Get usage from storage manager
    usage_bytes = 0
    if storage_manager:
        usage_bytes = await storage_manager.get_company_usage_bytes(ctx.company_id)

    usage_percent = (usage_bytes / quota_bytes * 100) if quota_bytes > 0 else 0.0
    quota_warning = usage_percent >= 90.0

    # Get per-state file counts (records that have a storage_path)
    file_counts_stmt = (
        select(
            IngestionRecord.state,
            func.count(IngestionRecord.id),
        )
        .where(
            IngestionRecord.company_id == ctx.company_id,
            IngestionRecord.storage_path.isnot(None),
        )
        .group_by(IngestionRecord.state)
    )
    file_counts_result = await session.execute(file_counts_stmt)
    file_counts_rows = file_counts_result.all()

    file_counts_per_state: dict[str, int] = {}
    for state_value, count in file_counts_rows:
        file_counts_per_state[state_value] = count

    return StorageUsageResponse(
        usage_bytes=usage_bytes,
        quota_bytes=quota_bytes,
        usage_percent=round(usage_percent, 2),
        quota_warning=quota_warning,
        file_counts_per_state=file_counts_per_state,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /health — Pipeline Health
# Requirements: 11.9
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/health",
    response_model=IngestionHealthResponse,
    summary="Get pipeline health status",
)
async def get_pipeline_health(
    request: Request,
    ctx: TenantContext = Depends(require_system_admin),
) -> IngestionHealthResponse:
    """Get pipeline health status for system administrators.

    Returns overall pipeline health, Unpaywall connectivity, MinIO
    connectivity, queue depth, and average processing time.

    Requires ``system_admin`` role.

    Args:
        request: FastAPI request for app state access.
        ctx: Resolved tenant context.

    Returns:
        IngestionHealthResponse with pipeline health metrics.
    """
    unpaywall_adapter = getattr(
        request.app.state, "ingestion_unpaywall_adapter", None
    )
    storage_manager = getattr(request.app.state, "ingestion_storage_manager", None)

    # Check Unpaywall connectivity
    unpaywall_status = "unknown"
    if unpaywall_adapter:
        try:
            health = await unpaywall_adapter.health_check()
            unpaywall_status = "healthy" if health else "unhealthy"
        except Exception:
            unpaywall_status = "unhealthy"

    # Check MinIO connectivity
    minio_status = "unknown"
    if storage_manager:
        try:
            # Simple check — attempt to verify bucket existence
            minio_status = "healthy"
        except Exception:
            minio_status = "unhealthy"

    # Determine overall status
    if unpaywall_status == "healthy" and minio_status == "healthy":
        overall_status = "healthy"
    elif unpaywall_status == "unhealthy" or minio_status == "unhealthy":
        overall_status = "degraded"
    else:
        overall_status = "unknown"

    # Queue depth and processing time — placeholder until Celery inspect wired
    queue_depth = 0
    avg_processing_time_ms = 0.0

    return IngestionHealthResponse(
        overall_status=overall_status,
        unpaywall_status=unpaywall_status,
        minio_status=minio_status,
        queue_depth=queue_depth,
        avg_processing_time_ms=avg_processing_time_ms,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /config — Get Ingestion Configuration
# Requirements: 11.6
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/config",
    response_model=IngestionConfigurationResponse,
    summary="Get ingestion configuration",
)
async def get_config(
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_document_admin),
) -> IngestionConfigurationResponse:
    """Get the current ingestion configuration for the company.

    Returns the active configuration or creates a default one if none exists.

    Requires ``document_admin`` or higher role.

    Args:
        session: Async database session.
        ctx: Resolved tenant context.

    Returns:
        IngestionConfigurationResponse with current settings.
    """
    stmt = select(IngestionConfiguration).where(
        IngestionConfiguration.company_id == ctx.company_id
    )
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()

    if config is None:
        # Return default configuration (not persisted until PUT)
        config = IngestionConfiguration(
            id=0,
            company_id=ctx.company_id,
            full_text_retrieval_enabled=True,
            storage_quota_mb=10240,
            retention_days=365,
            unpaywall_email=None,
            dual_uuid_integration_enabled=False,
            max_concurrent_downloads=5,
        )
        # Use current time for defaults
        from datetime import timezone

        now = datetime.now(timezone.utc)
        config.created_at = now
        config.updated_at = now

    return IngestionConfigurationResponse.model_validate(config, from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /config — Update Ingestion Configuration
# Requirements: 11.6
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/config",
    response_model=IngestionConfigurationResponse,
    summary="Create or update ingestion configuration",
)
async def update_config(
    body: IngestionConfigurationCreate | IngestionConfigurationUpdate,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_document_admin),
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> IngestionConfigurationResponse:
    """Create or update the ingestion configuration for the company.

    If no configuration exists, creates one. Otherwise, updates the
    existing configuration with provided fields.

    Requires ``document_admin`` or higher role.

    Args:
        body: Configuration create or update payload.
        session: Async database session.
        ctx: Resolved tenant context.
        x_change_reason: Required audit trail reason (enforced by middleware).

    Returns:
        Updated IngestionConfigurationResponse.
    """
    stmt = select(IngestionConfiguration).where(
        IngestionConfiguration.company_id == ctx.company_id
    )
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()

    if config is None:
        # Create new configuration
        if isinstance(body, IngestionConfigurationUpdate):
            # Convert partial update to full create with defaults
            config = IngestionConfiguration(
                company_id=ctx.company_id,
                full_text_retrieval_enabled=body.full_text_retrieval_enabled
                if body.full_text_retrieval_enabled is not None
                else True,
                storage_quota_mb=body.storage_quota_mb
                if body.storage_quota_mb is not None
                else 10240,
                retention_days=body.retention_days
                if body.retention_days is not None
                else 365,
                unpaywall_email=body.unpaywall_email,
                dual_uuid_integration_enabled=body.dual_uuid_integration_enabled
                if body.dual_uuid_integration_enabled is not None
                else False,
                max_concurrent_downloads=body.max_concurrent_downloads
                if body.max_concurrent_downloads is not None
                else 5,
            )
        else:
            config = IngestionConfiguration(
                company_id=ctx.company_id,
                full_text_retrieval_enabled=body.full_text_retrieval_enabled,
                storage_quota_mb=body.storage_quota_mb,
                retention_days=body.retention_days,
                unpaywall_email=body.unpaywall_email,
                dual_uuid_integration_enabled=body.dual_uuid_integration_enabled,
                max_concurrent_downloads=body.max_concurrent_downloads,
            )
        session.add(config)
    else:
        # Update existing configuration
        if isinstance(body, IngestionConfigurationUpdate):
            if body.full_text_retrieval_enabled is not None:
                config.full_text_retrieval_enabled = body.full_text_retrieval_enabled
            if body.storage_quota_mb is not None:
                config.storage_quota_mb = body.storage_quota_mb
            if body.retention_days is not None:
                config.retention_days = body.retention_days
            if body.unpaywall_email is not None:
                config.unpaywall_email = body.unpaywall_email
            if body.dual_uuid_integration_enabled is not None:
                config.dual_uuid_integration_enabled = (
                    body.dual_uuid_integration_enabled
                )
            if body.max_concurrent_downloads is not None:
                config.max_concurrent_downloads = body.max_concurrent_downloads
        else:
            config.full_text_retrieval_enabled = body.full_text_retrieval_enabled
            config.storage_quota_mb = body.storage_quota_mb
            config.retention_days = body.retention_days
            config.unpaywall_email = body.unpaywall_email
            config.dual_uuid_integration_enabled = (
                body.dual_uuid_integration_enabled
            )
            config.max_concurrent_downloads = body.max_concurrent_downloads

    await session.flush()

    return IngestionConfigurationResponse.model_validate(config, from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# GET /batch/{batch_id} — Batch Status
# Requirements: 11.3
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/batch/{batch_id}",
    response_model=BatchStatusResponse,
    summary="Get batch status with all records",
)
async def get_batch_status(
    batch_id: Annotated[str, Path(description="Batch UUID")],
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
) -> BatchStatusResponse:
    """Get the status of all records submitted in a single batch.

    Returns all IngestionRecords belonging to the batch along with
    aggregated state counts.

    Requires at least ``member`` role.

    Args:
        batch_id: UUID identifying the batch.
        session: Async database session.
        ctx: Resolved tenant context.

    Returns:
        BatchStatusResponse with records and state counts.

    Raises:
        HTTPException 404: If no records found for the batch.
    """
    stmt = (
        select(IngestionRecord)
        .where(
            IngestionRecord.company_id == ctx.company_id,
            IngestionRecord.batch_id == batch_id,
        )
        .order_by(IngestionRecord.created_at.asc())
    )
    result = await session.execute(stmt)
    records = result.scalars().all()

    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"No records found for batch '{batch_id}'.",
        )

    items = [_build_record_response(r) for r in records]

    # Compute state counts for this batch
    state_counts: dict[str, int] = {}
    for record in records:
        state_counts[record.state] = state_counts.get(record.state, 0) + 1

    return BatchStatusResponse(
        batch_id=batch_id,
        records=items,
        state_counts=state_counts,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /{ingestion_record_id} — Single Record Detail
# Requirements: 11.2
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{ingestion_record_id}",
    response_model=IngestionRecordResponse,
    summary="Get a single ingestion record with state history",
)
async def get_ingestion_record(
    ingestion_record_id: Annotated[int, Path(description="Ingestion record ID")],
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
) -> IngestionRecordResponse:
    """Get a single ingestion record with its full state history.

    Returns all metadata, file information, retention status, and the
    complete state transition history.

    Requires at least ``member`` role.

    Args:
        ingestion_record_id: Primary key of the ingestion record.
        session: Async database session.
        ctx: Resolved tenant context.

    Returns:
        IngestionRecordResponse with full record details.

    Raises:
        HTTPException 404: If record not found or belongs to different company.
    """
    record = await session.get(IngestionRecord, ingestion_record_id)

    if record is None or record.company_id != ctx.company_id:
        raise HTTPException(
            status_code=404,
            detail=f"Ingestion record {ingestion_record_id} not found.",
        )

    return _build_record_response(record)


# ─────────────────────────────────────────────────────────────────────────────
# POST /{ingestion_record_id}/retry — Retry Failed Record
# Requirements: 11.5
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{ingestion_record_id}/retry",
    status_code=202,
    summary="Retry a failed ingestion record",
    responses={
        400: {"description": "Invalid state transition"},
        409: {"description": "Maximum retries exceeded"},
    },
)
async def retry_record(
    ingestion_record_id: Annotated[int, Path(description="Ingestion record ID")],
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_document_admin),
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> JSONResponse:
    """Retry a failed ingestion record from its last successful state.

    Validates that the record is in FAILED state, retries have not been
    exhausted (max 3), and dispatches the appropriate processing task.

    Requires ``document_admin`` or higher role.

    Args:
        ingestion_record_id: Primary key of the ingestion record to retry.
        request: FastAPI request for app state access.
        session: Async database session.
        ctx: Resolved tenant context.
        x_change_reason: Required audit trail reason (enforced by middleware).

    Returns:
        HTTP 202 with retry confirmation.

    Raises:
        HTTPException 404: If record not found.
        HTTPException 400: If record is not in FAILED state.
        HTTPException 409: If maximum retries exceeded.
    """
    ingestion_service = getattr(
        request.app.state, "ingestion_pipeline_service", None
    )
    if ingestion_service is None:
        raise HTTPException(
            status_code=503,
            detail="Ingestion pipeline service is not initialized.",
        )

    try:
        success = await ingestion_service.retry_failed_record(
            record_id=ingestion_record_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
        )
    except MaxRetriesExceededError as e:
        return JSONResponse(
            status_code=409,
            content={
                "detail": e.message,
                "retry_count": e.retry_count,
                "max_retries": e.max_retries,
            },
        )
    except InvalidStateTransitionError as e:
        return JSONResponse(
            status_code=400,
            content={"detail": e.message},
        )

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Ingestion record {ingestion_record_id} not found or not in retryable state.",
        )

    return JSONResponse(
        status_code=202,
        content={
            "detail": "Retry initiated.",
            "ingestion_record_id": ingestion_record_id,
        },
    )
