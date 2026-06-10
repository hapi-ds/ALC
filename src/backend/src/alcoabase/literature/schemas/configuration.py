"""Pydantic v2 schemas for literature source configuration endpoints.

Provides request/response schemas for CRUD operations on per-company
source adapter configurations. API keys are accepted in plaintext on
create/update but are always returned masked in responses.

References:
    - Requirements: 3.1, 3.4, 3.5, 14.1
    - Design doc: .kiro/specs/Step_9-1_literature-search-engine/design.md
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SourceConfigurationCreate(BaseModel):
    """Request schema for creating a per-company source configuration.

    Attributes:
        source_adapter_name: Name of the registered source adapter.
        is_enabled: Whether this source is active for the company.
        api_key: Plaintext API key (encrypted before storage). 1–512 chars.
        priority: Search priority ranking (1=highest, 100=lowest).
        rate_limit_rpm: Custom per-company rate limit (requests/minute).
        proxy_override_url: Optional per-source proxy URL override.
        contact_email: Contact email for polite-pool APIs (e.g., Crossref).
        extra_config: Adapter-specific configuration settings.
    """

    source_adapter_name: str = Field(..., max_length=100)
    is_enabled: bool = True
    api_key: str | None = Field(None, min_length=1, max_length=512)
    priority: int = Field(50, ge=1, le=100)
    rate_limit_rpm: int | None = Field(None, ge=1)
    proxy_override_url: str | None = Field(None, max_length=500)
    contact_email: str | None = Field(None, max_length=320)
    extra_config: dict = Field(default_factory=dict)


class SourceConfigurationUpdate(BaseModel):
    """Request schema for updating an existing source configuration.

    All fields are optional; only provided fields are updated.

    Attributes:
        is_enabled: Whether this source is active for the company.
        api_key: New plaintext API key (encrypted before storage). 1–512 chars.
        priority: Updated search priority ranking (1=highest, 100=lowest).
        rate_limit_rpm: Updated per-company rate limit (requests/minute).
        proxy_override_url: Updated per-source proxy URL override.
        contact_email: Updated contact email for polite-pool APIs.
        extra_config: Updated adapter-specific configuration settings.
    """

    is_enabled: bool | None = None
    api_key: str | None = Field(None, min_length=1, max_length=512)
    priority: int | None = Field(None, ge=1, le=100)
    rate_limit_rpm: int | None = Field(None, ge=1)
    proxy_override_url: str | None = Field(None, max_length=500)
    contact_email: str | None = Field(None, max_length=320)
    extra_config: dict | None = None


class SourceConfigurationResponse(BaseModel):
    """Response schema for source configuration (API key masked).

    The api_key_masked field shows only the last 4 characters of the
    stored API key (e.g., "****abcd"), or None if no key is configured.

    Attributes:
        id: Configuration record ID.
        company_id: Company this configuration belongs to.
        source_adapter_name: Name of the registered source adapter.
        is_enabled: Whether this source is active for the company.
        api_key_masked: Masked API key showing last 4 chars, or None.
        priority: Search priority ranking (1=highest, 100=lowest).
        rate_limit_rpm: Custom per-company rate limit (requests/minute).
        proxy_override_url: Per-source proxy URL override.
        contact_email: Contact email for polite-pool APIs.
        extra_config: Adapter-specific configuration settings.
        created_at: When this configuration was created.
        updated_at: When this configuration was last modified.
    """

    id: int
    company_id: int
    source_adapter_name: str
    is_enabled: bool
    api_key_masked: str | None
    priority: int
    rate_limit_rpm: int | None
    proxy_override_url: str | None
    contact_email: str | None
    extra_config: dict
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
