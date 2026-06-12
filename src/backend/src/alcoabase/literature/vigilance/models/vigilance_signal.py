"""Vigilance Signal model for detected safety signals.

Records safety signals identified by the Vigilance Analyst agent including
severity classification, evidence summary, regulatory references, and
disposition tracking.

References:
    - Requirements 5.3, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
    - Design: .kiro/specs/Step_9-5_regulatory-medical-device-vigilance-pms/design.md
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
    from alcoabase.literature.vigilance.models.medical_product import (
        MedicalProduct,
    )
    from alcoabase.literature.vigilance.models.vigilance_search_profile import (
        VigilanceSearchProfile,
    )
    from alcoabase.models.company import Company


class VigilanceSignal(Base, AuditMixin):
    """A detected safety signal from vigilance literature analysis.

    Created when the Vigilance Analyst agent identifies a potential safety
    signal with confidence >= threshold. Tracks severity classification,
    evidence, regulatory references, recommended actions, and disposition
    lifecycle (under_review → confirmed/dismissed/escalated).

    Versioned via SQLAlchemy-Continuum for full audit trail.

    Attributes:
        id: Primary key.
        ingestion_record_id: FK to the literature ingestion record.
        product_id: FK to vigilance_medical_products.
        profile_id: FK to vigilance_search_profiles.
        company_id: FK to companies table (tenant isolation).
        severity: Signal severity (critical, major, minor).
        evidence_summary: Agent explanation of findings (max 3000 chars).
        affected_product_aspects: Device functions/components implicated.
        regulatory_references: Applicable regulation articles.
        recommended_actions: Suggested next steps (max 5 entries).
        confidence: Analysis confidence (0.0–1.0).
        disposition: Current review status (under_review, confirmed, dismissed, escalated).
        dismissal_reason: Required when disposition is dismissed (max 2000 chars).
        confirmation_note: Required when disposition is confirmed (max 3000 chars).
        reviewer_user_id: User who changed disposition.
        detection_timestamp: When the signal was detected.
        created_by: FK to users table (system user for automated detection).
        created_at: Record creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "vigilance_signals"
    __versioned__ = {}
    __table_args__ = (
        Index(
            "ix_vigilance_signals_company_severity",
            "company_id",
            "severity",
        ),
        Index(
            "ix_vigilance_signals_company_disposition",
            "company_id",
            "disposition",
        ),
        Index(
            "ix_vigilance_signals_product",
            "product_id",
        ),
        Index(
            "ix_vigilance_signals_profile",
            "profile_id",
        ),
        Index(
            "ix_vigilance_signals_ingestion_record",
            "ingestion_record_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ingestion_record_id: Mapped[int] = mapped_column(
        ForeignKey("literature_ingestion_records.id"), index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("vigilance_medical_products.id"), index=True
    )
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("vigilance_search_profiles.id"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )

    # Signal analysis fields
    severity: Mapped[str] = mapped_column(String(20))
    evidence_summary: Mapped[str] = mapped_column(Text)
    affected_product_aspects: Mapped[list] = mapped_column(
        ARRAY(String(500))
    )
    regulatory_references: Mapped[list] = mapped_column(
        ARRAY(String(200))
    )
    recommended_actions: Mapped[list] = mapped_column(
        ARRAY(String(500))
    )
    confidence: Mapped[float] = mapped_column(Float)

    # Disposition tracking
    disposition: Mapped[str] = mapped_column(String(20), default="under_review")
    dismissal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # Detection timestamp
    detection_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Audit fields
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped["MedicalProduct"] = relationship()
    profile: Mapped["VigilanceSearchProfile"] = relationship()
    company: Mapped["Company"] = relationship()
