"""FastAPI router for literature embedding index management endpoints.

Provides endpoints for:
- Index status monitoring (GET /status)
- Batch re-indexing initiation (POST /reindex)
- Re-indexing progress tracking (GET /reindex/{task_id})
- Embedding configuration read (GET /config)
- Embedding configuration update (PUT /config)

All endpoints require the X-Company-Id header for multi-tenancy.
Mutation endpoints (POST, PUT) require the X-Change-Reason header.

References:
    - Requirements: 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 9.7, 9.8, 9.9, 8.7
    - Design doc: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.embedding.exceptions import ReindexAlreadyActiveError
from alcoabase.literature.embedding.models.embedding_config import (
    EmbeddingConfiguration,
)
from alcoabase.literature.embedding.schemas.configuration import (
    EmbeddingConfigurationSchema,
    EmbeddingConfigurationUpdateSchema,
)
from alcoabase.literature.embedding.schemas.indexing import (
    IndexStatusSchema,
    ReindexProgressSchema,
    ReindexRequestSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/literature/index", tags=["literature-index"])


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
# GET /status — Index Status
# Requirements: 10.3, 10.8
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/status",
    response_model=IndexStatusSchema,
    summary="Get index health and statistics",
)
async def get_index_status(
    request: Request,
    ctx: TenantContext = Depends(require_member),
) -> IndexStatusSchema:
    """Get the OpenSearch index health and statistics for the requesting company.

    Returns index health status (green/yellow/red), document count,
    total chunks indexed, index size in bytes, and last indexing timestamp.

    Requires at least ``member`` role.

    Args:
        request: FastAPI request for app state access.
        ctx: Resolved tenant context.

    Returns:
        IndexStatusSchema with index health and statistics.

    Raises:
        HTTPException 503: If the index manager is not initialized.
    """
    index_manager = getattr(request.app.state, "literature_index_manager", None)
    if index_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Literature index service is not initialized.",
        )

    stats = await index_manager.get_index_stats(ctx.company_id)

    # Parse last_indexing_timestamp if it's a string
    last_indexing_ts = stats.get("last_indexing_timestamp")
    if isinstance(last_indexing_ts, str):
        try:
            last_indexing_ts = datetime.fromisoformat(last_indexing_ts)
        except (ValueError, TypeError):
            last_indexing_ts = None

    # Map 'unavailable' health to 'red' for the schema enum
    health = stats.get("health", "red")
    if health not in ("green", "yellow", "red"):
        health = "red"

    doc_count = stats.get("doc_count", 0)

    return IndexStatusSchema(
        health=health,
        doc_count=doc_count,
        chunks_indexed=doc_count,
        size_bytes=stats.get("size_bytes", 0),
        last_indexing_timestamp=last_indexing_ts,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /reindex — Initiate Re-indexing
# Requirements: 10.4, 10.7, 10.8, 8.7
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/reindex",
    status_code=202,
    summary="Initiate batch re-indexing",
    responses={
        409: {"description": "Re-indexing job already active for this company"},
        503: {"description": "Embedding service is not initialized"},
    },
)
async def initiate_reindex(
    request: Request,
    body: ReindexRequestSchema | None = None,
    ctx: TenantContext = Depends(require_system_admin),
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> JSONResponse:
    """Initiate a batch re-indexing operation for the requesting company.

    Creates a new re-indexing job and dispatches the first batch via Celery.
    Only one re-indexing job may be active per company at a time.

    Requires ``system_admin`` role and X-Change-Reason header.

    Args:
        request: FastAPI request for app state access.
        body: Optional request body with state_filter or record_ids.
        ctx: Resolved tenant context.
        x_change_reason: Required audit trail reason.

    Returns:
        HTTP 202 with task_id for progress tracking.

    Raises:
        HTTPException 400: If X-Change-Reason header is missing.
        HTTPException 409: If a re-indexing job is already active.
        HTTPException 503: If embedding service is not initialized.
    """
    if not x_change_reason or not x_change_reason.strip():
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header is required for re-indexing operations.",
        )

    embedding_service = getattr(request.app.state, "embedding_service", None)
    if embedding_service is None:
        raise HTTPException(
            status_code=503,
            detail="Embedding service is not initialized.",
        )

    state_filter = body.state_filter if body else None
    record_ids = body.record_ids if body else None

    try:
        task_id = await embedding_service.initiate_reindex(
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            reason=x_change_reason,
            state_filter=state_filter,
            record_ids=record_ids,
        )
    except ReindexAlreadyActiveError as e:
        return JSONResponse(
            status_code=409,
            content={
                "detail": e.message,
                "active_task_id": e.active_task_id,
                "progress_percent": e.progress_percent,
            },
        )

    return JSONResponse(
        status_code=202,
        content={"task_id": task_id},
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /reindex/{task_id} — Re-indexing Progress
# Requirements: 10.5, 10.8
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/reindex/{task_id}",
    response_model=ReindexProgressSchema,
    summary="Get re-indexing progress",
    responses={
        404: {"description": "Re-indexing job not found"},
        503: {"description": "Embedding service is not initialized"},
    },
)
async def get_reindex_progress(
    task_id: Annotated[str, Path(description="Re-indexing job task ID (UUID)")],
    request: Request,
    ctx: TenantContext = Depends(require_system_admin),
) -> ReindexProgressSchema:
    """Get progress information for a re-indexing job.

    Returns completion percentage, records processed/failed counts,
    batch progress, and estimated time remaining.

    Requires ``system_admin`` role.

    Args:
        task_id: UUID of the re-indexing job.
        request: FastAPI request for app state access.
        ctx: Resolved tenant context.

    Returns:
        ReindexProgressSchema with progress details.

    Raises:
        HTTPException 404: If the job is not found for this company.
        HTTPException 503: If embedding service is not initialized.
    """
    embedding_service = getattr(request.app.state, "embedding_service", None)
    if embedding_service is None:
        raise HTTPException(
            status_code=503,
            detail="Embedding service is not initialized.",
        )

    progress = await embedding_service.get_reindex_progress(
        task_id=task_id,
        company_id=ctx.company_id,
    )

    if progress.get("status") == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"Re-indexing job '{task_id}' not found.",
        )

    return ReindexProgressSchema(
        task_id=task_id,
        status=progress["status"],
        progress_percent=int(progress.get("percentage", 0)),
        total_records=progress.get("total_records", 0),
        records_processed=progress.get("records_processed", 0),
        records_failed=progress.get("records_failed", 0),
        current_batch=progress.get("current_batch", 0),
        total_batches=progress.get("total_batches", 0),
        estimated_remaining_seconds=progress.get("estimated_remaining_seconds"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /config — Get Embedding Configuration
# Requirements: 10.6, 9.7, 9.8
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/config",
    response_model=EmbeddingConfigurationSchema,
    summary="Get embedding configuration",
)
async def get_embedding_config(
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_document_admin),
) -> EmbeddingConfigurationSchema:
    """Get the current embedding configuration for the requesting company.

    Returns the active configuration or a default configuration if none
    has been explicitly set.

    Requires ``document_admin`` or higher role.

    Args:
        session: Async database session.
        ctx: Resolved tenant context.

    Returns:
        EmbeddingConfigurationSchema with current settings.
    """
    stmt = select(EmbeddingConfiguration).where(
        EmbeddingConfiguration.company_id == ctx.company_id
    )
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()

    if config is None:
        # Return default configuration (not persisted until PUT)
        now = datetime.now(timezone.utc)
        return EmbeddingConfigurationSchema(
            id=0,
            company_id=ctx.company_id,
            chunk_size_tokens=512,
            chunk_overlap_tokens=50,
            auto_embed_on_ingest=True,
            embed_abstract_only=False,
            max_chunks_per_document=500,
            created_at=now,
            updated_at=now,
        )

    return EmbeddingConfigurationSchema.model_validate(config, from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /config — Update Embedding Configuration
# Requirements: 10.6, 10.7, 9.7, 9.8, 9.9
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/config",
    response_model=EmbeddingConfigurationSchema,
    summary="Update embedding configuration",
    responses={
        422: {"description": "Configuration value outside valid range"},
    },
)
async def update_embedding_config(
    body: EmbeddingConfigurationUpdateSchema,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_document_admin),
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> EmbeddingConfigurationSchema:
    """Update the embedding configuration for the requesting company.

    Creates a new configuration if none exists, or updates the existing one.
    Validates all numeric ranges (HTTP 422 on violation). Records the change
    in the audit trail.

    Requires ``document_admin`` or higher role and X-Change-Reason header.

    Args:
        body: Configuration update payload with optional fields.
        session: Async database session.
        ctx: Resolved tenant context.
        x_change_reason: Required audit trail reason.

    Returns:
        Updated EmbeddingConfigurationSchema.

    Raises:
        HTTPException 400: If X-Change-Reason header is missing.
        HTTPException 422: If values are outside valid ranges (handled by Pydantic).
    """
    if not x_change_reason or not x_change_reason.strip():
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header is required for configuration updates.",
        )

    stmt = select(EmbeddingConfiguration).where(
        EmbeddingConfiguration.company_id == ctx.company_id
    )
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()

    # Capture previous values for audit log
    previous_values: dict[str, Any] = {}

    if config is None:
        # Create new configuration with defaults, overridden by provided values
        config = EmbeddingConfiguration(
            company_id=ctx.company_id,
            chunk_size_tokens=body.chunk_size_tokens if body.chunk_size_tokens is not None else 512,
            chunk_overlap_tokens=body.chunk_overlap_tokens if body.chunk_overlap_tokens is not None else 50,
            auto_embed_on_ingest=body.auto_embed_on_ingest if body.auto_embed_on_ingest is not None else True,
            embed_abstract_only=body.embed_abstract_only if body.embed_abstract_only is not None else False,
            max_chunks_per_document=body.max_chunks_per_document if body.max_chunks_per_document is not None else 500,
        )
        session.add(config)
        previous_values = {"created": True}
    else:
        # Capture previous values before update
        previous_values = {
            "chunk_size_tokens": config.chunk_size_tokens,
            "chunk_overlap_tokens": config.chunk_overlap_tokens,
            "auto_embed_on_ingest": config.auto_embed_on_ingest,
            "embed_abstract_only": config.embed_abstract_only,
            "max_chunks_per_document": config.max_chunks_per_document,
        }

        # Apply partial updates
        if body.chunk_size_tokens is not None:
            config.chunk_size_tokens = body.chunk_size_tokens
        if body.chunk_overlap_tokens is not None:
            config.chunk_overlap_tokens = body.chunk_overlap_tokens
        if body.auto_embed_on_ingest is not None:
            config.auto_embed_on_ingest = body.auto_embed_on_ingest
        if body.embed_abstract_only is not None:
            config.embed_abstract_only = body.embed_abstract_only
        if body.max_chunks_per_document is not None:
            config.max_chunks_per_document = body.max_chunks_per_document

    await session.flush()

    # Write audit log entry (Req 9.7, 11.1)
    new_values = {
        "chunk_size_tokens": config.chunk_size_tokens,
        "chunk_overlap_tokens": config.chunk_overlap_tokens,
        "auto_embed_on_ingest": config.auto_embed_on_ingest,
        "embed_abstract_only": config.embed_abstract_only,
        "max_chunks_per_document": config.max_chunks_per_document,
    }

    from alcoabase.literature.ingestion.models.ingestion import IngestionAuditLog

    audit_entry = IngestionAuditLog(
        company_id=ctx.company_id,
        ingestion_record_id=None,
        event_type="embedding_config_updated",
        details={
            "previous_values": previous_values,
            "new_values": new_values,
            "reason": x_change_reason,
        },
        user_id=ctx.user_id,
    )
    session.add(audit_entry)

    await session.commit()

    logger.info(
        "Embedding configuration updated for company %d by user %d. "
        "Previous: %s, New: %s. Reason: %s",
        ctx.company_id,
        ctx.user_id,
        previous_values,
        new_values,
        x_change_reason,
    )

    return EmbeddingConfigurationSchema.model_validate(config, from_attributes=True)
