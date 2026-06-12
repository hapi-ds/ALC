"""Periodic Safety Report model for regulatory submissions.

Stores auto-generated reports documenting all vigilance monitoring
activity within configurable time windows including search strategy,
result disposition, signal summary, and regulatory compliance artifacts.

References:
    - Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
    - Design: .kiro/specs/Step_9-5_regulatory-medical-device-vigilance-pms/design.md
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin

if TYPE_CHECKING:
    from alcoabase.literature.vigilance.models.medical_product import (
        MedicalProduct,
    )
    from alcoabase.models.company import Company


class PeriodicSafetyReport(Base, AuditMixin):
    """Auto-generated periodic safety report for regulatory submissions.

    Contains structured documentation of all vigilance search activity,
    detected signals, disposition outcomes, and regulatory compliance
    artifacts for a configurable reporting period. Supports a status
    lifecycle (generated → reviewed → approved → submitted).

    Versioned via SQLAlchemy-Continuum for full audit trail.

    Attributes:
        id: Primary key.
        product_id: FK to vigilance_medical_products.
        company_id: FK to companies table (tenant isolation).
        period_start: Start date of the reporting period.
        period_end: End date of the reporting period.
        generated_at: Timestamp when the report was generated.
        report_content: Full report body as structured JSON.
        status: Report lifecycle status (generated, reviewed, approved, submitted).
        version: Report version number (incremented on edits).
        status_history: JSONB array of status transition records.
        created_by: FK to users table.
        created_at: Record creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "vigilance_periodic_safety_reports"
    __versioned__ = {}
    __table_args__ = (
        Index(
            "ix_vigilance_periodic_reports_company_status",
            "company_id",
            "status",
        ),
        Index(
            "ix_vigilance_periodic_reports_product",
            "product_id",
        ),
        Index(
            "ix_vigilance_periodic_reports_period",
            "company_id",
            "period_start",
            "period_end",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("vigilance_medical_products.id"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    report_content: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="generated")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status_history: Mapped[list] = mapped_column(JSONB, default=list)

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
    company: Mapped["Company"] = relationship()
