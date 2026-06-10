"""Pydantic v2 schemas for the ingestion API endpoints.

Defines request/response schemas for batch ingestion submission,
record retrieval, batch status, state counts, storage usage, and
pipeline health monitoring.

References:
    - Requirements 1.7, 1.8, 2.7, 11.1, 11.2, 11.3, 11.4, 11.9
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


# ─── Enums ────────────────────────────────────────────────────────────────────


class IngestionStateSchema(StrEnum):
    """API-facing ingestion state enum mirroring the 7 lifecycle states.

    Each value corresponds to a state in the ingestion pipeline state machine.
    """

    METADATA_ONLY = "metadata_only"
    ABSTRACT_INDEXED = "abstract_indexed"
    FULL_TEXT_PENDING = "full_text_pending"
    FULL_TEXT_DOWNLOADED = "full_text_downloaded"
    SANITIZED = "sanitized"
    INDEXED = "indexed"
    FAILED = "failed"


# ─── Ingestion Request Schemas ────────────────────────────────────────────────


class LiteratureSearchResultInput(BaseModel):
    """Input schema for a single literature search result to ingest.

    Maps fields from the Phase 9.1 LiteratureSearchResult schema into
    a validated input for the ingestion pipeline.

    Attributes:
        title: Publication title (1–2000 characters).
        authors: List of author names preserving source ordering.
        doi: Digital Object Identifier (may be null).
        publication_date: Normalized publication date (may be null).
        journal_or_venue: Journal or conference name.
        publication_type: Normalized publication type string.
        external_id: Source-specific identifier (e.g., PMID, arXiv ID).
        source_id: Source adapter name that produced this result.
        url: Direct link to the source record.
        abstract: Publication abstract text (may be null).
    """

    title: str = Field(..., min_length=1, max_length=2000)
    authors: list[str] = Field(default_factory=list)
    doi: str | None = None
    publication_date: datetime | None = None
    journal_or_venue: str = ""
    publication_type: str = "other"
    external_id: str = Field(..., min_length=1)
    source_id: str = Field(..., min_length=1)
    url: str = ""
    abstract: str | None = None


class IngestionSubmitRequest(BaseModel):
    """Request body for batch ingestion submission.

    Accepts a list of up to 100 LiteratureSearchResult-compatible objects.
    The pipeline creates an IngestionRecord for each valid, non-duplicate result.

    Attributes:
        results: List of literature search results to ingest (1–100 items).
    """

    results: list[LiteratureSearchResultInput] = Field(
        ..., min_length=1, max_length=100
    )

    @field_validator("results")
    @classmethod
    def validate_results_count(
        cls, v: list[LiteratureSearchResultInput],
    ) -> list[LiteratureSearchResultInput]:
        """Validate that results list does not exceed 100 items.

        Args:
            v: The results list to validate.

        Returns:
            The validated results list.

        Raises:
            ValueError: If more than 100 results are submitted.
        """
        if len(v) > 100:
            msg = "Maximum 100 results per submission"
            raise ValueError(msg)
        return v


# ─── Ingestion Response Schemas ───────────────────────────────────────────────


class BatchIngestionResponse(BaseModel):
    """Response for batch ingestion submission (HTTP 202).

    Returned immediately after a batch is accepted for asynchronous processing.

    Attributes:
        batch_id: UUID identifying this batch submission.
        submitted_count: Total number of results submitted.
        duplicate_count: Number of results skipped as duplicates.
        created_ids: List of newly created IngestionRecord IDs.
    """

    batch_id: str
    submitted_count: int
    duplicate_count: int
    created_ids: list[int]


class IngestionRecordResponse(BaseModel):
    """Full ingestion record response with state history.

    Contains all metadata, file information, retention status, and
    the complete state transition history for a single ingestion record.

    Attributes:
        id: Primary key of the ingestion record.
        company_id: Company (tenant) owning this record.
        batch_id: UUID of the batch this record was submitted in.
        state: Current lifecycle state.
        failed_from_state: State from which failure occurred (if failed).
        error_type: Classification of the failure (if failed).
        error_message: Human-readable error detail (if failed).
        retry_count: Number of retry attempts made.
        title: Publication title.
        authors: List of author names.
        doi: Digital Object Identifier (may be null).
        publication_date: Publication date (may be null).
        journal_or_venue: Journal or conference name.
        publication_type: Normalized publication type.
        external_id: Source-specific identifier.
        source_id: Source adapter name.
        url: Direct link to source record.
        abstract: Publication abstract (may be null).
        storage_path: MinIO object path for the original file.
        file_size_bytes: Size of the downloaded file in bytes.
        content_type: MIME type of the downloaded file.
        sha256_checksum: SHA-256 hash of the downloaded file.
        download_timestamp: When the file was downloaded.
        word_count: Word count from sanitized content.
        retention_expiry_date: When the original file will be purged.
        original_file_purged: Whether the original file has been deleted.
        state_history: List of state transition records.
        created_at: Record creation timestamp.
        updated_at: Last modification timestamp.
    """

    id: int
    company_id: int
    batch_id: str
    state: IngestionStateSchema
    failed_from_state: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    retry_count: int = 0

    # Metadata
    title: str
    authors: list[str] = Field(default_factory=list)
    doi: str | None = None
    publication_date: datetime | None = None
    journal_or_venue: str = ""
    publication_type: str = "other"
    external_id: str
    source_id: str
    url: str = ""
    abstract: str | None = None

    # File info
    storage_path: str | None = None
    file_size_bytes: int | None = None
    content_type: str | None = None
    sha256_checksum: str | None = None
    download_timestamp: datetime | None = None
    word_count: int | None = None

    # Retention
    retention_expiry_date: datetime | None = None
    original_file_purged: bool = False

    # History
    state_history: list[dict] = Field(default_factory=list)

    # Timestamps
    created_at: datetime
    updated_at: datetime


class IngestionRecordListResponse(BaseModel):
    """Paginated list of ingestion records.

    Attributes:
        items: List of ingestion records for the current page.
        page: Current page number (1-indexed).
        page_size: Number of records per page.
        total_count: Total number of matching records across all pages.
    """

    items: list[IngestionRecordResponse]
    page: int
    page_size: int
    total_count: int


class BatchStatusResponse(BaseModel):
    """Status of all records submitted in a single batch.

    Attributes:
        batch_id: UUID identifying the batch.
        records: List of all ingestion records in the batch.
        state_counts: Count of records in each state for this batch.
    """

    batch_id: str
    records: list[IngestionRecordResponse]
    state_counts: dict[str, int]


# ─── Monitoring Schemas ───────────────────────────────────────────────────────


class StateCounts(BaseModel):
    """Aggregated state counts for monitoring dashboards.

    Maps each ingestion state to the number of records currently
    in that state for a given company.

    Attributes:
        metadata_only: Records awaiting abstract indexing.
        abstract_indexed: Records with abstract stored.
        full_text_pending: Records awaiting full-text download.
        full_text_downloaded: Records with downloaded full-text.
        sanitized: Records with sanitized content.
        indexed: Records fully processed and indexed.
        failed: Records in a failed state.
    """

    metadata_only: int = 0
    abstract_indexed: int = 0
    full_text_pending: int = 0
    full_text_downloaded: int = 0
    sanitized: int = 0
    indexed: int = 0
    failed: int = 0


class StorageUsageResponse(BaseModel):
    """Company storage usage and quota information.

    Attributes:
        usage_bytes: Current storage usage in bytes.
        quota_bytes: Total storage quota in bytes.
        usage_percent: Usage as a percentage of quota (0.0–100.0).
        quota_warning: True if usage exceeds 90% of quota.
        file_counts_per_state: Number of files stored per ingestion state.
    """

    usage_bytes: int
    quota_bytes: int
    usage_percent: float
    quota_warning: bool
    file_counts_per_state: dict[str, int]


class IngestionHealthResponse(BaseModel):
    """Pipeline health status for system administrators.

    Attributes:
        overall_status: Summary health status (healthy, degraded, unhealthy).
        unpaywall_status: Connectivity status to Unpaywall API.
        minio_status: Connectivity status to MinIO object store.
        queue_depth: Number of pending tasks in the ingestion queue.
        avg_processing_time_ms: Average task processing time in milliseconds.
    """

    overall_status: str
    unpaywall_status: str
    minio_status: str
    queue_depth: int
    avg_processing_time_ms: float
