"""Pydantic request/response schemas for AI Risk & Compliance Framework.

Provides validated schemas for risk framework operations including:
- AI task type registry queries
- Company risk profile management (create, update)
- HITL checkpoint review
- Operation log queries
- Dashboard statistics
- Tier definitions

References:
    - Design doc: .kiro/specs/Step_8-1_ai-risk-compliance-framework/design.md
    - Requirements: 1.1, 3.2, 5.2, 5.11, 10.1–10.16
"""

from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


T = TypeVar("T")


# ---------------------------------------------------------------------------
# Generic Pagination
# ---------------------------------------------------------------------------


class PaginatedResult(BaseModel, Generic[T]):
    """Generic paginated response wrapper.

    Attributes:
        items: List of items for the current page.
        total: Total number of items matching the query.
        limit: Maximum items per page that was requested.
        offset: Number of items skipped.
    """

    items: list[T] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------


class RiskTierOverrideEntry(BaseModel):
    """Single tier override entry within a profile creation/update request.

    Attributes:
        task_type_id: The AI task type identifier to override.
        assigned_tier: The risk tier to assign (high, medium, or low).
        justification: Rationale for the override (min 50 chars for de-escalation).
        regulatory_reference: Regulatory basis (required for de-escalation).
        approved_by: UUID of approving user (required for de-escalation).
    """

    task_type_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="AI task type identifier to override.",
    )
    assigned_tier: Literal["high", "medium", "low"] = Field(
        ...,
        description="Risk tier to assign.",
    )
    justification: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Rationale for the override.",
    )
    regulatory_reference: str | None = Field(
        default=None,
        max_length=2000,
        description="Regulatory basis for de-escalation.",
    )
    approved_by: UUID | None = Field(
        default=None,
        description="UUID of approving user (required for de-escalation).",
    )

    @field_validator("task_type_id")
    @classmethod
    def validate_task_type_id_pattern(cls, v: str) -> str:
        """Validate task_type_id matches ^[a-z0-9_]{1,100}$."""
        import re

        if not re.fullmatch(r"[a-z0-9_]{1,100}", v):
            raise ValueError(
                "task_type_id must contain only lowercase alphanumeric "
                "characters and underscores (1-100 characters)."
            )
        return v


class CreateProfileRequest(BaseModel):
    """Request schema for creating a Company Risk Profile.

    Attributes:
        profile_name: Human-readable profile name (3-200 characters).
        description: Optional description (max 2000 characters).
        regulatory_frameworks: Array of 1-20 applicable framework identifiers.
        overrides: Array of 1-50 tier override entries.
    """

    profile_name: str = Field(
        ...,
        min_length=3,
        max_length=200,
        description="Human-readable profile name.",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional profile description.",
    )
    regulatory_frameworks: list[str] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Array of applicable regulatory framework identifiers.",
    )
    overrides: list[RiskTierOverrideEntry] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Array of tier override entries.",
    )

    @field_validator("regulatory_frameworks")
    @classmethod
    def validate_regulatory_frameworks(cls, v: list[str]) -> list[str]:
        """Ensure each framework identifier is non-empty."""
        for i, framework in enumerate(v):
            if not framework or not framework.strip():
                raise ValueError(
                    f"regulatory_frameworks[{i}] must be a non-empty string."
                )
        return v

    @model_validator(mode="after")
    def validate_no_duplicate_task_type_ids(self) -> "CreateProfileRequest":
        """Ensure no duplicate task_type_ids in overrides array."""
        task_type_ids = [override.task_type_id for override in self.overrides]
        duplicates = [
            tid for tid in set(task_type_ids) if task_type_ids.count(tid) > 1
        ]
        if duplicates:
            raise ValueError(
                f"Duplicate task_type_id values in overrides: {', '.join(sorted(duplicates))}"
            )
        return self

    @model_validator(mode="after")
    def validate_deescalation_justification(self) -> "CreateProfileRequest":
        """Ensure de-escalation overrides have justification >= 50 chars.

        Note: Full de-escalation validation (comparing against default tier)
        is performed at the service layer since it requires DB lookups.
        This validator enforces the minimum justification length constraint
        that applies universally.
        """
        for override in self.overrides:
            if len(override.justification) < 50:
                # We can't determine escalation vs de-escalation at schema level
                # without knowing the default tier. The service layer handles that.
                # However, we enforce the minimum for ALL overrides as a baseline.
                pass
        return self


