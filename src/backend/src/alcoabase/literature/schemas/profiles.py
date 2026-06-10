"""Pydantic v2 schemas for literature search profile endpoints.

Provides request/response schemas for CRUD operations on per-company
search profiles. Profiles define default source selections, priority
overrides, and query filters applied to searches.

References:
    - Requirements: 13.1, 13.4, 14.2
    - Design doc: .kiro/specs/Step_9-1_literature-search-engine/design.md
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SearchProfileCreate(BaseModel):
    """Request schema for creating a search profile.

    Attributes:
        name: Profile name (unique per company).
        is_default: Whether this is the company's default profile.
        enabled_sources: List of source adapter names to include in searches.
        source_priorities: Mapping of source_name to priority override (1–100).
        default_filters: Default query filters applied to searches using this profile.
    """

    name: str = Field(..., min_length=1, max_length=200)
    is_default: bool = False
    enabled_sources: list[str] = Field(default_factory=list)
    source_priorities: dict[str, int] = Field(default_factory=dict)
    default_filters: dict = Field(default_factory=dict)


class SearchProfileUpdate(BaseModel):
    """Request schema for updating an existing search profile.

    All fields are optional; only provided fields are updated.

    Attributes:
        name: Updated profile name.
        is_default: Whether this should become the company's default profile.
        enabled_sources: Updated list of source adapter names.
        source_priorities: Updated source priority mapping.
        default_filters: Updated default query filters.
    """

    name: str | None = Field(None, min_length=1, max_length=200)
    is_default: bool | None = None
    enabled_sources: list[str] | None = None
    source_priorities: dict[str, int] | None = None
    default_filters: dict | None = None


class SearchProfileResponse(BaseModel):
    """Response schema for a search profile.

    Attributes:
        id: Profile record ID.
        company_id: Company this profile belongs to.
        name: Profile name (unique per company).
        is_default: Whether this is the company's default profile.
        enabled_sources: List of source adapter names included in searches.
        source_priorities: Mapping of source_name to priority override.
        default_filters: Default query filters applied to searches.
        created_at: When this profile was created.
        updated_at: When this profile was last modified.
    """

    id: int
    company_id: int
    name: str
    is_default: bool
    enabled_sources: list[str]
    source_priorities: dict[str, int]
    default_filters: dict
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
