"""FastAPI router for hybrid and unified literature search endpoints.

Provides endpoints for:
- POST /literature/search/hybrid — Execute hybrid BM25+kNN search
- POST /literature/search/unified — Execute unified search across
  literature and internal document indices

Both endpoints require ``member`` role or higher and the ``X-Company-Id``
header for tenant resolution. Empty/whitespace queries are rejected with
HTTP 422. If the company's embedding index does not yet exist, an empty
result set (HTTP 200) is returned rather than an error.

References:
    - Requirements: 10.1, 10.2, 10.8, 10.9, 10.10, 4.7, 6.9, 11.5, 11.6
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.embedding.exceptions import SearchServiceUnavailableError
from alcoabase.literature.embedding.schemas.search import (
    HybridSearchRequestSchema,
    HybridSearchResponseSchema,
    HybridSearchResultSchema,
)
from alcoabase.literature.embedding.services.hybrid_query_engine import (
    HybridSearchRequest,
    HybridSearchResponse,
)
from alcoabase.literature.ingestion.models.ingestion import IngestionAuditLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/literature/search", tags=["Literature Hybrid Search"])


# ─────────────────────────────────────────────────────────────────────────────
# Role-checking dependency
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


require_member = _require_member()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_hybrid_query_engine(request: Request):
    """Retrieve the HybridQueryEngine from application state.

    Args:
        request: The current FastAPI request.

    Returns:
        HybridQueryEngine instance or None if not initialized.
    """
    return getattr(request.app.state, "hybrid_query_engine", None)


def _get_index_manager(request: Request):
    """Retrieve the LiteratureIndexManager from application state.

    Args:
        request: The current FastAPI request.

    Returns:
        LiteratureIndexManager instance or None if not initialized.
    """
    return getattr(request.app.state, "literature_index_manager", None)


async def _index_exists_for_company(request: Request, company_id: int) -> bool:
    """Check whether the literature embedding index exists for a company.

    Args:
        request: The current FastAPI request.
        company_id: The company identifier.

    Returns:
        True if the index exists, False otherwise.
    """
    index_manager = _get_index_manager(request)
    if index_manager is None:
        return False

    index_name = index_manager._index_name(company_id)
    try:
        return await index_manager._client.indices.exists(index=index_name)
    except Exception:
        return False


def _validate_query(query: str) -> None:
    """Validate that the query is not empty or whitespace-only.

    Args:
        query: The search query string.

    Raises:
        HTTPException: 422 if the query is empty or whitespace-only.
    """
    if not query or not query.strip():
        raise HTTPException(
            status_code=422,
            detail="Query must contain at least one non-whitespace character.",
        )


def _build_search_request(
    body: HybridSearchRequestSchema,
    ctx: TenantContext,
    include_internal: bool = False,
) -> HybridSearchRequest:
    """Convert Pydantic request schema to the engine's dataclass.

    Args:
        body: Validated request body from the endpoint.
        ctx: Resolved tenant context.
        include_internal: Whether to include internal documents.

    Returns:
        HybridSearchRequest dataclass for the engine.
    """
    return HybridSearchRequest(
        query=body.query.strip(),
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        partition_filter=body.partition_filter.value,
        semantic_weight=body.semantic_weight,
        rrf_k=body.rrf_k,
        page=body.page,
        page_size=body.page_size,
        literature_boost=body.literature_boost,
        internal_boost=body.internal_boost,
        date_range_start=(
            body.date_range.start.isoformat() if body.date_range and body.date_range.start else None
        ),
        date_range_end=(
            body.date_range.end.isoformat() if body.date_range and body.date_range.end else None
        ),
        source_id=body.source_id,
        authors=body.authors or [],
        publication_type=body.publication_type,
        include_internal=include_internal,
    )


def _response_from_engine(
    engine_response: HybridSearchResponse,
    query_time_ms: float,
) -> HybridSearchResponseSchema:
    """Convert engine response dataclass to Pydantic response schema.

    Args:
        engine_response: Response from HybridQueryEngine.
        query_time_ms: Search execution time in milliseconds.

    Returns:
        HybridSearchResponseSchema ready for serialization.
    """
    results = [
        HybridSearchResultSchema(
            chunk_text=r.chunk_text,
            title=r.title,
            authors=r.authors,
            doi=r.doi,
            publication_date=r.publication_date,
            source_id=r.source_id,
            relevance_score=min(r.relevance_score, 1.0),
            partition_tag=r.partition_tag,
            section_heading=r.section_heading,
            ingestion_record_id=r.ingestion_record_id,
        )
        for r in engine_response.results
    ]

    return HybridSearchResponseSchema(
        results=results,
        total_count=engine_response.total_count,
        page=engine_response.page,
        page_size=engine_response.page_size,
        degraded_mode=engine_response.degraded_mode,
        partial_results=engine_response.partial_results,
        unavailable_index=engine_response.unavailable_index,
        query_time_ms=query_time_ms,
    )


def _empty_response(
    page: int,
    page_size: int,
) -> HybridSearchResponseSchema:
    """Build an empty search response when the index doesn't exist.

    Args:
        page: Requested page number.
        page_size: Requested page size.

    Returns:
        HybridSearchResponseSchema with zero results.
    """
    return HybridSearchResponseSchema(
        results=[],
        total_count=0,
        page=page,
        page_size=page_size,
        degraded_mode=False,
        partial_results=False,
        unavailable_index=None,
        query_time_ms=0.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /hybrid — Hybrid Literature Search
# Requirements: 10.1, 10.8, 10.9, 10.10, 4.7, 6.9
# ─────────────────────────────────────────────────────────────────────────────


async def _log_search_query(
    session: AsyncSession,
    company_id: int,
    user_id: int,
    query_text_length: int,
    search_mode: str,
    result_count: int,
    response_time_ms: float,
    partition_filter: str,
) -> None:
    """Write an audit log entry for a search query execution (Req 11.5).

    Never logs the full query text or document content — only the
    query_text_length is recorded to comply with Req 11.6.

    Args:
        session: Active database session.
        company_id: Tenant scope.
        user_id: Requesting user.
        query_text_length: Length of the query text (NOT the text itself).
        search_mode: One of 'hybrid', 'unified', 'keyword-only', 'semantic-only'.
        result_count: Number of results returned.
        response_time_ms: Query execution time in milliseconds.
        partition_filter: Partition filter applied to the query.
    """
    log_entry = IngestionAuditLog(
        company_id=company_id,
        ingestion_record_id=None,
        event_type="search_query",
        details={
            "query_text_length": query_text_length,
            "search_mode": search_mode,
            "result_count": result_count,
            "response_time_ms": round(response_time_ms, 2),
            "partition_filter": partition_filter,
        },
        user_id=user_id,
    )
    session.add(log_entry)
    await session.commit()


@router.post(
    "/hybrid",
    response_model=HybridSearchResponseSchema,
    summary="Execute hybrid BM25 + semantic search",
    responses={
        400: {"description": "Missing X-Company-Id header"},
        403: {"description": "Insufficient permissions"},
        422: {"description": "Invalid query or parameters"},
        503: {"description": "Search service unavailable"},
    },
)
async def search_hybrid(
    body: HybridSearchRequestSchema,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
) -> HybridSearchResponseSchema:
    """Execute a hybrid BM25 + kNN semantic search against literature embeddings.

    Combines keyword matching (BM25) with semantic similarity (kNN) via
    reciprocal rank fusion (RRF). Returns paginated results scoped to the
    requesting company's vector space.

    Requires at least the ``member`` role and the ``X-Company-Id`` header.

    Args:
        body: Validated search request with query, filters, and scoring params.
        request: FastAPI request for app state access.
        session: Async database session for audit logging.
        ctx: Resolved tenant context with company_id and user_id.

    Returns:
        HybridSearchResponseSchema with fused search results.

    Raises:
        HTTPException 400: If X-Company-Id header is missing.
        HTTPException 403: If user lacks member role.
        HTTPException 422: If query is empty/whitespace-only.
        HTTPException 503: If search service is unavailable.
    """
    # Validate non-empty query
    _validate_query(body.query)

    # Validate X-Company-Id is present (handled by tenant dependency,
    # but we enforce it explicitly per requirement 4.7)
    company_id_header = request.headers.get("X-Company-Id")
    if not company_id_header:
        raise HTTPException(
            status_code=400,
            detail="X-Company-Id header is required.",
        )

    # Check if index exists — return empty results if not
    if not await _index_exists_for_company(request, ctx.company_id):
        return _empty_response(body.page, body.page_size)

    # Get the query engine
    query_engine = _get_hybrid_query_engine(request)
    if query_engine is None:
        raise HTTPException(
            status_code=503,
            detail="Search service is not initialized.",
        )

    # Build engine request and execute
    search_request = _build_search_request(body, ctx, include_internal=False)

    start_time = time.perf_counter()
    try:
        engine_response = await query_engine.search(search_request)
    except SearchServiceUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="Search service is temporarily unavailable.",
        )
    query_time_ms = (time.perf_counter() - start_time) * 1000

    # Audit log: record search query (Req 11.5) — never log full query text (Req 11.6)
    try:
        await _log_search_query(
            session=session,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            query_text_length=len(body.query),
            search_mode="hybrid",
            result_count=engine_response.total_count,
            response_time_ms=query_time_ms,
            partition_filter=body.partition_filter.value,
        )
    except Exception:
        # Audit logging failure should not break the search response
        logger.warning(
            "Failed to write search query audit log for company %d.",
            ctx.company_id,
            exc_info=True,
        )

    return _response_from_engine(engine_response, query_time_ms)


# ─────────────────────────────────────────────────────────────────────────────
# POST /unified — Unified Search (Literature + Internal)
# Requirements: 10.2, 10.8, 10.9, 10.10, 4.7, 6.9
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/unified",
    response_model=HybridSearchResponseSchema,
    summary="Execute unified search across literature and internal documents",
    responses={
        400: {"description": "Missing X-Company-Id header"},
        403: {"description": "Insufficient permissions"},
        422: {"description": "Invalid query or parameters"},
        503: {"description": "Search service unavailable"},
    },
)
async def search_unified(
    body: HybridSearchRequestSchema,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: TenantContext = Depends(require_member),
) -> HybridSearchResponseSchema:
    """Execute unified search across literature and internal document indices.

    Queries both the company's literature embedding index and internal
    knowledge index, merging results with RRF and applying partition
    boosting. Respects ABAC permissions for internal documents.

    Requires at least the ``member`` role and the ``X-Company-Id`` header.

    Args:
        body: Validated search request with query, filters, and scoring params.
        request: FastAPI request for app state access.
        session: Async database session for audit logging.
        ctx: Resolved tenant context with company_id and user_id.

    Returns:
        HybridSearchResponseSchema with merged results from both indices.

    Raises:
        HTTPException 400: If X-Company-Id header is missing.
        HTTPException 403: If user lacks member role.
        HTTPException 422: If query is empty/whitespace-only.
        HTTPException 503: If search service is unavailable.
    """
    # Validate non-empty query
    _validate_query(body.query)

    # Validate X-Company-Id is present
    company_id_header = request.headers.get("X-Company-Id")
    if not company_id_header:
        raise HTTPException(
            status_code=400,
            detail="X-Company-Id header is required.",
        )

    # Check if index exists — return empty results if not
    if not await _index_exists_for_company(request, ctx.company_id):
        return _empty_response(body.page, body.page_size)

    # Get the query engine
    query_engine = _get_hybrid_query_engine(request)
    if query_engine is None:
        raise HTTPException(
            status_code=503,
            detail="Search service is not initialized.",
        )

    # Build engine request with include_internal from body
    search_request = _build_search_request(
        body, ctx, include_internal=body.include_internal
    )

    start_time = time.perf_counter()
    try:
        engine_response = await query_engine.unified_search(search_request)
    except SearchServiceUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="Search service is temporarily unavailable.",
        )
    query_time_ms = (time.perf_counter() - start_time) * 1000

    # Audit log: record search query (Req 11.5) — never log full query text (Req 11.6)
    try:
        await _log_search_query(
            session=session,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            query_text_length=len(body.query),
            search_mode="unified",
            result_count=engine_response.total_count,
            response_time_ms=query_time_ms,
            partition_filter=body.partition_filter.value,
        )
    except Exception:
        # Audit logging failure should not break the search response
        logger.warning(
            "Failed to write search query audit log for company %d.",
            ctx.company_id,
            exc_info=True,
        )

    return _response_from_engine(engine_response, query_time_ms)