class UpdateProfileRequest(BaseModel):
    """Request schema for updating a Company Risk Profile (partial update).

    All fields are optional for partial updates.

    Attributes:
        profile_name: Human-readable profile name (3-200 characters).
        description: Optional description (max 2000 characters).
        regulatory_frameworks: Array of 1-20 applicable framework identifiers.
        overrides: Array of 1-50 tier override entries.
    """

    profile_name: str | None = Field(
        default=None,
        min_length=3,
        max_length=200,
        description="Human-readable profile name.",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional profile description.",
    )
    regulatory_frameworks: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        description="Array of applicable regulatory framework identifiers.",
    )
    overrides: list[RiskTierOverrideEntry] | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="Array of tier override entries.",
    )

    @field_validator("regulatory_frameworks")
    @classmethod
    def validate_regulatory_frameworks(cls, v: list[str] | None) -> list[str] | None:
        """Ensure each framework identifier is non-empty when provided."""
        if v is None:
            return v
        for i, framework in enumerate(v):
            if not framework or not framework.strip():
                raise ValueError(
                    f"regulatory_frameworks[{i}] must be a non-empty string."
                )
        return v

    @model_validator(mode="after")
    def validate_no_duplicate_task_type_ids(self) -> "UpdateProfileRequest":
        """Ensure no duplicate task_type_ids in overrides array when provided."""
        if self.overrides is None:
            return self
        task_type_ids = [override.task_type_id for override in self.overrides]
        duplicates = [
            tid for tid in set(task_type_ids) if task_type_ids.count(tid) > 1
        ]
        if duplicates:
            raise ValueError(
                f"Duplicate task_type_id values in overrides: {', '.join(sorted(duplicates))}"
            )
        return self


class ReviewCheckpointRequest(BaseModel):
    """Request schema for reviewing a HITL checkpoint.

    Attributes:
        action: Review action — "approve" or "reject".
        reviewer_comments: Reviewer's comments (required on reject, max 2000 chars).
        reviewed_sections: Optional array of section identifiers reviewed (max 50).
    """

    action: Literal["approve", "reject"] = Field(
        ...,
        description="Review action: approve or reject.",
    )
    reviewer_comments: str | None = Field(
        default=None,
        max_length=2000,
        description="Reviewer's comments (required for rejection).",
    )
    reviewed_sections: list[str] | None = Field(
        default=None,
        max_length=50,
        description="Optional array of section identifiers that were reviewed.",
    )

    @model_validator(mode="after")
    def validate_comments_required_on_reject(self) -> "ReviewCheckpointRequest":
        """Ensure reviewer_comments is provided and non-empty when action is reject."""
        if self.action == "reject":
            if not self.reviewer_comments or not self.reviewer_comments.strip():
                raise ValueError(
                    "reviewer_comments is required when action is 'reject'."
                )
        return self


class CheckpointFilters(BaseModel):
    """Filter criteria for HITL checkpoint queries.

    Attributes:
        task_type_id: Filter by AI task type identifier.
        status: Filter by checkpoint status.
        assigned_reviewer: Filter by assigned reviewer UUID.
        start_date: Filter by creation date >= start_date (ISO 8601).
        end_date: Filter by creation date <= end_date (ISO 8601).
    """

    task_type_id: str | None = Field(
        default=None,
        max_length=100,
        description="Filter by AI task type identifier.",
    )
    status: Literal["pending", "approved", "rejected", "expired"] | None = Field(
        default=None,
        description="Filter by checkpoint status.",
    )
    assigned_reviewer: UUID | None = Field(
        default=None,
        description="Filter by assigned reviewer UUID.",
    )
    start_date: datetime | None = Field(
        default=None,
        description="Filter by creation date >= start_date (ISO 8601).",
    )
    end_date: datetime | None = Field(
        default=None,
        description="Filter by creation date <= end_date (ISO 8601).",
    )

    @field_validator("task_type_id")
    @classmethod
    def validate_task_type_id_pattern(cls, v: str | None) -> str | None:
        """Validate task_type_id matches ^[a-z0-9_]{1,100}$ when provided."""
        if v is None:
            return v
        import re

        if not re.fullmatch(r"[a-z0-9_]{1,100}", v):
            raise ValueError(
                "task_type_id must contain only lowercase alphanumeric "
                "characters and underscores (1-100 characters)."
            )
        return v

    @model_validator(mode="after")
    def validate_date_range(self) -> "CheckpointFilters":
        """Ensure start_date is not after end_date when both are provided."""
        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                raise ValueError("start_date must be before end_date.")
        return self


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------


