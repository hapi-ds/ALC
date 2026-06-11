"""Novelty Flag model for knowledge gap identification.

Records when a newly ingested paper covers topics not addressed by any
existing internal document, enabling proactive knowledge base updates.

References:
    - Requirements 7.1, 7.2, 7.3
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin

if TYPE_CHECKING:
    from alcoabase.models.company import Company


class NoveltyFlag(Base, AuditMixin):
    """Records when a paper covers topics not addressed internally.

    Created when the Contradiction Detection Service finds zero internal
    documents with similarity >= threshold for a newly indexed record.

    Lifecycle: new → acknowledged → integrated | dismissed.

    Versioned via SQLAlchemy-Continuum for full audit trail.

    Attributes:
        id: Primary key.
        ingestion_record_id: FK to the novel paper.
        company_id: Tenant isolation.
        novelty_description: LLM-generated summary (max 2000 chars).
        suggested_document_types: Array of doc types to create.
        relevance_score: Float 0.0–1.0 (relevance to company domain).
        high_priority: True if relevance_score >= 0.8.
        status: "new", "acknowledged", "integrated", "dismissed".
        linked_document_id: UUID of created internal doc (optional).
        dismissal_reason: Reason for dismissal (optional).
        acknowledged_by: User who acknowledged.
        acknowledged_at: Acknowledgment timestamp.
        integrated_by: User who integrated findings.
        integrated_at: Integration timestamp.
        dismissed_by: User who dismissed.
        dismissed_at: Dismissal timestamp.
        group_id: Optional group UUID for topic-similar flags.
        created_at: Flag creation timestamp.
    """

    __tablename__ = "literature_novelty_flags"
    __versioned__ = {}
    __table_args__ = (
        Index(
            "ix_lit_novelty_flags_company_status",
            "company_id",
            "status",
        ),
        Index(
            "ix_lit_novelty_flags_company_relevance",
            "company_id",
            "relevance_score",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ingestion_record_id: Mapped[int] = mapped_column(
        ForeignKey("literature_ingestion_records.id"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )

    # Novelty details
    novelty_description: Mapped[str] = mapped_column(Text)
    suggested_document_types: Mapped[list | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    relevance_score: Mapped[float] = mapped_column(Float)
    high_priority: Mapped[bool] = mapped_column(Boolean, default=False)

    # Status lifecycle
    status: Mapped[str] = mapped_column(String(20), default="new")
    linked_document_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    dismissal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    integrated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    integrated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dismissed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Grouping for topic-similar flags
    group_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped["Company"] = relationship()
