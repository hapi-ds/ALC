"""Search API router for hybrid document search.

Provides the POST /api/search endpoint for performing hybrid
(BM25 lexical + kNN semantic) search across indexed documents.

References:
    - Task 12.10: Create FastAPI router /api/search
    - Requirement 14: Semantic and Hybrid Search
"""

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


class SearchRequest(BaseModel):
    """Request body for hybrid search.

    Attributes:
        query: Natural language search query.
        user_id: ID of the user performing the search (for ABAC filtering).
        limit: Maximum number of results to return (1-100, default 20).
    """

    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    user_id: int = Field(..., description="User ID for ABAC filtering")
    limit: int = Field(default=20, ge=1, le=100, description="Max results")


class SearchResultResponse(BaseModel):
    """A single search result in the response.

    Attributes:
        document_uuid: The Document-UUID of the matched document.
        title: Document title.
        version: Document version string.
        excerpt: Matching text excerpt.
        relevance_score: Combined relevance score (0.0 to 1.0).
    """

    document_uuid: str
    title: str
    version: str
    excerpt: str
    relevance_score: float


class SearchResponse(BaseModel):
    """Response body for hybrid search.

    Attributes:
        results: List of ranked search results.
        total: Total number of results returned.
        query: The original search query.
    """

    results: list[SearchResultResponse]
    total: int
    query: str


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

    results: list[SearchResult] = service.hybrid_search(
        query=request.query,
        user_id=request.user_id,
        limit=request.limit,
    )

    response_results = [
        SearchResultResponse(
            document_uuid=r.document_uuid,
            title=r.title,
            version=r.version,
            excerpt=r.excerpt,
            relevance_score=r.relevance_score,
        )
        for r in results
    ]

    return SearchResponse(
        results=response_results,
        total=len(response_results),
        query=request.query,
    )
