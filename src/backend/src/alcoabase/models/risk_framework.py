"""Risk framework models for AI Risk & Compliance Framework (Phase 8.1).

This module defines the database models for the AI Risk & Compliance Framework,
including:
- AITaskType: Registry of AI-powered task types with risk classifications
- CompanyRiskProfile: Per-tenant risk profile configuration
- RiskTierOverride: Company-specific tier overrides within a profile
- RiskAssessmentRecord: Immutable records of tier assignment changes
- HITLCheckpoint: Human-in-the-loop review checkpoints for AI operations
- AIOperationLog: Immutable operation audit logs at tier-appropriate depth
- ControlEnforcementLog: Immutable control enforcement records

Versioned models (AuditMixin): AITaskType, CompanyRiskProfile, HITLCheckpoint
— these support updates and use SQLAlchemy-Continuum for audit trail.

Immutable models (event listeners): RiskAssessmentRecord, AIOperationLog,
ControlEnforcementLog — append-only, no UPDATE/DELETE permitted at the
application layer.

References:
    - Design: .kiro/specs/Step_8-1_ai-risk-compliance-framework/design.md
    - Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8
    - ALCOA+ data integrity: attributable, legible, contemporaneous, original, accurate
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin


# ---------------------------------------------------------------------------
# Enum Definitions
# ---------------------------------------------------------------------------


class RiskTier(str, enum.Enum):
    """Risk classification level for AI task types.

    Determines the depth of validation, HITL requirements, and audit
    logging granularity applied to an AI operation.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AuditDepth(str, enum.Enum):
    """Granularity of audit logging for an AI operation.

    - full: All inputs, outputs, intermediate steps, token counts, model params
    - standard: Inputs, outputs, model used, duration
    - minimal: Operation type, timestamp, user, success/failure
    """

    FULL = "full"
    STANDARD = "standard"
    MINIMAL = "minimal"


class GateResult(str, enum.Enum):
    """Outcome of a Control Gate enforcement check."""

    PASSED = "passed"
    BLOCKED = "blocked"


