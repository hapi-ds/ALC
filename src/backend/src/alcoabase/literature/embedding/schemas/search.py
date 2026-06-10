"""Pydantic v2 schemas for hybrid and unified literature search endpoints.

Provides request/response schemas for:
- POST /api/literature/search/hybrid
- POST /api/literature/search/unified

Includes validation for query length, pagination bounds, scoring parameters,
partition filtering, and date range constraints.

References:
    - Requirements: 6.1, 6.3, 6.4, 6.5, 6.6, 10.1, 10.2
    - Design doc: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ─── Enums ────────────────────────────────────────────────────────────────────


class PartitionFilter(StrEnum):
    """Allowed partition filter values for search queries.

    Controls whether results include public literature, private knowledge,
    or both.
    """

    PUBLIC_LITERATURE = "public_literature"
    PRIVATE_KNOWLEDGE = "private_knowledge"
    ALL = "all"


# ─── Date Range ───────────────────────────────────────────────────────────────


class DateRange(BaseModel):
    """ISO-8601 date range filter for search queries.

    Attributes:
        start: Start date (inclusive).
        end: End date (inclusive).
    """

    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def _validate_date_range(self) -> DateRange:
        """Validate that end is not before start."""
        if (
            self.start is not None
            and self.end is not None
            and self.end < self.start
        ):
            msg = "date_range.end must not be before date_range.start"
            raise ValueError(msg)
        return self


# ─── Search Request ───────────────────────────────────────────────────────────


class HybridSearchRequestSchema(BaseModel):
    """Request schema for hybrid and unified literature search.

    Accepts query text, optional filters, pagination parameters, and
    scoring configuration for RRF fusion between BM25 and kNN results.

    Attributes:
        query: Search query text (1–1000 characters, required).
        partition_filter: Filter by content origin (default: all).
        semantic_weight: Weight for semantic vs keyword scoring (0.0–1.0).
        rrf_k: Reciprocal rank fusion k parameter (1–200, default 60).
        page: Page number (1-indexed, minimum 1, default 1).
        page_size: Results per page (1–100, default 20).
        literature_boost: Boost factor for literature results (0.1–10.0).
        internal_boost: Boost factor for internal document results (0.1–10.0).
        date_range: Optional publication date range filter.
        source_id: Optional filter by source adapter name.
        authors: Optional filter by author names.
        publication_type: Optional filter by publication type.
        include_internal: Include internal documents in unified search.
    """

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Search query text (1–1000 characters).",
    )
    partition_filter: PartitionFilter = Field(
        default=PartitionFilter.ALL,
        description="Filter results by content origin partition.",
    )
    semantic_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Weight for semantic scoring (0.0=pure BM25, 1.0=pure kNN).",
    )
    rrf_k: int = Field(
        default=60,
        ge=1,
        le=200,
        description="RRF k parameter for rank fusion.",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Page number (1-indexed).",
    )
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Results per page (1–100).",
    )
    literature_boost: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Boost factor for literature partition results.",
    )
    internal_boost: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Boost factor for internal document results.",
    )
    date_range: DateRange | None = Field(
        default=None,
        description="Optional publication date range filter (ISO-8601).",
    )
    source_id: str | None = Field(
        default=None,
        description="Optional filter by source adapter name.",
    )
    authors: list[str] | None = Field(
        default=None,
        description="Optional filter by author names.",
    )
    publication_type: str | None = Field(
        default=None,
        description="Optional filter by publication type.",
    )
    include_internal: bool = Field(
        default=True,
        description="Include internal documents in unified search (unified endpoint only).",
    )


# ─── Search Result ────────────────────────────────────────────────────────────


class HybridSearchResultSchema(BaseModel):
    """A single result from hybrid or unified search.

    Contains the matched chunk text, document metadata, and the
    RRF-fused relevance score.

    Attributes:
        chunk_text: Matched text chunk content.
        title: Document title.
        authors: List of author names.
        doi: Digital Object Identifier (may be null).
        publication_date: Publication date (may be null).
        source_id: Source adapter name (may be null).
        relevance_score: RRF-fused relevance score (0.0–1.0).
        partition_tag: Content origin ('public_literature' or 'private_knowledge').
        section_heading: Section heading the chunk belongs to.
        ingestion_record_id: Associated ingestion record identifier.
    """

    model_config = ConfigDict(frozen=True)

    chunk_text: str
    title: str
    authors: list[str] = Field(default_factory=list)
    doi: str | None = None
    publication_date: date | None = None
    source_id: str | None = None
    relevance_score: float = Field(ge=0.0, le=1.0)
    partition_tag: str
    section_heading: str = ""
    ingestion_record_id: int


# ─── Search Response ──────────────────────────────────────────────────────────


class HybridSearchResponseSchema(BaseModel):
    """Complete response for hybrid and unified search endpoints.

    Includes paginated results, total count, and metadata flags indicating
    degraded mode or partial results.

    Attributes:
        results: List of search result items for the current page.
        total_count: Estimated total matching results across all pages.
        page: Current page number.
        page_size: Number of results per page.
        degraded_mode: True if vLLM was unavailable (BM25-only fallback).
        partial_results: True if one index was unreachable (unified search).
        unavailable_index: Name of the unreachable index (if partial_results).
        query_time_ms: Search execution time in milliseconds.
    """

    results: list[HybridSearchResultSchema]
    total_count: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    degraded_mode: bool = False
    partial_results: bool = False
    unavailable_index: str | None = None
    query_time_ms: float | None = None
