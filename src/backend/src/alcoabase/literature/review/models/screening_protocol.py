"""Screening Protocol model for systematic literature review criteria.

Defines inclusion/exclusion criteria using the PICO framework and custom
keyword/regex patterns. Supports versioning for audit trail compliance.

References:
    - Requirements 2.1, 2.7, 2.8
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin

if TYPE_CHECKING:
    from alcoabase.models.company import Company


class ScreeningProtocol(Base, AuditMixin):
    """Defines inclusion/exclusion criteria for systematic literature reviews.

    Supports PICO framework fields (Population, Intervention, Comparison,
    Outcome), custom inclusion/exclusion keyword patterns (including regex),
    date range filtering, publication type filtering, and language filtering.

    Versioned via SQLAlchemy-Continuum for full audit trail.

    Attributes:
        id: Primary key.
        company_id: FK to companies table (tenant isolation).
        name: Protocol name (1–200 chars).
        description: Optional description (max 5000 chars).
        version: Auto-incremented on updates.
        status: "draft", "active", or "archived".
        created_by: FK to users table.
        pico_population: PICO population criteria (max 2000 chars).
        pico_intervention: PICO intervention criteria (max 2000 chars).
        pico_comparison: PICO comparison criteria (max 2000 chars, optional).
        pico_outcome: PICO outcome criteria (max 2000 chars).
        inclusion_criteria: JSONB array of keyword/regex patterns (max 20).
        exclusion_criteria: JSONB array of keyword/regex patterns (max 20).
        publication_date_from: Optional start date filter (ISO-8601).
        publication_date_to: Optional end date filter (ISO-8601).
        allowed_publication_types: Optional array of allowed types.
        allowed_languages: Optional array of ISO 639-1 codes.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "literature_screening_protocols"
    __versioned__ = {}
    __table_args__ = (
        Index(
            "ix_lit_screening_protocols_company_status",
            "company_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # PICO framework fields
    pico_population: Mapped[str | None] = mapped_column(
        String(2000), nullable=True
    )
    pico_intervention: Mapped[str | None] = mapped_column(
        String(2000), nullable=True
    )
    pico_comparison: Mapped[str | None] = mapped_column(
        String(2000), nullable=True
    )
    pico_outcome: Mapped[str | None] = mapped_column(
        String(2000), nullable=True
    )

    # Custom criteria (JSONB arrays of keyword/regex patterns)
    inclusion_criteria: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list
    )
    exclusion_criteria: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list
    )

    # Filtering fields
    publication_date_from: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    publication_date_to: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    allowed_publication_types: Mapped[list | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    allowed_languages: Mapped[list | None] = mapped_column(
        ARRAY(String), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship()