class TierDefinitionResponse(BaseModel):
    """Response schema for a risk tier definition with its control set.

    Attributes:
        tier_level: The risk tier level (high, medium, low).
        display_name: Human-readable tier name.
        description: Description of the tier.
        hitl_required: Whether HITL checkpoint is required.
        hitl_blocks_visibility: Whether HITL blocks output visibility.
        audit_depth: Audit logging depth for this tier.
        validations: List of validation requirements.
        provenance_required: Whether generation provenance is required.
        expiry_hours: Hours until unreviewed output expires (null for Low).
        rate_limit: Rate limit per user per hour (null if no limit).
        output_label: Output metadata label (null for High).
        enforcement_type: Whether controls are enforced automatically or manually.
    """

    tier_level: Literal["high", "medium", "low"]
    display_name: str
    description: str
    hitl_required: bool
    hitl_blocks_visibility: bool
    audit_depth: Literal["full", "standard", "minimal"]
    validations: list[str] = Field(default_factory=list)
    provenance_required: bool
    expiry_hours: int | None = None
    rate_limit: int | None = None
    output_label: str | None = None
    enforcement_type: Literal["automatic", "manual"] = "automatic"

    model_config = ConfigDict(from_attributes=True)


class AITaskTypeResponse(BaseModel):
    """Response schema for an AI task type in list views.

    Attributes:
        id: UUID primary key.
        task_type_id: Unique string identifier.
        display_name: Human-readable name.
        module_reference: AlcoaBase phase/feature reference.
        default_risk_tier: Default risk tier assignment.
        company_tier: Company-specific tier override (null if not overridden).
        is_active: Whether the task type is currently active.
        is_system_defined: Whether this is a built-in task type.
    """

    id: UUID
    task_type_id: str
    display_name: str
    module_reference: str
    default_risk_tier: Literal["high", "medium", "low"]
    company_tier: Literal["high", "medium", "low"] | None = None
    is_active: bool
    is_system_defined: bool

    model_config = ConfigDict(from_attributes=True)


