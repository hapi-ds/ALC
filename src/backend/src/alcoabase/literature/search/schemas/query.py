"""Pydantic v2 schemas for literature search query endpoints.

Defines request/response schemas for hybrid literature search with faceted
filtering, paginated results, and facet count aggregations.

References:
    - Requirements: 1.1, 1.5, 1.6
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ─── Enums ────────────────────────────────────────────────────────────────────


class SearchMode(StrEnum):
    """Search execution mode determining which retrieval strategies to use."""

    HYBRID = "hybrid"
    KEYWORD = "keyword"
    SEMANTIC = "semantic"


class Provenance(StrEnum):
    """Origin indicator for search results."""

    EXTERNAL = "external"
    INTERNAL = "internal"


# ─── Filter Schema ───────────────────────────────────────────────────────────


class SearchFilters(BaseModel):
    """Faceted filter constraints for narrowing literature search results.

    All fields are optional; when provided, they act as post-filter
    constraints on the OpenSearch query without affecting relevance scoring.

    Attributes:
        date_from: Earliest publication date (inclusive, ISO format).
        date_to: Latest publication date (inclusive, ISO format).
        journals: Filter to specific journal names (max 20).
        sources: Filter to specific source adapter names (max 10).
        publication_types: Filter to specific publication types (max 10).
        mesh_terms: Filter to specific MeSH terms (max 30).
        device_class: Filter to specific device class values (max 5).
    """

    date_from: date | None = None
    date_to: date | None = None
    journals: list[str] = Field(default_factory=list, max_length=20)
    sources: list[str] = Field(default_factory=list, max_length=10)
    publication_types: list[str] = Field(default_factory=list, max_length=10)
    mesh_terms: list[str] = Field(default_factory=list, max_length=30)
    device_class: list[str] = Field(default_factory=list, max_length=5)


# ─── Request Schema ──────────────────────────────────────────────────────────


class LiteratureSearchQueryRequest(BaseModel):
    """Request body for POST /api/literature-search/query.

    Executes a hybrid literature search with optional faceted filtering,
    pagination, and internal document inclusion.

    Attributes:
        query_text: Search query string (1–1000 characters, non-whitespace).
        filters: Faceted filter constraints (all optional).
        search_mode: Retrieval strategy (hybrid, keyword, or semantic).
        include_internal: Whether to include internal company documents.
        page: Page number for pagination (1-indexed).
        page_size: Number of results per page (1–100).
    """

    query_text: str = Field(..., min_length=1, max_length=1000)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    search_mode: SearchMode = Field(default=SearchMode.HYBRID)
    include_internal: bool = Field(default=False)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @field_validator("query_text")
    @classmethod
    def query_text_not_whitespace(cls, v: str) -> str:
        """Validate that query_text is not empty or whitespace-only.

        Args:
            v: The query text value to validate.

        Returns:
            The stripped query text.

        Raises:
            ValueError: If query_text contains only whitespace characters.
        """
        if not v.strip():
            msg = "Search query must not be empty or whitespace-only"
            raise ValueError(msg)
        return v.strip()


# ─── Response Schemas ─────────────────────────────────────────────────────────


class LiteratureSearchResult(BaseModel):
    """A single literature search result with metadata and scoring.

    Represents one item from a hybrid search result set, including provenance
    information and internalization status.

    Attributes:
        id: Record identifier (ingestion_record_id or document_id).
        title: Publication title.
        authors: List of author names.
        abstract: Abstract text (truncated to 500 characters).
        publication_date: Publication date (may be null).
        journal: Journal or venue name.
        source: Source adapter name or "internal".
        publication_type: Normalized publication type.
        mesh_terms: List of MeSH terms.
        doi: Digital Object Identifier (may be null).
        relevance_score: Combined relevance score (0.0–1.0).
        provenance: Origin indicator ("external" or "internal").
        full_text_available: Whether full-text content is available.
        is_internalized: Whether this item has been internalized as a Document.
    """

    id: int
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = Field(default=None, max_length=500)
    publication_date: datetime | None = None
    journal: str = ""
    source: str
    publication_type: str = "other"
    mesh_terms: list[str] = Field(default_factory=list)
    doi: str | None = None
    relevance_score: float = Field(ge=0.0, le=1.0)
    provenance: Provenance
    full_text_available: bool = False
    is_internalized: bool = False

    model_config = ConfigDict(from_attributes=True)


class PaginationMeta(BaseModel):
    """Pagination metadata for paginated responses.

    Attributes:
        total_results: Total number of matching results across all pages.
        page: Current page number (1-indexed).
        page_size: Number of results per page.
        total_pages: Total number of available pages.
    """

    total_results: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_pages: int = Field(ge=0)


class FacetValue(BaseModel):
    """A single facet value with its associated result count.

    Attributes:
        value: The facet value (e.g., journal name, source adapter name).
        count: Number of results matching this facet value.
    """

    value: str
    count: int = Field(ge=0)


class FacetCounts(BaseModel):
    """Aggregated facet counts for filter dimensions.

    Provides result counts per facet value to populate the filter panel UI.

    Attributes:
        journals: Journal facet values with result counts.
        sources: Source adapter facet values with result counts.
        publication_types: Publication type facet values with result counts.
    """

    journals: list[FacetValue] = Field(default_factory=list)
    sources: list[FacetValue] = Field(default_factory=list)
    publication_types: list[FacetValue] = Field(default_factory=list)


class PaginatedSearchResponse(BaseModel):
    """Paginated literature search response with results, pagination, and facets.

    Returned from POST /api/literature-search/query with the full result set
    for the requested page, pagination metadata, facet counts, and a reference
    to the search execution log entry.

    Attributes:
        results: List of search results for the current page.
        pagination: Pagination metadata.
        facets: Facet counts for filter dimensions (null if not computed).
        search_execution_id: ID of the SearchExecutionLog record for this query.
    """

    results: list[LiteratureSearchResult]
    pagination: PaginationMeta
    facets: FacetCounts | None = None
    search_execution_id: int
