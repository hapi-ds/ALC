"""SLR Review workflow model with state machine and PRISMA tracking.

Tracks the lifecycle of a Systematic Literature Review from protocol
definition through screening, human review, and completion.

References:
    - Requirements 4.1, 4.2, 4.3
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
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin

if TYPE_CHECKING:
    from alcoabase.models.company import Company


class SLRReview(Base, AuditMixin):
    """Systematic Literature Review workflow instance.

    Manages the end-to-end SLR lifecycle with state machine enforcement:
    protocol_defined → screening_in_progress → screening_complete →
    human_review_in_progress → completed.

    PRISMA Flow statistics are computed from associated ScreeningDecision
    aggregates rather than stored as denormalized counters.

    Versioned via SQLAlchemy-Continuum for full audit trail.

    Attributes:
        id: Primary key.
        company_id: Tenant isolation.
        protocol_id: FK to ScreeningProtocol.
        name: Review name (1–200 chars).
        description: Optional description.
        status: Lifecycle state.
        record_filter: JSONB filter used to resolve record set.
        created_by: Initiating user.
        completed_by: User who completed the review (nullable).
        records_identified: Total records submitted.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
        completed_at: Completion timestamp (nullable).
    """

    __tablename__ = "literature_slr_reviews"
    __versioned__ = {}
    __table_args__ = (
        Index(
            "ix_lit_slr_reviews_company_status",
            "company_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    protocol_id: Mapped[int] = mapped_column(
        ForeignKey("literature_screening_protocols.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="protocol_defined")
    record_filter: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    completed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_identified: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    company: Mapped["Company"] = relationship()