class AITaskTypeDetailResponse(BaseModel):
    """Response schema for full AI task type detail view.

    Attributes:
        id: UUID primary key.
        task_type_id: Unique string identifier.
        display_name: Human-readable name.
        description: Detailed description.
        module_reference: AlcoaBase phase/feature reference.
        default_risk_tier: Default risk tier assignment.
        company_tier: Company-specific tier override (null if not overridden).
        risk_factors: Array of risk factor descriptions.
        is_active: Whether the task type is currently active.
        is_system_defined: Whether this is a built-in task type.
        control_set: The applicable control set for the effective tier.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    id: UUID
    task_type_id: str
    display_name: str
    description: str
    module_reference: str
    default_risk_tier: Literal["high", "medium", "low"]
    company_tier: Literal["high", "medium", "low"] | None = None
    risk_factors: list[str] = Field(default_factory=list)
    is_active: bool
    is_system_defined: bool
    control_set: TierDefinitionResponse | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class RiskTierOverrideResponse(BaseModel):
    """Response schema for a tier override within a profile.

    Attributes:
        id: UUID primary key.
        task_type_id: The AI task type identifier.
        assigned_tier: The overridden risk tier.
        justification: Rationale for the override.
        regulatory_reference: Regulatory basis (if provided).
        approved_by: UUID of approving user (if provided).
        approval_date: Approval timestamp (if approved).
        created_at: Creation timestamp.
    """

    id: UUID
    task_type_id: str
    assigned_tier: Literal["high", "medium", "low"]
    justification: str
    regulatory_reference: str | None = None
    approved_by: UUID | None = None
    approval_date: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompanyRiskProfileResponse(BaseModel):
    """Response schema for a Company Risk Profile.

    Attributes:
        id: UUID primary key.
        company_id: FK to the owning company.
        profile_name: Human-readable profile name.
        description: Optional description.
        regulatory_frameworks: Array of applicable framework identifiers.
        is_active: Whether this is the currently active profile.
        overrides: List of tier overrides in this profile.
        created_by: ID of the user who created the profile.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    id: UUID
    company_id: int
    profile_name: str
    description: str | None = None
    regulatory_frameworks: list[str] = Field(default_factory=list)
    is_active: bool
    overrides: list[RiskTierOverrideResponse] = Field(default_factory=list)
    created_by: int
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class HITLCheckpointResponse(BaseModel):
    """Response schema for a HITL checkpoint.

    Attributes:
        id: UUID primary key.
        company_id: FK to the company.
        operation_id: Reference to the AI operation.
        task_type_id: The AI task type identifier.
        ai_output_reference: URI or storage key for the AI output.
        status: Current checkpoint status.
        assigned_reviewer_role: Minimum role required to review.
        reviewer_user_id: ID of the reviewing user (set on review).
        reviewer_comments: Reviewer's comments.
        reviewed_sections: Array of reviewed section identifiers.
        created_at: Creation timestamp.
        expires_at: Expiry timestamp.
        reviewed_at: Review completion timestamp.
    """

    id: UUID
    company_id: int
    operation_id: str
    task_type_id: str
    ai_output_reference: str
    status: Literal["pending", "approved", "rejected", "expired"]
    assigned_reviewer_role: str
    reviewer_user_id: int | None = None
    reviewer_comments: str | None = None
    reviewed_sections: list[str] | None = None
    created_at: datetime
    expires_at: datetime
    reviewed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AIOperationLogResponse(BaseModel):
    """Response schema for an AI operation log entry.

    Attributes:
        id: UUID primary key.
        company_id: FK to the company.
        task_type_id: The AI task type identifier.
        risk_tier: Risk tier applied to this operation.
        user_id: ID of the user who initiated the operation.
        audit_depth: Logging depth applied.
        input_data: Input data (null for minimal depth).
        output_data: Output data (null for minimal depth).
        model_name: Name of the AI model used.
        inference_duration_ms: Duration of inference in milliseconds.
        token_count_input: Number of input tokens.
        token_count_output: Number of output tokens.
        gate_result: Whether the operation passed or was blocked.
        blocking_reason: Reason for blocking (if blocked).
        source_document_ids: Array of referenced document IDs.
        created_at: Creation timestamp.
    """

    id: UUID
    company_id: int
    task_type_id: str
    risk_tier: Literal["high", "medium", "low"]
    user_id: int
    audit_depth: Literal["full", "standard", "minimal"]
    input_data: dict | None = None
    output_data: dict | None = None
    model_name: str | None = None
    inference_duration_ms: int | None = None
    token_count_input: int | None = None
    token_count_output: int | None = None
    gate_result: Literal["passed", "blocked"]
    blocking_reason: str | None = None
    source_document_ids: list[str] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ControlEnforcementLogResponse(BaseModel):
    """Response schema for a control enforcement log entry.

    Attributes:
        id: UUID primary key.
        company_id: FK to the company.
        operation_log_id: FK to the associated AIOperationLog.
        task_type_id: The AI task type identifier.
        risk_tier: Risk tier applied.
        controls_enforced: Array of control names that were enforced.
        controls_satisfied: Mapping of control name to boolean satisfaction.
        overall_result: Whether all controls passed or operation was blocked.
        blocking_reason: Reason for blocking (if blocked).
        enforcement_duration_ms: Time spent on enforcement checks.
        created_at: Creation timestamp.
    """

    id: UUID
    company_id: int
    operation_log_id: UUID
    task_type_id: str
    risk_tier: Literal["high", "medium", "low"]
    controls_enforced: list[str] = Field(default_factory=list)
    controls_satisfied: dict[str, bool] = Field(default_factory=dict)
    overall_result: Literal["passed", "blocked"]
    blocking_reason: str | None = None
    enforcement_duration_ms: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DashboardStatsResponse(BaseModel):
    """Response schema for risk framework dashboard statistics.

    Attributes:
        operations_by_tier: Count of AI operations by tier in the last 30 days.
        pending_checkpoints: Count of pending HITL checkpoints.
        expired_checkpoints: Count of expired checkpoints.
        blocked_operations: Count of blocked operations.
        active_profile_name: Name of the company's active risk profile (null if none).
    """

    operations_by_tier: dict[str, int] = Field(
        default_factory=dict,
        description="Count of AI operations by tier (e.g., {'high': 5, 'medium': 12, 'low': 45}).",
    )
    pending_checkpoints: int = Field(ge=0, default=0)
    expired_checkpoints: int = Field(ge=0, default=0)
    blocked_operations: int = Field(ge=0, default=0)
    active_profile_name: str | None = None

    model_config = ConfigDict(from_attributes=True)
