"""Pydantic v2 schemas for per-company ingestion configuration.

Provides request/response schemas for creating, updating, and retrieving
ingestion pipeline configurations. Includes validation for conditional
email requirements and numeric field ranges.

References:
    - Requirements: 8.1, 8.2, 8.6, 8.7, 8.8
    - Design doc: .kiro/specs/Step_9-2_automated-ingestion-pipeline/design.md
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IngestionConfigurationCreate(BaseModel):
    """Request schema for creating a per-company ingestion configuration.

    Attributes:
        full_text_retrieval_enabled: Whether full-text retrieval via Unpaywall is active.
        storage_quota_mb: Maximum storage allocation in megabytes (min 100).
        retention_days: Days to retain original files before cleanup (0 = indefinite).
        unpaywall_email: Contact email for Unpaywall API; required when full-text
            retrieval is enabled.
        dual_uuid_integration_enabled: Whether to pipe sanitized content through
            the Dual-UUID extraction layer.
        max_concurrent_downloads: Maximum parallel download tasks per company (1–20).
    """

    full_text_retrieval_enabled: bool = Field(
        default=True,
        description="Whether full-text retrieval via Unpaywall is active.",
    )
    storage_quota_mb: int = Field(
        default=10240,
        ge=100,
        description="Maximum storage allocation in megabytes (min 100).",
    )
    retention_days: int = Field(
        default=365,
        ge=0,
        description="Days to retain original files before cleanup (0 = indefinite).",
    )
    unpaywall_email: str | None = Field(
        default=None,
        description=(
            "Contact email for Unpaywall API. "
            "Required when full_text_retrieval_enabled is True."
        ),
    )
    dual_uuid_integration_enabled: bool = Field(
        default=False,
        description="Whether to pipe sanitized content through the Dual-UUID extraction layer.",
    )
    max_concurrent_downloads: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum parallel download tasks per company (1–20).",
    )

    @model_validator(mode="after")
    def validate_unpaywall_email(self) -> "IngestionConfigurationCreate":
        """Require a valid email when full-text retrieval is enabled.

        Raises:
            ValueError: If full_text_retrieval_enabled is True and
                unpaywall_email is missing or has invalid format.
        """
        if self.full_text_retrieval_enabled:
            if not self.unpaywall_email:
                raise ValueError(
                    "unpaywall_email is required when full_text_retrieval_enabled is True"
                )
            if "@" not in self.unpaywall_email:
                raise ValueError(
                    "unpaywall_email must be a valid email address (must contain '@')"
                )
        return self


class IngestionConfigurationUpdate(BaseModel):
    """Request schema for updating an existing ingestion configuration.

    All fields are optional; only provided fields are updated.

    Attributes:
        full_text_retrieval_enabled: Whether full-text retrieval via Unpaywall is active.
        storage_quota_mb: Maximum storage allocation in megabytes (min 100).
        retention_days: Days to retain original files before cleanup (0 = indefinite).
        unpaywall_email: Contact email for Unpaywall API.
        dual_uuid_integration_enabled: Whether to pipe sanitized content through
            the Dual-UUID extraction layer.
        max_concurrent_downloads: Maximum parallel download tasks per company (1–20).
    """

    full_text_retrieval_enabled: bool | None = Field(
        default=None,
        description="Whether full-text retrieval via Unpaywall is active.",
    )
    storage_quota_mb: int | None = Field(
        default=None,
        ge=100,
        description="Maximum storage allocation in megabytes (min 100).",
    )
    retention_days: int | None = Field(
        default=None,
        ge=0,
        description="Days to retain original files before cleanup (0 = indefinite).",
    )
    unpaywall_email: str | None = Field(
        default=None,
        description=(
            "Contact email for Unpaywall API. "
            "Required when full_text_retrieval_enabled is True."
        ),
    )
    dual_uuid_integration_enabled: bool | None = Field(
        default=None,
        description="Whether to pipe sanitized content through the Dual-UUID extraction layer.",
    )
    max_concurrent_downloads: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Maximum parallel download tasks per company (1–20).",
    )


class IngestionConfigurationResponse(IngestionConfigurationCreate):
    """Response schema for an ingestion configuration record.

    Extends the Create schema with server-managed fields (id, company_id,
    timestamps).

    Attributes:
        id: Configuration record primary key.
        company_id: Company this configuration belongs to.
        created_at: When this configuration was created.
        updated_at: When this configuration was last modified.
    """

    id: int
    company_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
