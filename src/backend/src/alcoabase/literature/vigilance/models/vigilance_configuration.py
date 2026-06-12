"""Vigilance Configuration model for per-company escalation and reporting settings.

Stores company-level vigilance configuration including auto-escalation
rules, notification channels, report scheduling, and digest preferences.

References:
    - Requirements 7.7, 8.1
    - Design: .kiro/specs/Step_9-5_regulatory-medical-device-vigilance-pms/design.md
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin

if TYPE_CHECKING:
    from alcoabase.models.company import Company


class VigilanceConfiguration(Base, AuditMixin):
    """Per-company vigilance monitoring configuration.

    Controls escalation behavior, notification channels, and periodic
    report generation settings. One record per company (unique constraint
    on company_id).

    Versioned via SQLAlchemy-Continuum for full audit trail.

    Attributes:
        id: Primary key.
        company_id: FK to companies table (unique per company).
        critical_signal_auto_escalate: Auto-escalate critical signals.
        major_signal_daily_digest: Include major signals in daily digest.
        escalation_notification_channels: Notification channel identifiers.
        report_period: Report generation period (monthly, quarterly, annually).
        report_generation_day: Day of period for auto-generation (1–28).
        auto_report_enabled: Whether to auto-generate periodic reports.
        created_by: FK to users table.
        created_at: Record creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "vigilance_configurations"
    __versioned__ = {}

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), unique=True, index=True
    )
    critical_signal_auto_escalate: Mapped[bool] = mapped_column(
        Boolean, default=True
    )
    major_signal_daily_digest: Mapped[bool] = mapped_column(
        Boolean, default=True
    )
    escalation_notification_channels: Mapped[list] = mapped_column(
        ARRAY(String(50))
    )
    report_period: Mapped[str] = mapped_column(String(20), default="quarterly")
    report_generation_day: Mapped[int] = mapped_column(Integer, default=1)
    auto_report_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Audit fields
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship()
