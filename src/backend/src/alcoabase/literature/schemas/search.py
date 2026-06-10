"""Pydantic v2 schemas for Literature Search API request/response.

Contains schemas for search queries, normalized results, adapter capabilities,
partial result information, search responses, and async task status.

References:
    - Requirements 8.5, 12.1, 12.4, 12.5, 14.5, 15.2
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ─── Enums ────────────────────────────────────────────────────────────────────


class PublicationType(StrEnum):
    """Normalized publication type classification.

    Maps source-specific types to a standardized set for consistent
    downstream processing.
    """

    JOURNAL_ARTICLE = "journal_article"
    PREPRINT = "preprint"
    CONFERENCE_PAPER = "conference_paper"
    REVIEW = "review"
    OTHER = "other"


class DatePrecision(StrEnum):
    """Precision of the publication date as provided by the source.

    Used to indicate whether the original date from the source had
    day, month, or year-only granularity. Partial dates are normalized
    to the first day of the missing component.
    """

    DAY = "day"
    MONTH = "month"
    YEAR = "year"


class TaskStatus(StrEnum):
    """Status of an asynchronous literature search task."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ─── Search Query ─────────────────────────────────────────────────────────────


class SearchQuery(BaseModel):
    """Structured literature search request.

    Attributes:
        terms: Free-text search terms.
        sources: Optional list of specific source adapter names to query.
        date_from: Optional start date for publication date range filter.
        date_to: Optional end date for publication date range filter.
        page_size: Results per page (1–100, default 20).
        page: Page number (1-indexed, default 1).
        publication_types: Optional filter by publication type(s).
        profile_name: Optional named search profile to apply.
    """

    terms: str = Field(..., min_length=1, max_length=2000)
    sources: list[str] | None = None
    date_from: date | None = None
    date_to: date | None = None
    page_size: int = Field(default=20, ge=1, le=100)
    page: int = Field(default=1, ge=1)
    publication_types: list[PublicationType] | None = None
    profile_name: str | None = None

    @model_validator(mode="after")
    def _validate_date_range(self) -> SearchQuery:
        """Validate that date_to is not before date_from."""
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_to < self.date_from
        ):
            msg = "date_to must not be before date_from"
            raise ValueError(msg)
        return self


# ─── Search Results ───────────────────────────────────────────────────────────


class LiteratureSearchResult(BaseModel):
    """Normalized search result from any literature source.

    This is the canonical result format returned to consumers.
    All source-specific data is mapped into these fields by adapters.
    The model is frozen to ensure immutability after construction.

    Attributes:
        title: Publication title (max 2000 chars).
        authors: List of author names preserving source ordering (max 500).
        abstract: Publication abstract (may be empty, max 50000 chars).
        doi: Digital Object Identifier (may be null).
        publication_date: Normalized to ISO 8601 date.
        source_id: Adapter name that produced this result.
        external_id: Source-specific identifier (PMID, arXiv ID, etc.).
        journal_or_venue: Journal or conference name (may be empty).
        publication_type: Normalized publication type.
        url: Direct link to source record (may be null).
        date_precision: Original date granularity from source.
        retrieval_timestamp: When this result was fetched (UTC datetime).
        query_id: ID of the originating search query.
    """

    model_config = ConfigDict(frozen=True)

    title: str = Field(..., max_length=2000)
    authors: list[str] = Field(default_factory=list, max_length=500)
    abstract: str = Field(default="", max_length=50000)
    doi: str | None = None
    publication_date: date
    source_id: str
    external_id: str
    journal_or_venue: str = ""
    publication_type: PublicationType = PublicationType.OTHER
    url: str | None = None
    date_precision: DatePrecision = DatePrecision.DAY
    retrieval_timestamp: datetime
    query_id: str


# ─── Partial Results and Search Response ──────────────────────────────────────


class PartialResultInfo(BaseModel):
    """Information about sources that failed during a search.

    Attributes:
        timed_out_sources: Sources that exceeded the 15-second timeout.
        errored_sources: Sources that returned errors (5xx, parse, etc.).
        unavailable_sources: Sources excluded due to circuit breaker or
            rate limiting.
    """

    timed_out_sources: list[str] = Field(default_factory=list)
    errored_sources: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    """Complete search response with results and metadata.

    Attributes:
        results: List of normalized literature search results.
        total_count: Total estimated result count across all sources.
        partial_results: Information about sources that failed, or None
            if all sources responded successfully.
        query_id: Unique identifier for this search query.
    """

    results: list[LiteratureSearchResult]
    total_count: int
    partial_results: PartialResultInfo | None = None
    query_id: str


# ─── Adapter Capabilities and Registry ────────────────────────────────────────


class AdapterCapabilities(BaseModel):
    """Declares what query fields and filters an adapter supports.

    Attributes:
        supports_keyword: Whether keyword/free-text search is supported.
        supports_author: Whether author name filtering is supported.
        supports_date_range: Whether date range filtering is supported.
        supports_publication_type: Whether publication type filtering is
            supported.
        supports_doi: Whether DOI lookup is supported.
    """

    supports_keyword: bool = True
    supports_author: bool = False
    supports_date_range: bool = False
    supports_publication_type: bool = False
    supports_doi: bool = False


class AdapterRegistryEntry(BaseModel):
    """Public representation of a registered adapter in the source registry.

    Attributes:
        name: Unique adapter identifier.
        version: Semantic version string.
        display_name: Human-readable name.
        requires_api_key: Whether this source requires an API key.
        capabilities: Supported query features.
        status: Current health status (available, degraded, unreachable).
        last_health_check: Timestamp of the most recent health check.
    """

    name: str
    version: str
    display_name: str
    requires_api_key: bool
    capabilities: AdapterCapabilities
    status: str
    last_health_check: datetime | None = None


# ─── Async Task Schemas ───────────────────────────────────────────────────────


class AsyncTaskResponse(BaseModel):
    """Response for async task creation (HTTP 202).

    Returned when a search is dispatched as a Celery task because it
    targets more than 3 sources or requests more than 50 results.

    Attributes:
        task_id: Unique Celery task identifier.
        status: Initial task status (typically QUEUED).
        status_url: URL to poll for task progress.
    """

    task_id: str
    status: TaskStatus
    status_url: str


class AsyncTaskStatus(BaseModel):
    """Response for task status polling.

    Attributes:
        task_id: Unique Celery task identifier.
        status: Current task status.
        progress_percent: Estimated completion percentage (0–100).
        partial_results: Intermediate results if available.
        error_message: Error details if task failed.
    """

    task_id: str
    status: TaskStatus
    progress_percent: int = Field(default=0, ge=0, le=100)
    partial_results: SearchResponse | None = None
    error_message: str | None = None
