"""Contradiction Alert model for literature-vs-internal-document conflicts.

Records detected contradictions between newly ingested literature and
internal corporate documents (SOPs, URS, validation plans), with severity
classification and status lifecycle tracking.

References:
    - Requirements 5.5, 5.6, 6.1, 6.4
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
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin

if TYPE_CHECKING:
    from alcoabase.models.company import Company


class ContradictionAlert(Base, AuditMixin):
    """Records a detected contradiction between literature and internal docs.

    Lifecycle: new → acknowledged → resolved | dismissed.
    Critical alerts are auto-escalated via ImpactAnalysisService.

    Versioned via SQLAlchemy-Continuum for full audit trail.

    Attributes:
        id: Primary key.
        ingestion_record_id: FK to the literature paper.
        internal_document_id: UUID of the affected internal document.
        company_id: Tenant isolation.
        severity: "critical", "major", or "minor".
        contradiction_description: Full description (max 3000 chars).
        evidence_from_literature: Supporting evidence (max 2000 chars).
        recommended_action: Suggested action (max 1000 chars).
        confidence: Analysis confidence (0.0–1.0).
        affected_internal_sections: Array of section identifiers.
        status: "new", "acknowledged", "resolved", "dismissed".
        acknowledged_by: User who acknowledged.
        acknowledged_at: Acknowledgment timestamp.
        resolution_note: Resolution explanation (max 3000 chars).
        change_request_id: Optional linked change request.
        resolved_by: User who resolved.
        resolved_at: Resolution timestamp.
        dismissal_reason: Dismissal explanation (max 2000 chars).
        dismissed_by: User who dismissed.
        dismissed_at: Dismissal timestamp.
        impact_report_id: Linked ImpactReport (for critical alerts).
        created_at: Alert creation timestamp.
    """

    __tablename__ = "literature_contradiction_alerts"
    __versioned__ = {}
    __table_args__ = (
        Index(
            "ix_lit_contradiction_alerts_company_severity_status",
            "company_id",
            "severity",
            "status",
        ),
        Index(
            "ix_lit_contradiction_alerts_company_created",
            "company_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ingestion_record_id: Mapped[int] = mapped_column(
        ForeignKey("literature_ingestion_records.id"), index=True
    )
    internal_document_id: Mapped[str] = mapped_column(String(36), index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )

    # Contradiction details
    severity: Mapped[str] = mapped_column(String(20))
    contradiction_description: Mapped[str] = mapped_column(Text)
    evidence_from_literature: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(String(1000))
    confidence: Mapped[float] = mapped_column(Float)
    affected_internal_sections: Mapped[list | None] = mapped_column(
        ARRAY(String), nullable=True
    )

    # Status lifecycle
    status: Mapped[str] = mapped_column(String(20), default="new")
    acknowledged_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_request_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    resolved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dismissal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    dismissed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Impact analysis linkage
    impact_report_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped["Company"] = relationship()
