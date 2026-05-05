"""Pydantic request/response schemas for company, membership, and agent activation endpoints.

Provides validated schemas for company creation and management,
user-company membership operations, and per-company agent activation.

References:
    - Design doc: .kiro/specs/multi-tenancy/design.md
    - Requirements 1, 2, 10: Company CRUD, Membership, Agent Activation
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CompanyCreate(BaseModel):
    """Request schema for creating a new company.

    Attributes:
        slug: URL-safe unique identifier (3-100 chars, lowercase alphanumeric and hyphens).
        display_name: Human-readable company name.
        regulatory_framework: Quality management standard governing the company.
        audit_config: Optional JSON configuration for audit profiles and review thresholds.
    """

    slug: str = Field(
        ...,
        min_length=3,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$",
        description="URL-safe unique identifier for the company.",
    )
    display_name: str = Field(..., min_length=1, max_length=300)
    regulatory_framework: Literal[
        "ISO_13485", "GMP", "GDP", "ISO_9001", "ISO_17025", "CUSTOM"
    ] = Field(..., description="Quality management standard for the company.")
    audit_config: dict = Field(
        default_factory=dict,
        description="Audit profile configuration (signature roles, training scope, retention).",
    )


class CompanyUpdate(BaseModel):
    """Request schema for updating an existing company.

    Attributes:
        display_name: Optional new display name.
        regulatory_framework: Optional new regulatory framework.
        audit_config: Optional new audit configuration.
    """

    display_name: str | None = Field(default=None, min_length=1, max_length=300)
    regulatory_framework: Literal[
        "ISO_13485", "GMP", "GDP", "ISO_9001", "ISO_17025", "CUSTOM"
    ] | None = Field(default=None)
    audit_config: dict | None = Field(default=None)


class CompanyResponse(BaseModel):
    """Response schema for a company entity.

    Attributes:
        id: Company primary key.
        slug: URL-safe unique identifier.
        display_name: Human-readable company name.
        regulatory_framework: Quality management standard.
        audit_config: Audit profile configuration.
        is_active: Whether the company is currently active.
        created_at: Server-side UTC creation timestamp.
    """

    id: int
    slug: str
    display_name: str
    regulatory_framework: str
    audit_config: dict
    is_active: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class MembershipCreate(BaseModel):
    """Request schema for adding a user to a company.

    Attributes:
        user_id: ID of the user to add.
        role: Membership role within the company.
    """

    user_id: int = Field(..., description="ID of the user to assign.")
    role: Literal["admin", "member", "viewer"] = Field(
        ..., description="Role within the company."
    )


class MembershipUpdate(BaseModel):
    """Request schema for updating a membership role.

    Attributes:
        role: New role for the membership.
    """

    role: Literal["admin", "member", "viewer"] = Field(
        ..., description="Updated role within the company."
    )


class MembershipResponse(BaseModel):
    """Response schema for a company membership.

    Attributes:
        id: Membership primary key.
        user_id: ID of the member user.
        company_id: ID of the associated company.
        role: Membership role.
        created_at: Membership creation timestamp.
        revoked_at: Timestamp when membership was revoked (null if active).
    """

    id: int
    user_id: int
    company_id: int
    role: str
    created_at: datetime | None = None
    revoked_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgentActivationCreate(BaseModel):
    """Request schema for activating a global agent for a company.

    Attributes:
        config_overrides: Optional per-company configuration overrides for the agent.
    """

    config_overrides: dict | None = Field(
        default=None,
        description="Optional configuration overrides for the activated agent.",
    )


class AgentActivationResponse(BaseModel):
    """Response schema for a company agent activation.

    Attributes:
        id: Activation primary key.
        company_id: ID of the associated company.
        agent_definition_id: ID of the activated agent definition.
        config_overrides: Per-company configuration overrides.
        is_active: Whether this activation is currently active.
        activated_at: Activation timestamp.
    """

    id: int
    company_id: int
    agent_definition_id: int
    config_overrides: dict
    is_active: bool
    activated_at: datetime | None = None

    model_config = {"from_attributes": True}
