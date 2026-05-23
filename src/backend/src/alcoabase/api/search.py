"""Search API router for hybrid document search.

Provides the POST /api/search endpoint for performing hybrid
(BM25 lexical + kNN semantic) search across indexed documents.

References:
    - Task 12.10: Create FastAPI router /api/search
    - Requirement 14: Semantic and Hybrid Search
"""

from typing import Literal

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from alcoabase.services.knowledge_service import KnowledgeService, SearchResult

router = APIRouter(prefix="/search", tags=["Search"])

# Module-level service instance
_knowledge_service: KnowledgeService | None = None


def _get_knowledge_service() -> KnowledgeService:
    """Get or create the KnowledgeService singleton.

    Returns:
        KnowledgeService: The service instance.
    """
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service


# ---------------------------------------------------------------------------
# Request/Response Schemas
# ---------------------------------------------------------------------------


class SearchFilters(BaseModel):
    """Optional filters for narrowing search results.

    Attributes:
        document_type: Filter by document type (OR within category).
        status: Filter by document status (OR within category).
        tags: Filter by tags (OR within category).
    """

    document_type: list[str] = Field(default_factory=list)
    status: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    """Request body for hybrid search.

    Attributes:
        query: Natural language search query.
        user_id: ID of the user performing the search (for ABAC filtering).
        limit: Maximum number of results to return (1-100, default 20).
        filters: Optional faceted filter criteria.
        offset: Number of results to skip for pagination.
        sort_by: Sort order — "relevance" or "date".
    """

    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    user_id: int = Field(..., description="User ID for ABAC filtering")
    limit: int = Field(default=20, ge=1, le=100, description="Max results")
    filters: SearchFilters | None = Field(default=None)
    offset: int = Field(default=0, ge=0)
    sort_by: Literal["relevance", "date"] = Field(default="relevance")


class SearchResultResponse(BaseModel):
    """A single search result in the response.

    Attributes:
        document_uuid: The Document-UUID of the matched document.
        title: Document title.
        version: Document version string.
        excerpt: Matching text excerpt.
        relevance_score: Combined relevance score (0.0 to 1.0).
        document_type: Document type category.
        status: Document lifecycle status.
        tags: Document tags.
        created_at: Creation timestamp (ISO 8601).
        updated_at: Last update timestamp (ISO 8601).
    """

    document_uuid: str
    title: str
    version: str
    excerpt: str
    relevance_score: float
    document_type: str | None = None
    status: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class SearchResponse(BaseModel):
    """Response body for hybrid search.

    Attributes:
        results: List of ranked search results.
        total: Total number of results returned in this page.
        total_available: Total matching results before pagination.
        query: The original search query.
        offset: The offset used for pagination.
        filters_applied: Active filters echoed back (empty dict if none).
    """

    results: list[SearchResultResponse]
    total: int
    total_available: int
    query: str
    offset: int
    filters_applied: dict[str, list[str]] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=SearchResponse)
async def hybrid_search(request: SearchRequest) -> SearchResponse:
    """Perform hybrid search combining BM25 lexical + kNN semantic search.

    Combines keyword matching and vector similarity to find relevant
    documents. Results are filtered by ABAC permissions and exclude
    CSV validation records.

    Args:
        request: Search request with query, user_id, and limit.

    Returns:
        SearchResponse with ranked results.
    """
    service = _get_knowledge_service()

    # Build filters dict from request (filtering out empty lists)
    filters_dict: dict[str, list[str]] | None = None
    if request.filters:
        filters_dict = {
            k: v for k, v in request.filters.model_dump().items() if v
        }
        if not filters_dict:
            filters_dict = None

    results, total_available = service.hybrid_search(
        query=request.query,
        user_id=request.user_id,
        limit=request.limit,
        filters=filters_dict,
        offset=request.offset,
        sort_by=request.sort_by,
    )

    # Build filters_applied from request filters (non-empty lists only)
    filters_applied: dict[str, list[str]] = {}
    if request.filters:
        filters_applied = {
            k: v for k, v in request.filters.model_dump().items() if v
        }

    response_results = [
        SearchResultResponse(
            document_uuid=r.document_uuid,
            title=r.title,
            version=r.version,
            excerpt=r.excerpt,
            relevance_score=r.relevance_score,
            document_type=r.document_type,
            status=r.status,
            tags=r.tags,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in results
    ]

    return SearchResponse(
        results=response_results,
        total=len(response_results),
        total_available=total_available,
        query=request.query,
        offset=request.offset,
        filters_applied=filters_applied,
    )
