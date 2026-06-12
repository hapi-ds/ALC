"""FastAPI router for Phase 9.6 Literature Search, Citation UI & Traceability endpoints.

Provides 17 endpoints under ``/literature-search`` for:
- Search execution (query, saved searches)
- One-click internalization
- Citation collection management
- Traceability link CRUD
- CSV/PDF export with PRISMA flow

All endpoints require tenant context via ``X-Company-Id`` and appropriate
role checks. The ``X-Change-Reason`` header is enforced globally by
AuditMiddleware and is not re-checked here.

References:
    - Requirements: 1.1–7.5
    - Design: .kiro/specs/Step_9-6_literature-search-citation-ui/design.md
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.search.exceptions import (
    CollectionCapacityExceededError,
    DuplicateInternalizationError,
    ExportReferenceNotFoundError,
    IngestionRecordNotFoundError,
    InsufficientPermissionsError,
    InvalidTraceabilityTargetError,
    NonInternalizedDocumentError,
    SavedSearchLimitExceededError,
    SearchUnavailableError,
)
from alcoabase.literature.search.schemas.citation_collection import (
    AddDocumentsRequest,
    CitationCollectionDetailResponse,
    CitationCollectionResponse,
    CreateCitationCollectionRequest,
    PaginatedCitationCollectionResponse,
    UpdateCitationCollectionRequest,
)
from alcoabase.literature.search.schemas.export import ExportRequest
from alcoabase.literature.search.schemas.internalization import (
    InternalizationRequest,
    InternalizedDocumentResponse,
)
from alcoabase.literature.search.schemas.query import (
    LiteratureSearchQueryRequest,
    PaginatedSearchResponse,
)
from alcoabase.literature.search.schemas.saved_search import (
    CreateSavedSearchRequest,
    PaginatedSavedSearchResponse,
    SavedSearchResponse,
)
from alcoabase.literature.search.schemas.traceability import (
    CreateTraceabilityLinksRequest,
    PaginatedTraceabilityLinksResponse,
    TraceabilityLinkResponse,
)
from alcoabase.literature.search.services.export_service import ExportService
from alcoabase.literature.search.services.literature_search_service import (
    LiteratureSearchService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/literature-search",
    tags=["Literature Search & Citation UI"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Role-checking dependencies
# ─────────────────────────────────────────────────────────────────────────────

_MEMBER_ROLES = {"member", "document_admin", "system_admin", "admin"}
_DOCUMENT_ADMIN_ROLES = {"document_admin", "system_admin", "admin"}


async def require_member(
    tenant: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """Enforce at least member role.

    Args:
        tenant: Resolved tenant context.

    Returns:
        The tenant context if authorized.

    Raises:
        HTTPException 403: If user lacks member role.
    """
    if tenant.membership_role not in _MEMBER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions. Requires at least member role.",
        )
    return tenant


async def require_document_admin(
    tenant: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """Enforce at least document_admin role.

    Args:
        tenant: Resolved tenant context.

    Returns:
        The tenant context if authorized.

    Raises:
        HTTPException 403: If user lacks document_admin role.
    """
    if tenant.membership_role not in _DOCUMENT_ADMIN_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions. Requires document_admin role or higher.",
        )
    return tenant


# ─────────────────────────────────────────────────────────────────────────────
# Service dependencies
# ─────────────────────────────────────────────────────────────────────────────


async def get_literature_search_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> LiteratureSearchService:
    """Build LiteratureSearchService from app state and session.

    Retrieves HybridQueryEngine, AuditTrailService, TraceabilityMatrixService,
    and storage_client from the application state.

    Args:
        request: FastAPI request for app state access.
        session: Active async database session.

    Returns:
        Configured LiteratureSearchService instance.
    """
    app_state = request.app.state
    hybrid_query_engine = getattr(app_state, "hybrid_query_engine", None)
    audit_trail_service = getattr(app_state, "audit_trail_service", None)
    traceability_matrix_service = getattr(app_state, "traceability_matrix_service", None)
    storage_client = getattr(app_state, "storage_client", None)

    return LiteratureSearchService(
        session=session,
        hybrid_query_engine=hybrid_query_engine,
        audit_trail_service=audit_trail_service,
        traceability_matrix_service=traceability_matrix_service,
        storage_client=storage_client,
    )


async def get_export_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ExportService:
    """Build ExportService from app state and session.

    Args:
        request: FastAPI request for app state access.
        session: Active async database session.

    Returns:
        Configured ExportService instance.
    """
    query_engine = getattr(request.app.state, "hybrid_query_engine", None)
    return ExportService(session=session, query_engine=query_engine)


# ─────────────────────────────────────────────────────────────────────────────
# Exception-to-HTTP mapping helper
# ─────────────────────────────────────────────────────────────────────────────


def _handle_service_error(exc: Exception) -> HTTPException:
    """Map domain exceptions to appropriate HTTP error responses.

    Args:
        exc: The caught exception from the service layer.

    Returns:
        HTTPException with the appropriate status code and detail message.
    """
    if isinstance(exc, SearchUnavailableError):
        return HTTPException(status_code=503, detail=exc.message)
    if isinstance(exc, DuplicateInternalizationError):
        return HTTPException(status_code=409, detail=exc.message)
    if isinstance(exc, IngestionRecordNotFoundError):
        return HTTPException(status_code=404, detail=exc.message)
    if isinstance(exc, InsufficientPermissionsError):
        return HTTPException(status_code=403, detail=exc.message)
    if isinstance(exc, SavedSearchLimitExceededError):
        return HTTPException(status_code=422, detail=exc.message)
    if isinstance(exc, CollectionCapacityExceededError):
        return HTTPException(status_code=422, detail=exc.message)
    if isinstance(exc, NonInternalizedDocumentError):
        return HTTPException(status_code=422, detail=exc.message)
    if isinstance(exc, InvalidTraceabilityTargetError):
        return HTTPException(status_code=404, detail=exc.message)
    if isinstance(exc, ExportReferenceNotFoundError):
        return HTTPException(status_code=404, detail=exc.message)
    if isinstance(exc, ValueError):
        return HTTPException(status_code=404, detail=str(exc))
    # Fallback
    return HTTPException(status_code=500, detail="Internal server error.")


# ─────────────────────────────────────────────────────────────────────────────
# 1. POST /query — Execute literature search
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/query",
    response_model=PaginatedSearchResponse,
    summary="Execute a literature search query",
    responses={
        403: {"description": "Insufficient permissions"},
        422: {"description": "Invalid query parameters"},
        503: {"description": "Search service unavailable"},
    },
)
async def execute_search(
    body: LiteratureSearchQueryRequest,
    ctx: TenantContext = Depends(require_member),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> PaginatedSearchResponse:
    """Execute a hybrid literature search with faceted filtering.

    Args:
        body: Search query with filters, mode, and pagination.
        ctx: Resolved tenant context (member+ role).
        service: LiteratureSearchService dependency.

    Returns:
        Paginated search results with facets and execution ID.
    """
    try:
        result = await service.execute_search(
            query_text=body.query_text,
            filters=body.filters.model_dump(),
            search_mode=body.search_mode.value,
            include_internal=body.include_internal,
            page=body.page,
            page_size=body.page_size,
            user_id=ctx.user_id,
            company_id=ctx.company_id,
        )
        return PaginatedSearchResponse(**result)
    except (SearchUnavailableError, ValueError) as exc:
        raise _handle_service_error(exc)


# ─────────────────────────────────────────────────────────────────────────────
# 2. POST /saved-searches — Create saved search
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/saved-searches",
    response_model=SavedSearchResponse,
    status_code=201,
    summary="Create a saved search",
    responses={
        403: {"description": "Insufficient permissions"},
        422: {"description": "Saved search limit exceeded or invalid input"},
    },
)
async def create_saved_search(
    body: CreateSavedSearchRequest,
    ctx: TenantContext = Depends(require_member),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> SavedSearchResponse:
    """Persist a search configuration for later re-execution.

    Args:
        body: Saved search parameters.
        ctx: Resolved tenant context (member+ role).
        service: LiteratureSearchService dependency.

    Returns:
        The created saved search record.
    """
    try:
        result = await service.create_saved_search(
            name=body.name,
            description=body.description,
            query_text=body.query_text,
            filters=body.filters.model_dump(),
            search_mode=body.search_mode.value,
            include_internal=body.include_internal,
            user_id=ctx.user_id,
            company_id=ctx.company_id,
        )
        return SavedSearchResponse(**result)
    except SavedSearchLimitExceededError as exc:
        raise _handle_service_error(exc)


# ─────────────────────────────────────────────────────────────────────────────
# 3. GET /saved-searches — List saved searches
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/saved-searches",
    response_model=PaginatedSavedSearchResponse,
    summary="List saved searches",
    responses={
        403: {"description": "Insufficient permissions"},
    },
)
async def list_saved_searches(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: TenantContext = Depends(require_member),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> PaginatedSavedSearchResponse:
    """List saved searches for the current user with pagination.

    Args:
        page: Page number (1-indexed).
        page_size: Results per page.
        ctx: Resolved tenant context (member+ role).
        service: LiteratureSearchService dependency.

    Returns:
        Paginated list of saved searches.
    """
    result = await service.list_saved_searches(
        user_id=ctx.user_id,
        company_id=ctx.company_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedSavedSearchResponse(**result)


# ─────────────────────────────────────────────────────────────────────────────
# 4. POST /saved-searches/{id}/execute — Execute a saved search
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/saved-searches/{saved_search_id}/execute",
    response_model=PaginatedSearchResponse,
    summary="Re-execute a saved search",
    responses={
        403: {"description": "Insufficient permissions"},
        404: {"description": "Saved search not found"},
        503: {"description": "Search service unavailable"},
    },
)
async def execute_saved_search(
    saved_search_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: TenantContext = Depends(require_member),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> PaginatedSearchResponse:
    """Re-execute a saved search using its stored parameters.

    Args:
        saved_search_id: ID of the saved search.
        page: Page number for result pagination.
        page_size: Results per page.
        ctx: Resolved tenant context (owner/document_admin).
        service: LiteratureSearchService dependency.

    Returns:
        Paginated search results.
    """
    try:
        result = await service.execute_saved_search(
            saved_search_id=saved_search_id,
            user_id=ctx.user_id,
            company_id=ctx.company_id,
            page=page,
            page_size=page_size,
        )
        return PaginatedSearchResponse(**result)
    except (ValueError, SearchUnavailableError) as exc:
        raise _handle_service_error(exc)


# ─────────────────────────────────────────────────────────────────────────────
# 5. DELETE /saved-searches/{id} — Delete a saved search
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/saved-searches/{saved_search_id}",
    status_code=204,
    summary="Delete a saved search",
    responses={
        403: {"description": "Insufficient permissions"},
        404: {"description": "Saved search not found"},
    },
)
async def delete_saved_search(
    saved_search_id: int,
    ctx: TenantContext = Depends(require_member),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> None:
    """Delete (archive) a saved search.

    Args:
        saved_search_id: ID of the saved search.
        ctx: Resolved tenant context (owner/document_admin).
        service: LiteratureSearchService dependency.
    """
    try:
        await service.delete_saved_search(
            saved_search_id=saved_search_id,
            user_id=ctx.user_id,
            company_id=ctx.company_id,
        )
    except ValueError as exc:
        raise _handle_service_error(exc)


# ─────────────────────────────────────────────────────────────────────────────
# 6. POST /internalize — One-click internalization
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/internalize",
    response_model=InternalizedDocumentResponse,
    status_code=201,
    summary="Internalize a literature record as a managed document",
    responses={
        403: {"description": "Insufficient permissions"},
        404: {"description": "Ingestion record not found"},
        409: {"description": "Already internalized"},
        422: {"description": "Validation error"},
    },
)
async def internalize(
    body: InternalizationRequest,
    ctx: TenantContext = Depends(require_document_admin),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> InternalizedDocumentResponse:
    """Convert an IngestionRecord into a managed internal Document.

    Args:
        body: Internalization request with optional links and collection.
        ctx: Resolved tenant context (document_admin+ role).
        service: LiteratureSearchService dependency.

    Returns:
        The newly created Document details.
    """
    try:
        result = await service.internalize(
            ingestion_record_id=body.ingestion_record_id,
            user_id=ctx.user_id,
            company_id=ctx.company_id,
            document_name=body.document_name,
            document_type=body.document_type,
            tags=body.tags,
            traceability_links=[
                link.model_dump() for link in body.traceability_links
            ] if body.traceability_links else None,
            citation_collection_id=body.citation_collection_id,
        )
        return InternalizedDocumentResponse(**result)
    except (
        IngestionRecordNotFoundError,
        DuplicateInternalizationError,
        NonInternalizedDocumentError,
        InvalidTraceabilityTargetError,
        CollectionCapacityExceededError,
        ValueError,
    ) as exc:
        raise _handle_service_error(exc)


# ─────────────────────────────────────────────────────────────────────────────
# 7. POST /citation-collections — Create citation collection
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/citation-collections",
    response_model=CitationCollectionResponse,
    status_code=201,
    summary="Create a citation collection",
    responses={
        403: {"description": "Insufficient permissions"},
        422: {"description": "Invalid input"},
    },
)
async def create_citation_collection(
    body: CreateCitationCollectionRequest,
    ctx: TenantContext = Depends(require_document_admin),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> CitationCollectionResponse:
    """Create a new citation collection for organizing literature documents.

    Args:
        body: Collection creation parameters.
        ctx: Resolved tenant context (document_admin+ role).
        service: LiteratureSearchService dependency.

    Returns:
        The created citation collection.
    """
    try:
        result = await service.create_citation_collection(
            name=body.name,
            description=body.description,
            purpose=body.purpose.value,
            user_id=ctx.user_id,
            company_id=ctx.company_id,
        )
        return CitationCollectionResponse(**result)
    except ValueError as exc:
        raise _handle_service_error(exc)


# ─────────────────────────────────────────────────────────────────────────────
# 8. GET /citation-collections — List citation collections
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/citation-collections",
    response_model=PaginatedCitationCollectionResponse,
    summary="List citation collections",
    responses={
        403: {"description": "Insufficient permissions"},
    },
)
async def list_citation_collections(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    purpose: str | None = Query(default=None),
    ctx: TenantContext = Depends(require_member),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> PaginatedCitationCollectionResponse:
    """List citation collections with pagination and optional purpose filter.

    Args:
        page: Page number (1-indexed).
        page_size: Results per page.
        purpose: Optional purpose filter.
        ctx: Resolved tenant context (member+ role).
        service: LiteratureSearchService dependency.

    Returns:
        Paginated list of citation collections.
    """
    result = await service.list_citation_collections(
        company_id=ctx.company_id,
        page=page,
        page_size=page_size,
        purpose=purpose,
    )
    return PaginatedCitationCollectionResponse(**result)


# ─────────────────────────────────────────────────────────────────────────────
# 9. GET /citation-collections/{id} — Get citation collection detail
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/citation-collections/{collection_id}",
    response_model=CitationCollectionDetailResponse,
    summary="Get citation collection detail with documents",
    responses={
        403: {"description": "Insufficient permissions"},
        404: {"description": "Collection not found"},
    },
)
async def get_citation_collection(
    collection_id: int,
    ctx: TenantContext = Depends(require_member),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> CitationCollectionDetailResponse:
    """Retrieve a citation collection with its ordered document list.

    Args:
        collection_id: ID of the citation collection.
        ctx: Resolved tenant context (member+ role).
        service: LiteratureSearchService dependency.

    Returns:
        Citation collection detail with documents.
    """
    try:
        result = await service.get_citation_collection(
            collection_id=collection_id,
            company_id=ctx.company_id,
        )
        return CitationCollectionDetailResponse(**result)
    except ValueError as exc:
        raise _handle_service_error(exc)


# ─────────────────────────────────────────────────────────────────────────────
# 10. PUT /citation-collections/{id} — Update citation collection
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/citation-collections/{collection_id}",
    response_model=CitationCollectionResponse,
    summary="Update a citation collection",
    responses={
        403: {"description": "Insufficient permissions"},
        404: {"description": "Collection not found"},
        422: {"description": "Invalid input"},
    },
)
async def update_citation_collection(
    collection_id: int,
    body: UpdateCitationCollectionRequest,
    ctx: TenantContext = Depends(require_document_admin),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> CitationCollectionResponse:
    """Update a citation collection's metadata.

    Args:
        collection_id: ID of the citation collection.
        body: Updated fields.
        ctx: Resolved tenant context (document_admin+ role).
        service: LiteratureSearchService dependency.

    Returns:
        Updated citation collection.
    """
    try:
        result = await service.update_citation_collection(
            collection_id=collection_id,
            company_id=ctx.company_id,
            name=body.name,
            description=body.description,
            purpose=body.purpose.value if body.purpose is not None else None,
        )
        return CitationCollectionResponse(**result)
    except ValueError as exc:
        raise _handle_service_error(exc)


# ─────────────────────────────────────────────────────────────────────────────
# 11. DELETE /citation-collections/{id} — Delete citation collection
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/citation-collections/{collection_id}",
    status_code=204,
    summary="Delete a citation collection",
    responses={
        403: {"description": "Insufficient permissions"},
        404: {"description": "Collection not found"},
    },
)
async def delete_citation_collection(
    collection_id: int,
    ctx: TenantContext = Depends(require_document_admin),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> None:
    """Soft-delete (archive) a citation collection.

    Args:
        collection_id: ID of the citation collection.
        ctx: Resolved tenant context (document_admin+ role).
        service: LiteratureSearchService dependency.
    """
    try:
        await service.delete_citation_collection(
            collection_id=collection_id,
            company_id=ctx.company_id,
        )
    except ValueError as exc:
        raise _handle_service_error(exc)


# ─────────────────────────────────────────────────────────────────────────────
# 12. POST /citation-collections/{id}/documents — Add documents to collection
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/citation-collections/{collection_id}/documents",
    status_code=201,
    summary="Add documents to a citation collection",
    responses={
        403: {"description": "Insufficient permissions"},
        404: {"description": "Collection not found"},
        422: {"description": "Non-internalized document or capacity exceeded"},
    },
)
async def add_documents_to_collection(
    collection_id: int,
    body: AddDocumentsRequest,
    ctx: TenantContext = Depends(require_document_admin),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> dict[str, Any]:
    """Add internalized documents to a citation collection.

    Args:
        collection_id: ID of the citation collection.
        body: Request with document IDs to add.
        ctx: Resolved tenant context (document_admin+ role).
        service: LiteratureSearchService dependency.

    Returns:
        Dict with added document membership IDs.
    """
    try:
        ids = await service.add_documents_to_collection(
            collection_id=collection_id,
            document_ids=body.document_ids,
            user_id=ctx.user_id,
            company_id=ctx.company_id,
        )
        return {"added_ids": ids}
    except (
        ValueError,
        NonInternalizedDocumentError,
        CollectionCapacityExceededError,
    ) as exc:
        raise _handle_service_error(exc)


# ─────────────────────────────────────────────────────────────────────────────
# 13. DELETE /citation-collections/{id}/documents/{doc_id} — Remove document
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/citation-collections/{collection_id}/documents/{document_id}",
    status_code=204,
    summary="Remove a document from a citation collection",
    responses={
        403: {"description": "Insufficient permissions"},
        404: {"description": "Collection or document membership not found"},
    },
)
async def remove_document_from_collection(
    collection_id: int,
    document_id: int,
    ctx: TenantContext = Depends(require_document_admin),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> None:
    """Remove a document from a citation collection.

    Args:
        collection_id: ID of the citation collection.
        document_id: ID of the document to remove.
        ctx: Resolved tenant context (document_admin+ role).
        service: LiteratureSearchService dependency.
    """
    try:
        await service.remove_document_from_collection(
            collection_id=collection_id,
            document_id=document_id,
            user_id=ctx.user_id,
            company_id=ctx.company_id,
        )
    except ValueError as exc:
        raise _handle_service_error(exc)


# ─────────────────────────────────────────────────────────────────────────────
# 14. POST /traceability-links — Create traceability links
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/traceability-links",
    response_model=list[TraceabilityLinkResponse],
    status_code=201,
    summary="Create traceability links for a document",
    responses={
        403: {"description": "Insufficient permissions"},
        404: {"description": "Document or target not found"},
        422: {"description": "Non-internalized document"},
    },
)
async def create_traceability_links(
    body: CreateTraceabilityLinksRequest,
    ctx: TenantContext = Depends(require_document_admin),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> list[dict[str, Any]]:
    """Create traceability links between an internalized document and targets.

    Args:
        body: Request with document ID and link specifications.
        ctx: Resolved tenant context (document_admin+ role).
        service: LiteratureSearchService dependency.

    Returns:
        List of created traceability link IDs.
    """
    try:
        link_ids = await service.create_traceability_links(
            document_id=body.document_id,
            links=[link.model_dump() for link in body.links],
            user_id=ctx.user_id,
            company_id=ctx.company_id,
        )
        # Return link IDs; the full response will be fetched via list endpoint
        # For now return minimal response with IDs
        return [{"id": lid} for lid in link_ids]
    except (
        ValueError,
        NonInternalizedDocumentError,
        InvalidTraceabilityTargetError,
    ) as exc:
        raise _handle_service_error(exc)


# ─────────────────────────────────────────────────────────────────────────────
# 15. GET /traceability-links — List traceability links
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/traceability-links",
    response_model=PaginatedTraceabilityLinksResponse,
    summary="List traceability links",
    responses={
        403: {"description": "Insufficient permissions"},
    },
)
async def list_traceability_links(
    document_id: int | None = Query(default=None),
    target_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: TenantContext = Depends(require_member),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> PaginatedTraceabilityLinksResponse:
    """List traceability links with optional filters.

    Args:
        document_id: Optional filter by source document ID.
        target_id: Optional filter by target entity ID.
        page: Page number (1-indexed).
        page_size: Results per page.
        ctx: Resolved tenant context (member+ role).
        service: LiteratureSearchService dependency.

    Returns:
        Paginated list of traceability links.
    """
    result = await service.list_traceability_links(
        company_id=ctx.company_id,
        document_id=document_id,
        target_id=target_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedTraceabilityLinksResponse(**result)


# ─────────────────────────────────────────────────────────────────────────────
# 16. DELETE /traceability-links/{id} — Delete a traceability link
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/traceability-links/{link_id}",
    status_code=204,
    summary="Delete a traceability link",
    responses={
        403: {"description": "Insufficient permissions"},
        404: {"description": "Link not found"},
    },
)
async def delete_traceability_link(
    link_id: int,
    ctx: TenantContext = Depends(require_document_admin),
    service: LiteratureSearchService = Depends(get_literature_search_service),
) -> None:
    """Delete a traceability link.

    Args:
        link_id: ID of the traceability link to delete.
        ctx: Resolved tenant context (document_admin+ role).
        service: LiteratureSearchService dependency.
    """
    try:
        await service.delete_traceability_link(
            link_id=link_id,
            user_id=ctx.user_id,
            company_id=ctx.company_id,
        )
    except ValueError as exc:
        raise _handle_service_error(exc)


# ─────────────────────────────────────────────────────────────────────────────
# 17. POST /export — Export search results as CSV or PDF
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/export",
    summary="Export search results as CSV or PDF file",
    responses={
        403: {"description": "Insufficient permissions"},
        404: {"description": "Referenced search not found"},
    },
)
async def export_search_results(
    body: ExportRequest,
    ctx: TenantContext = Depends(require_member),
    export_service: ExportService = Depends(get_export_service),
) -> StreamingResponse:
    """Generate and return an export file of search results.

    Args:
        body: Export request with format and search reference.
        ctx: Resolved tenant context (member+ role).
        export_service: ExportService dependency.

    Returns:
        StreamingResponse with CSV or PDF content.
    """
    try:
        if body.format == "csv":
            return await export_service.generate_csv_export(
                search_execution_id=body.search_execution_id,
                saved_search_id=body.saved_search_id,
                company_id=ctx.company_id,
                user_id=ctx.user_id,
            )
        else:
            return await export_service.generate_pdf_export(
                search_execution_id=body.search_execution_id,
                saved_search_id=body.saved_search_id,
                company_id=ctx.company_id,
                user_id=ctx.user_id,
                include_prisma_flow=body.include_prisma_flow,
            )
    except (ExportReferenceNotFoundError, ValueError) as exc:
        raise _handle_service_error(exc)
