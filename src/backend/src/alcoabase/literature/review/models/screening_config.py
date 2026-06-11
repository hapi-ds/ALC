"""Per-company screening configuration model.

Controls automated screening behavior, batch sizes, confidence thresholds,
and contradiction detection toggles on a per-company basis.

References:
    - Requirements 11.1, 11.2, 11.3
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin

if TYPE_CHECKING:
    from alcoabase.models.company import Company


class ScreeningConfiguration(Base, AuditMixin):
    """Per-company screening behavior settings.

    One record per company. Controls automation preferences for the
    literature review subsystem.

    Versioned via SQLAlchemy-Continuum for full audit trail.

    Attributes:
        id: Primary key.
        company_id: FK to companies (unique per company).
        auto_screen_on_index: Auto-screen newly indexed papers.
        default_batch_size: Default batch size for screening runs (1–100).
        confidence_threshold_for_auto_include: AI decisions above this skip
            human review (0.5–1.0).
        max_concurrent_screening_tasks: Max parallel screening tasks (1–20).
        contradiction_detection_enabled: Enable cross-reference tasks.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "literature_screening_configurations"
    __versioned__ = {}
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_screening_config_company"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), unique=True, index=True
    )
    auto_screen_on_index: Mapped[bool] = mapped_column(Boolean, default=False)
    default_batch_size: Mapped[int] = mapped_column(Integer, default=20)
    confidence_threshold_for_auto_include: Mapped[float] = mapped_column(
        Float, default=0.8
    )
    max_concurrent_screening_tasks: Mapped[int] = mapped_column(
        Integer, default=5
    )
    contradiction_detection_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship()
