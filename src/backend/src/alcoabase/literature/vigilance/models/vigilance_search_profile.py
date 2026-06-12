"""Vigilance Search Profile model for scheduled search configuration.

Defines per-product search parameters including search terms, MeSH terms,
adverse event keywords, device identifiers, exclusion terms, source
selection, and cron scheduling.

References:
    - Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
    - Design: .kiro/specs/Step_9-5_regulatory-medical-device-vigilance-pms/design.md
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
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
    from alcoabase.models.company import Company


class VigilanceSearchProfile(Base, AuditMixin):
    """Configuration for automated vigilance literature searches.

    Defines what to search for (terms, keywords, identifiers), where to
    search (source_ids), what to exclude, and when to execute (cron).
    Linked to a specific MedicalProduct within a company.

    Versioned via SQLAlchemy-Continuum for full audit trail.

    Attributes:
        id: Primary key.
        product_id: FK to vigilance_medical_products.
        company_id: FK to companies table (tenant isolation).
        name: Profile name (1–200 chars).
        search_terms: Array of product names/brand names/synonyms (1–50, each 1–500).
        mesh_terms: Array of MeSH descriptors (0–30, each 1–200).
        adverse_event_keywords: Array of adverse event descriptors (1–50, each 1–500).
        device_identifiers: Array of UDIs/catalog/model numbers (0–20, each 1–200).
        exclusion_terms: Array of exclusion terms (0–30, each 1–500).
        source_ids: Array of source adapter identifiers (empty = all enabled).
        schedule_cron: Valid 5-field cron expression.
        status: Profile status (active, paused, archived).
        created_by: FK to users table.
        created_at: Record creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "vigilance_search_profiles"
    __versioned__ = {}
    __table_args__ = (
        Index(
            "ix_vigilance_search_profiles_company_status",
            "company_id",
            "status",
        ),
        Index(
            "ix_vigilance_search_profiles_product",
            "product_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("vigilance_medical_products.id"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    search_terms: Mapped[list] = mapped_column(ARRAY(String(500)))
    mesh_terms: Mapped[list | None] = mapped_column(
        ARRAY(String(200)), nullable=True
    )
    adverse_event_keywords: Mapped[list] = mapped_column(ARRAY(String(500)))
    device_identifiers: Mapped[list | None] = mapped_column(
        ARRAY(String(200)), nullable=True
    )
    exclusion_terms: Mapped[list | None] = mapped_column(
        ARRAY(String(500)), nullable=True
    )
    source_ids: Mapped[list | None] = mapped_column(
        ARRAY(String(100)), nullable=True
    )
    schedule_cron: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active")

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
