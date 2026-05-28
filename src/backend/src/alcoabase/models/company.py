"""Company, membership, and agent activation models for multi-tenancy.

This module defines the core multi-tenancy models:
- Company: The tenant entity representing a single organization.
- CompanyMembership: Association between users and companies with roles.
- CompanyAgentActivation: Per-company activation of global agent definitions.

References:
    - Multi-tenancy design: .kiro/specs/multi-tenancy/design.md
    - Requirements: .kiro/specs/multi-tenancy/requirements.md (Req 1, 2, 10, 12)
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base


class Company(Base):
    """Tenant entity representing a single organization.

    Each Company operates in an isolated data context within AlcoaBase.
    All tenant-scoped resources (documents, templates, workflows, etc.)
    are associated with exactly one Company via a company_id foreign key.

    Attributes:
        id: Primary key.
        slug: Unique URL-safe identifier for the company.
        display_name: Human-readable company name.
        regulatory_framework: Quality management standard (e.g., ISO_13485, GMP).
        audit_config: JSON configuration for audit profiles and review thresholds.
        is_active: Whether the company is currently active.
        created_at: Server-side UTC timestamp of creation.
        memberships: List of user memberships in this company.
    """

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(300))
    regulatory_framework: Mapped[str] = mapped_column(String(50))
    audit_config: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    memberships: Mapped[list["CompanyMembership"]] = relationship(
        back_populates="company"
    )


class CompanyMembership(Base):
    """Association between a user and a company with a designated role.

    A user can belong to multiple companies. Each membership has a role
    that determines the user's permissions within that company context.

    Attributes:
        id: Primary key.
        user_id: Foreign key to the user.
        company_id: Foreign key to the company.
        role: Membership role ("admin", "member", or "viewer").
        created_at: Server-side UTC timestamp of membership creation.
        revoked_at: Timestamp when membership was revoked (null if active).
        user: Relationship to the User model.
        company: Relationship to the Company model.
    """

    __tablename__ = "company_memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    role: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship()
    company: Mapped["Company"] = relationship(back_populates="memberships")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "company_id", name="uq_company_memberships_user_company"
        ),
    )


class CompanyAgentActivation(Base):
    """Per-company activation of a global agent definition.

    Companies activate global agent definitions to make them available
    for document review within their tenant context. Optional config
    overrides allow per-company customization without modifying the
    global definition.

    Attributes:
        id: Primary key.
        company_id: Foreign key to the company.
        agent_definition_id: Foreign key to the agent definition.
        config_overrides: JSON overrides for the agent configuration.
        is_active: Whether this activation is currently active.
        activated_at: Server-side UTC timestamp of activation.
        company: Relationship to the Company model.
        agent_definition: Relationship to the AgentDefinition model.
    """

    __tablename__ = "company_agent_activations"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    agent_definition_id: Mapped[int] = mapped_column(
        ForeignKey("agent_definitions.id"), index=True
    )
    config_overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(default=True)
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped["Company"] = relationship()
    agent_definition: Mapped["AgentDefinition"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "agent_definition_id",
            name="uq_company_agent_activations_company_agent",
        ),
    )
