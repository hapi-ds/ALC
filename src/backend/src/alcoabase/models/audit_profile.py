"""Audit profile model for company-specific review configurations.

This module defines the AuditProfile model that stores company-scoped
configurations determining which auditor agents are assigned to document
reviews, what regulatory frameworks apply, severity thresholds, and
required review quorum.

References:
    - Requirement 9.4: AuditProfile database model specification
    - Requirement 4: Company-Specific Audit Profiles
    - ALCOA+ data integrity: attributable, legible, contemporaneous, original, accurate
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin


class AuditProfile(Base, AuditMixin):
    """Company-specific audit profile configuration.

    Audit profiles determine which auditor agents review documents for a
    given company, what regulatory frameworks apply, the required quorum
    of agent reviews before master summarization, and severity weight
    thresholds for compliance scoring.

    Each company can have multiple profiles but exactly one marked as
    the default (is_default=True). Soft-deletion is achieved by setting
    is_active=False.

    Attributes:
        id: Primary key.
        company_id: Foreign key to the owning company (multi-tenancy).
        name: Profile display name (max 200 chars).
        description: Optional human-readable description of the profile.
        regulatory_frameworks: JSON array of applicable framework strings
            (e.g., ["ISO 13485", "GMP", "21 CFR Part 11"]).
        assigned_agent_ids: JSON array of agent definition IDs assigned
            to this profile for parallel review.
        quorum: Minimum number of agent reviews required before the
            Master Auditor can produce a summary. Must be >= 1 and
            <= len(assigned_agent_ids).
        severity_thresholds: JSON object mapping severity levels to
            numeric weights (e.g., {"critical": 25, "major": 10,
            "minor": 3, "informational": 0.5}).
        is_default: Whether this is the company's default audit profile.
            Only one profile per company should have is_default=True.
        is_active: Whether this profile is active. Inactive profiles
            are treated as soft-deleted.
        created_at: Server-side UTC timestamp of creation.
        updated_at: Server-side timestamp updated on every modification.
    """

    __tablename__ = "audit_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    regulatory_frameworks: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=list
    )
    assigned_agent_ids: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=list
    )
    quorum: Mapped[int] = mapped_column(Integer, default=1)
    severity_thresholds: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=dict
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
