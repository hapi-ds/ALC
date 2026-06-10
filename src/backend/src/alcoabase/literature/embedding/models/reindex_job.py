"""Re-indexing job progress tracking model.

Tracks batch re-indexing job state and progress for each company.
Used by the EmbeddingService to persist re-indexing progress in the
database (not solely in memory), enabling progress queries and
cancellation support via the re-indexing API endpoint.

References:
    - Requirement 8.3: Persist re-indexing progress in the database
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base

if TYPE_CHECKING:
    from alcoabase.models.company import Company


class ReindexJob(Base):
    """Tracks batch re-indexing job progress per company.

    Each re-indexing operation creates a single ReindexJob record that is
    updated as batches are dispatched and completed. The job persists status,
    batch progress, record counts, and optional cancellation metadata.

    Status lifecycle:
        queued → in_progress → completed
        queued → in_progress → failed
        queued → in_progress → cancelled

    Attributes:
        id: Primary key.
        task_id: UUID string for external reference (unique, indexed).
        company_id: FK to companies table (indexed).
        status: Job status (queued|in_progress|completed|failed|cancelled).
        total_records: Total records targeted for re-indexing.
        total_batches: Total batches computed from records and batch size.
        current_batch: Current batch number being processed.
        records_processed: Count of successfully re-indexed records.
        records_failed: Count of records that failed re-indexing.
        started_at: Job start timestamp (server-generated).
        updated_at: Last progress update timestamp (auto-updated).
        cancelled_by: User ID who cancelled the job (nullable).
        cancel_reason: Reason for cancellation (nullable).
        company: Relationship to the Company model.
    """

    __tablename__ = "literature_reindex_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="queued")
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    total_batches: Mapped[int] = mapped_column(Integer, default=0)
    current_batch: Mapped[int] = mapped_column(Integer, default=0)
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    cancelled_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    company: Mapped["Company"] = relationship()
