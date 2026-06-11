"""Screening Decision model (append-only, no versioning).

Records structured screening verdicts produced by the Literature Screener
Agent for individual ingestion records. Append-only design ensures
immutable audit trail without SQLAlchemy-Continuum overhead.

References:
    - Requirements 3.2, 4.4, 15.3
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Float,
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

if TYPE_CHECKING:
    from alcoabase.models.company import Company


class ScreeningDecision(Base):
    """Records a single screening verdict for an IngestionRecord.

    Append-only: new decisions are always inserted, never updated.
    Human overrides are stored as separate fields on the same record,
    set once after initial creation.

    Does NOT use AuditMixin — immutability is enforced at the application
    layer (append-only pattern).

    Attributes:
        id: Primary key.
        screening_run_id: FK to ScreeningRun.
        ingestion_record_id: FK to IngestionRecord being screened.
        protocol_id: FK to ScreeningProtocol used.
        company_id: Tenant isolation.
        verdict: "include", "exclude", or "uncertain".
        confidence: Float 0.0–1.0.
        rationale: Agent explanation text (max 2000 chars).
        matched_inclusion_criteria: JSONB array of criterion indices.
        matched_exclusion_criteria: JSONB array of criterion indices.
        screening_duration_ms: Time for this individual screening.
        human_verdict: Optional human override ("include" or "exclude").
        human_rationale: Optional human explanation (max 2000 chars).
        human_reviewer_id: User who overrode.
        human_override_at: Timestamp of override.
        created_at: Decision creation timestamp.
    """

    __tablename__ = "literature_screening_decisions"
    __table_args__ = (
        Index(
            "ix_lit_screening_decisions_run_record",
            "screening_run_id",
            "ingestion_record_id",
        ),
        Index(
            "ix_lit_screening_decisions_company_verdict",
            "company_id",
            "verdict",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    screening_run_id: Mapped[int] = mapped_column(
        ForeignKey("literature_screening_runs.id"), index=True
    )
    ingestion_record_id: Mapped[int] = mapped_column(
        ForeignKey("literature_ingestion_records.id"), index=True
    )
    protocol_id: Mapped[int] = mapped_column(
        ForeignKey("literature_screening_protocols.id"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )

    # AI screening result
    verdict: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    matched_inclusion_criteria: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list
    )
    matched_exclusion_criteria: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list
    )
    screening_duration_ms: Mapped[int] = mapped_column(Integer)

    # Human override fields (set once after initial creation)
    human_verdict: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    human_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_reviewer_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    human_override_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped["Company"] = relationship()
