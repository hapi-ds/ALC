"""Medical Product model for device portfolio management.

Stores regulatory metadata for registered medical devices including
device class, UDI, intended purpose, and predicate devices. Supports
multi-tenant scoping and status lifecycle (active, discontinued, recalled).

References:
    - Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
    - Design: .kiro/specs/Step_9-5_regulatory-medical-device-vigilance-pms/design.md
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
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


class MedicalProduct(Base, AuditMixin):
    """Registered medical device in a company's product portfolio.

    Each product holds regulatory metadata used to scope vigilance
    monitoring activities. Multiple VigilanceSearchProfiles can be
    associated with a single product for different search strategies.

    Versioned via SQLAlchemy-Continuum for full audit trail.

    Attributes:
        id: Primary key.
        company_id: FK to companies table (tenant isolation).
        name: Product name (1–300 characters).
        udi: Unique Device Identifier (1–128 chars, unique per company when provided).
        device_class: Regulatory classification (I, IIa, IIb, III, IVDR_A–D).
        gmdn_code: Global Medical Device Nomenclature code (1–20 chars).
        intended_purpose: Text describing intended use (max 5000 chars).
        manufacturer_name: Manufacturer name (1–300 chars, optional).
        predicate_devices: Array of predicate device names (max 10, each 1–300 chars).
        risk_class_justification: Rationale for classification (max 3000 chars).
        status: Lifecycle status (active, discontinued, recalled).
        created_by: FK to users table.
        created_at: Record creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "vigilance_medical_products"
    __versioned__ = {}
    __table_args__ = (
        # Partial unique: UDI must be unique within a company when provided
        Index(
            "uq_vigilance_medical_products_company_udi",
            "company_id",
            "udi",
            unique=True,
            postgresql_where="udi IS NOT NULL",
        ),
        Index(
            "ix_vigilance_medical_products_company_status",
            "company_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(300))
    udi: Mapped[str | None] = mapped_column(String(128), nullable=True)
    device_class: Mapped[str] = mapped_column(String(10))
    gmdn_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    intended_purpose: Mapped[str] = mapped_column(Text)
    manufacturer_name: Mapped[str | None] = mapped_column(
        String(300), nullable=True
    )
    predicate_devices: Mapped[list | None] = mapped_column(
        ARRAY(String(300)), nullable=True
    )
    risk_class_justification: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
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

    company: Mapped["Company"] = relationship()