class CheckpointStatus(str, enum.Enum):
    """Status of a HITL checkpoint in its lifecycle.

    Valid transitions: pending -> approved | rejected | expired
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# Versioned Models (AuditMixin — SQLAlchemy-Continuum)
# ---------------------------------------------------------------------------


class AITaskType(Base, AuditMixin):
    """Registry entry for an AI-powered task type with risk classification.

    Each AI task type maps to exactly one default risk tier and can be
    overridden per company via CompanyRiskProfile. System-defined task types
    have company_id=NULL; company-custom task types reference a specific company.

    Attributes:
        id: UUID primary key.
        task_type_id: Unique string identifier (lowercase alphanumeric + underscores).
        display_name: Human-readable name (max 200 chars).
        description: Detailed description of the task type.
        module_reference: AlcoaBase phase/feature reference (e.g., "5.4").
        default_risk_tier: Default risk tier assignment.
        risk_factors: JSON array of strings describing why this tier was assigned.
        is_active: Whether the task type is currently active.
        is_system_defined: True for built-in task types, False for company-custom.
        company_id: FK to companies (NULL for system-defined).
        created_at: Server-generated creation timestamp.
        updated_at: Server-generated update timestamp.
    """

    __tablename__ = "ai_task_types"
    __table_args__ = (
        UniqueConstraint("task_type_id", name="uq_ai_task_types_task_type_id"),
        Index("ix_ai_task_types_company_id", "company_id"),
        Index("ix_ai_task_types_task_type_id", "task_type_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_type_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    module_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    default_risk_tier: Mapped[str] = mapped_column(String(10), nullable=False)
    risk_factors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_system_defined: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


class CompanyRiskProfile(Base, AuditMixin):
    """Per-tenant risk profile configuration with tier overrides.

    Each company can have at most one active profile at any time. Creating
    a new profile deactivates the previous one (soft-delete with is_active=false).
    A partial unique index on (company_id) WHERE is_active=true enforces this
    at the database level.

    Attributes:
        id: UUID primary key.
        company_id: FK to the owning company.
        profile_name: Human-readable profile name (max 200 chars).
        description: Optional description.
        regulatory_frameworks: JSON array of applicable framework identifiers.
        is_active: Whether this is the currently active profile.
        created_by: FK to the user who created the profile.
        created_at: Server-generated creation timestamp.
        updated_at: Server-generated update timestamp.
    """

    __tablename__ = "company_risk_profiles"
    __table_args__ = (
        # Partial unique index: at most one active profile per company
        Index(
            "ix_company_risk_profiles_active_company",
            "company_id",
            unique=True,
            postgresql_where="is_active = true",
        ),
        Index("ix_company_risk_profiles_company_id", "company_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    profile_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    regulatory_frameworks: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


class RiskTierOverride(Base):
    """Company-specific tier override within a risk profile.

    Each override assigns a specific risk tier to a task type, potentially
    differing from the system default. De-escalation overrides require
    additional justification and approval.

    Attributes:
        id: UUID primary key.
        profile_id: FK to the parent CompanyRiskProfile.
        task_type_id: The AI task type identifier being overridden.
        assigned_tier: The overridden risk tier.
        justification: Rationale for the override (required for de-escalation).
        regulatory_reference: Regulatory basis for de-escalation.
        approved_by: FK to approving user (required for de-escalation).
        approval_date: Timestamp of approval (required when approved_by is set).
        created_at: Server-generated creation timestamp.
    """

    __tablename__ = "risk_tier_overrides"
    __table_args__ = (
        Index("ix_risk_tier_overrides_profile_id", "profile_id"),
        Index("ix_risk_tier_overrides_task_type_id", "task_type_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company_risk_profiles.id"),
        nullable=False,
    )
    task_type_id: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_tier: Mapped[str] = mapped_column(String(10), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    regulatory_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    approval_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Immutable Models (event listeners — no UPDATE/DELETE)
# ---------------------------------------------------------------------------


class RiskAssessmentRecord(Base):
    """Immutable record documenting a risk tier assignment change.

    Created for every tier change (both escalation and de-escalation).
    This record is append-only — no UPDATE or DELETE operations are permitted.

    Attributes:
        id: UUID primary key.
        company_id: FK to the company.
        task_type_id: The AI task type whose tier changed.
        previous_tier: Previous risk tier (nullable for initial assignment).
        new_tier: New risk tier.
        assessor_user_id: FK to the user who made the change.
        assessment_date: When the assessment was performed.
        justification: Rationale for the tier change.
        regulatory_references: JSON array of regulatory references.
        created_at: Server-generated creation timestamp.
    """

    __tablename__ = "risk_assessment_records"
    __table_args__ = (
        Index("ix_risk_assessment_records_company_id", "company_id"),
        Index("ix_risk_assessment_records_task_type_id", "task_type_id"),
        Index("ix_risk_assessment_records_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    task_type_id: Mapped[str] = mapped_column(String(100), nullable=False)
    previous_tier: Mapped[str | None] = mapped_column(String(10), nullable=True)
    new_tier: Mapped[str] = mapped_column(String(10), nullable=False)
    assessor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    assessment_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    regulatory_references: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Versioned Model (AuditMixin — SQLAlchemy-Continuum)
# ---------------------------------------------------------------------------


class HITLCheckpoint(Base, AuditMixin):
    """Human-in-the-loop review checkpoint for AI operations.

    Created for High and Medium tier operations. Tracks the review lifecycle
    from pending through approval, rejection, or expiry.

    Valid state transitions: pending -> approved | rejected | expired

    Attributes:
        id: UUID primary key.
        company_id: FK to the company.
        operation_id: Reference to the AI operation.
        task_type_id: The AI task type identifier.
        ai_output_reference: URI or storage key for the AI output.
        status: Current checkpoint status.
        assigned_reviewer_role: Minimum role required to review.
        reviewer_user_id: FK to the reviewing user (set on review).
        reviewer_comments: Reviewer's comments (required for rejection).
        reviewed_sections: JSON array of reviewed section identifiers.
        created_at: Server-generated creation timestamp.
        expires_at: Expiry timestamp (72 hours from creation for High tier).
        reviewed_at: Timestamp when the review was completed.
    """

    __tablename__ = "hitl_checkpoints"
    __table_args__ = (
        Index("ix_hitl_checkpoints_company_id", "company_id"),
        Index("ix_hitl_checkpoints_task_type_id", "task_type_id"),
        Index("ix_hitl_checkpoints_status", "status"),
        Index("ix_hitl_checkpoints_created_at", "created_at"),
        Index("ix_hitl_checkpoints_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    operation_id: Mapped[str] = mapped_column(String(200), nullable=False)
    task_type_id: Mapped[str] = mapped_column(String(100), nullable=False)
    ai_output_reference: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    assigned_reviewer_role: Mapped[str] = mapped_column(String(50), nullable=False)
    reviewer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    reviewer_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_sections: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ---------------------------------------------------------------------------
# Immutable Models (event listeners — no UPDATE/DELETE)
# ---------------------------------------------------------------------------


class AIOperationLog(Base):
    """Immutable audit log for AI operations at tier-appropriate depth.

    Records every AI operation with fields matching the tier's audit depth:
    - full: all inputs/outputs/intermediate steps/model params/token counts
    - standard: input summary/output/model_name/token counts/source doc IDs
    - minimal: task_type_id/user_id/company_id/timestamp/status/duration

    This record is append-only — no UPDATE or DELETE operations are permitted.

    Attributes:
        id: UUID primary key.
        company_id: FK to the company.
        task_type_id: The AI task type identifier.
        risk_tier: Risk tier applied to this operation.
        user_id: FK to the user who initiated the operation.
        audit_depth: Logging depth applied.
        input_data: JSONB input data (null for minimal depth).
        output_data: JSONB output data (null for minimal depth).
        model_name: Name of the AI model used.
        inference_duration_ms: Duration of inference in milliseconds.
        token_count_input: Number of input tokens.
        token_count_output: Number of output tokens.
        gate_result: Whether the operation passed or was blocked.
        blocking_reason: Reason for blocking (if blocked).
        source_document_ids: JSON array of referenced document IDs.
        created_at: Server-generated creation timestamp.
    """

    __tablename__ = "ai_operation_logs"
    __table_args__ = (
        Index("ix_ai_operation_logs_company_id", "company_id"),
        Index("ix_ai_operation_logs_task_type_id", "task_type_id"),
        Index("ix_ai_operation_logs_created_at", "created_at"),
        Index("ix_ai_operation_logs_user_id", "user_id"),
        Index("ix_ai_operation_logs_risk_tier", "risk_tier"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    task_type_id: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(10), nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    audit_depth: Mapped[str] = mapped_column(String(10), nullable=False)
    input_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    inference_duration_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    token_count_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gate_result: Mapped[str] = mapped_column(String(10), nullable=False)
    blocking_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ControlEnforcementLog(Base):
    """Immutable record of control enforcement for an AI operation.

    Created for every AI operation regardless of tier, success, or failure.
    Records which controls were enforced, which were satisfied, and the
    overall gate result.

    This record is append-only — no UPDATE or DELETE operations are permitted.

    Attributes:
        id: UUID primary key.
        company_id: FK to the company.
        operation_log_id: FK to the associated AIOperationLog.
        task_type_id: The AI task type identifier.
        risk_tier: Risk tier applied.
        controls_enforced: JSON array of control names that were enforced.
        controls_satisfied: JSON object mapping control name to boolean.
        overall_result: Whether all controls passed or operation was blocked.
        blocking_reason: Reason for blocking (if blocked).
        enforcement_duration_ms: Time spent on enforcement checks.
        created_at: Server-generated creation timestamp.
    """

    __tablename__ = "control_enforcement_logs"
    __table_args__ = (
        Index("ix_control_enforcement_logs_company_id", "company_id"),
        Index("ix_control_enforcement_logs_operation_log_id", "operation_log_id"),
        Index("ix_control_enforcement_logs_task_type_id", "task_type_id"),
        Index("ix_control_enforcement_logs_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    operation_log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_operation_logs.id"),
        nullable=False,
    )
    task_type_id: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(10), nullable=False)
    controls_enforced: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    controls_satisfied: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    overall_result: Mapped[str] = mapped_column(String(10), nullable=False)
    blocking_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    enforcement_duration_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
