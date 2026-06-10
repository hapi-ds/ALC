"""Pydantic v2 schemas for re-indexing and index status endpoints.

Provides request/response schemas for:
- POST /api/literature/index/reindex (initiate re-indexing)
- GET /api/literature/index/reindex/{task_id} (progress tracking)
- GET /api/literature/index/status (index health and statistics)

References:
    - Requirements: 8.3, 8.5, 10.3, 10.4, 10.5
    - Design doc: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


# ─── Enums ────────────────────────────────────────────────────────────────────


class ReindexJobStatus(StrEnum):
    """Status values for a re-indexing job."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IndexHealth(StrEnum):
    """OpenSearch index health status values."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


# ─── Reindex Request ──────────────────────────────────────────────────────────


class ReindexRequestSchema(BaseModel):
    """Request schema for initiating a batch re-indexing operation.

    Allows filtering by ingestion record state or specifying explicit
    record IDs to re-index.

    Attributes:
        state_filter: Optional list of states to include (e.g., ['indexed', 'abstract_indexed']).
        record_ids: Optional list of specific ingestion record IDs to re-index.
    """

    state_filter: list[str] | None = Field(
        default=None,
        description=(
            "Filter records by state. Allowed values: 'indexed', 'abstract_indexed'. "
            "If omitted, all eligible records are re-indexed."
        ),
    )
    record_ids: list[int] | None = Field(
        default=None,
        description="Specific ingestion record IDs to re-index. Overrides state_filter if provided.",
    )


# ─── Reindex Progress ─────────────────────────────────────────────────────────


class ReindexProgressSchema(BaseModel):
    """Response schema for re-indexing progress tracking.

    Returned by GET /api/literature/index/reindex/{task_id}.

    Attributes:
        task_id: Unique identifier for the re-indexing job.
        status: Current job status.
        progress_percent: Completion percentage (0–100).
        total_records: Total records to process.
        records_processed: Records successfully processed so far.
        records_failed: Records that failed processing.
        current_batch: Current batch number being processed.
        total_batches: Total number of batches.
        started_at: When the job was initiated.
        updated_at: When the progress was last updated.
        estimated_remaining_seconds: Estimated seconds until completion (null if unknown).
    """

    task_id: str
    status: ReindexJobStatus
    progress_percent: int = Field(ge=0, le=100)
    total_records: int = Field(ge=0)
    records_processed: int = Field(ge=0)
    records_failed: int = Field(ge=0)
    current_batch: int = Field(ge=0)
    total_batches: int = Field(ge=0)
    started_at: datetime | None = None
    updated_at: datetime | None = None
    estimated_remaining_seconds: float | None = None


# ─── Index Status ─────────────────────────────────────────────────────────────


class IndexStatusSchema(BaseModel):
    """Response schema for index health and statistics.

    Returned by GET /api/literature/index/status.

    Attributes:
        health: OpenSearch cluster health for the company's index.
        doc_count: Total number of documents (chunks) in the index.
        chunks_indexed: Total chunks indexed (same as doc_count).
        size_bytes: Index size in bytes.
        last_indexing_timestamp: When the most recent document was indexed (ISO-8601).
    """

    health: IndexHealth
    doc_count: int = Field(ge=0)
    chunks_indexed: int = Field(ge=0)
    size_bytes: int = Field(ge=0)
    last_indexing_timestamp: datetime | None = None
