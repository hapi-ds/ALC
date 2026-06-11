"""Screening Run execution tracking model.

Tracks a single execution of the Literature Screener Agent against a
batch of ingestion records, including progress counters for real-time
monitoring.

References:
    - Requirements 3.3, 3.4
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base

if TYPE_CHECKING:
    from alcoabase.models.company import Company


class ScreeningRun(Base):
    """Tracks a single execution of screening against a batch of records.

    Not versioned via AuditMixin — progress counters are updated frequently
    during execution and do not require audit trail versioning.

    Attributes:
        id: Primary key.
        review_id: FK to SLRReview.
        protocol_id: FK to ScreeningProtocol (version at time of run).
        company_id: Tenant isolation.
        status: "queued", "in_progress", "completed", "failed".
        total_records: Total records in this run.
        screened_count: Successfully screened.
        include_count: Records with "include" verdict.
        exclude_count: Records with "exclude" verdict.
        uncertain_count: Records with "uncertain" verdict.
        failed_count: Records that failed to screen.
        batch_size: Configured batch size.
        total_batches: Computed number of batches.
        current_batch: Current batch being processed.
        started_at: Run start timestamp.
        completed_at: Run completion timestamp.
        total_duration_ms: Total runtime in milliseconds.
        celery_task_id: Celery task identifier for tracking.
    """

    __tablename__ = "literature_screening_runs"
    __table_args__ = (
        Index(
            "ix_lit_screening_runs_company_status",
            "company_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("literature_slr_reviews.id"), index=True
    )
    protocol_id: Mapped[int] = mapped_column(
        ForeignKey("literature_screening_protocols.id")
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )

    # Status and progress tracking
    status: Mapped[str] = mapped_column(String(20), default="queued")
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    screened_count: Mapped[int] = mapped_column(Integer, default=0)
    include_count: Mapped[int] = mapped_column(Integer, default=0)
    exclude_count: Mapped[int] = mapped_column(Integer, default=0)
    uncertain_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)

    # Batch configuration
    batch_size: Mapped[int] = mapped_column(Integer, default=20)
    total_batches: Mapped[int] = mapped_column(Integer, default=0)
    current_batch: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps and tracking
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_duration_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )

    company: Mapped["Company"] = relationship()
